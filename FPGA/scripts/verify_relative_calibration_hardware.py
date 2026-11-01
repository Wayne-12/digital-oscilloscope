"""Opt-in real calibration acceptance; restores config and preserves saved baselines.

The board must already have the verified firmware loaded and SW0 enabled.
No JTAG or Flash operations are performed by this script.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output-dir',type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    spec = importlib.util.spec_from_file_location('relative_calibration_acceptance_ui',ROOT/'示波器显示界面.py')
    ui = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ui
    spec.loader.exec_module(ui)
    np,p = ui.np,ui.proto
    output = args.output_dir or ROOT/'FPGA/reports/relative_calibration_hardware'/datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    app = ui.QtWidgets.QApplication([])
    ui.configure_fonts(app)
    ui.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
    window = ui.ScopeWindow(profile_path=output/'ui_profile.json')
    window.timer.stop()
    window.source.setCurrentIndex(1)
    window.port.setCurrentIndex(window.port.findData(args.port))
    window.baud.setCurrentText('921600')
    window.connect_button.setEnabled(False)
    window.connect_button.setText('独立串口验证中')
    window.tabs.setCurrentIndex(3)
    window.resize(1600,1100)
    worker = ui.SerialWorker(args.port,921600)
    report = {'verdict':'FAIL','source':'hardware-uart','hardware_verified':False,
              'output':str(output),'port':args.port,'restored':False,'flash_programmed':False}
    baseline_path = ROOT/'PC/ui/hardware_calibration_baseline.json'
    baseline_before = baseline_path.read_bytes() if baseline_path.exists() else None
    original = None

    def progress(step,text,status):
        window.receive_calibration_progress(step,text,status)
        app.processEvents()
        if status.startswith('完成'):
            print(f'STEP {step+1}: {text}',flush=True)

    def run(label,baseline):
        window.hardware_calibration_busy = True
        window.cal_step = 0
        window._calibration_rebuild = False
        result = ui.hwcal.run_closed_loop(worker,output/label,worker.device_identity,
                                          baseline=baseline,progress=progress)
        assert result['status']=='PASS' and result['restored'],result
        assert result['configuration_before_hex']==original.hex()
        assert len(result['raw_frames'])==35
        assert all(k not in result for k in ('snr','sinad','sfdr','enob'))
        for row in result['raw_frames']:
            words = np.load(output/label/row['file'])
            assert len(words)==16384 and not np.any(words&32768)
        # Recompute the comparison directly from the two saved raw holdout frames.
        zero_words = np.load(output/label/'033_zero_recheck.npy')
        dc_words = np.load(output/label/'034_dc_holdout_512.npy')
        for key,words,target in (('zero',zero_words,0.0),
                                 ('dc_holdout',dc_words,result['reference_gain']*512*ui.hwcal.SCALE)):
            values = result['before_after'][key]
            observed = float(((2047.5-(words&4095).astype(float))*ui.hwcal.SCALE).mean())
            assert abs(values['before_volts']-observed)<1e-12
            assert abs(values['expected_volts']-target)<1e-12
            assert abs(values['after_error_volts']-((observed-result['offset'])/result['gain']-target))<1e-12
        window.receive_hardware_calibration(result)
        return result

    try:
        worker.open_link()
        version = struct.unpack_from('<I',worker.exchange(p.GET_VERSION).payload,4)[0]
        assert version==0xA0261026 and worker.capabilities==7
        report.update(build_id=f'0x{version:08X}',capabilities=worker.capabilities,device_id=worker.device_identity)
        worker.exchange(p.STOP)
        original = worker.exchange(p.GET_CONFIG).payload
        before = worker.read_status()
        report.update(configuration_before_hex=original.hex(),status_before=before)
        window.hardware_connected = True
        window.device_capabilities = worker.capabilities
        window.device_rate = 25000000
        window.badge.setText(f'● {args.port} · 实物相对校准验证')
        saved = ui.hwcal.validate_fingerprint(json.loads(baseline_before)) if baseline_before else None
        if saved is not None:
            assert saved['device_id']==worker.device_identity
            window.hardware_baseline = saved
            report['saved_baseline_sha256'] = hashlib.sha256(baseline_before).hexdigest()
        print('RUN 1: saved relative baseline' if saved else 'RUN 1: first relative reference',flush=True)
        first = run('first_run',saved)
        ui.write_hardware_fingerprint(output/'measured_fingerprint.json',first)
        print('RUN 2: repeat against the same relative reference',flush=True)
        # Retain the same reference across runs: avoid silently redefining unity.
        repeat = run('repeat_run',saved)
        assert abs(repeat['dc_gain']/first['dc_gain']-1)<.05
        report.update(first_report=str(output/'first_run/report.json'),repeat_report=str(output/'repeat_run/report.json'),
                      repeat_dc_gain_drift_percent=(repeat['dc_gain']/first['dc_gain']-1)*100,
                      comparison=repeat['before_after'],response_frequency=repeat['response_frequency'],
                      response_db=repeat['response_db'],dc_r2=repeat['dc_r2'],
                      gain=repeat['gain'],offset=repeat['offset'],noise=repeat['noise'])
        # Cancellation is injected after real zero-output acquisition has modified config.
        def cancel_progress(step,text,status):
            if step==1:
                worker.cancel_capture.set()
        cancelled = ui.hwcal.run_closed_loop(worker,output/'cancel_recovery',worker.device_identity,
                                             baseline=saved,progress=cancel_progress)
        assert cancelled['status']=='CANCELLED' and cancelled['restored']
        assert cancelled['configuration_after_hex']==original.hex()
        worker.cancel_capture.clear()
        report['cancel_and_restore'] = 'PASS'
        current = worker.capture(8)
        raw = current.words.copy()
        window.single_pending = True
        window.receive_capture(current)
        window.single_pending = False
        window.apply_cal.setChecked(True)
        assert window.active_display_calibration() is not None
        np.testing.assert_array_equal(window.current.words,raw)
        np.save(output/'display_raw.npy',raw)
        window.show()
        app.processEvents()
        assert window.grab().save(str(output/'hardware_calibration.png'))
        window.tabs.setCurrentIndex(0)
        app.processEvents()
        assert window.grab().save(str(output/'corrected_waveform.png'))
        after = worker.read_status()
        deltas = [(b-a)&0xffffffff for a,b in zip(before['counters'][:8],after['counters'][:8])]
        report.update(status_after=after,fpga_error_counter_deltas=deltas,
                      parser_errors=dict(worker.parser.errors),raw_preserved=True,
                      raw_frames=70+len(cancelled['raw_frames'])+1)
        assert not after['backend_error'] and not any(deltas) and not any(worker.parser.errors.values())
        report.update(verdict='PASS',hardware_verified=True)
    except Exception as error:
        report.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        if original is not None:
            try:
                worker.cancel_capture.clear()
                worker.exchange(p.STOP,restoring=True)
                config = ui.hwcal.decode_configuration(original)
                worker.exchange(p.SET_DDS,config['dds'],restoring=True)
                worker.exchange(p.SET_TRIGGER,config['trigger'],restoring=True)
                restored = worker.exchange(p.GET_CONFIG,restoring=True).payload
                assert restored==original
                report.update(restored=True,configuration_after_hex=restored.hex())
            except Exception as error:
                report.update(verdict='FAIL',restored=False,restore_error=repr(error))
        if worker.link is not None:
            worker.link.close()
        baseline_after = baseline_path.read_bytes() if baseline_path.exists() else None
        report['saved_baseline_unchanged'] = baseline_after==baseline_before
        if not report['saved_baseline_unchanged']:
            report.update(verdict='FAIL',error='Saved calibration baseline unexpectedly changed')
        window.close()
        (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'verdict':report['verdict'],'restored':report['restored'],
                      'error':report.get('error'),'report':str(output)},ensure_ascii=False),flush=True)
    return report['verdict']!='PASS'


if __name__=='__main__':
    raise SystemExit(main())
