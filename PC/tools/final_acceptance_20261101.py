"""Final live-board and production Qt checks; no programming operations."""
from pathlib import Path
import importlib.util
import json
import os
import struct
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'PC/reports/final_acceptance_20261101'/os.environ.get('SCOPE_ACCEPTANCE_VARIANT','')
OUT.mkdir(parents=True,exist_ok=True)
spec = importlib.util.spec_from_file_location('final_scope_ui', ROOT/'示波器显示界面.py')
u = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = u
spec.loader.exec_module(u)
p, np = u.proto, u.np
exchange_original = u.SerialWorker.exchange
def traced_exchange(self, kind, payload=b'', *args, **kwargs):
    try:
        return exchange_original(self, kind, payload, *args, **kwargs)
    except Exception as exc:
        with (OUT/'exchange_failures.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps({'kind':hex(kind),'payload':payload.hex(),'sequence_next':self.sequence,'error':repr(exc)},ensure_ascii=False)+'\n')
        raise
u.SerialWorker.exchange = traced_exchange
report = {'result': 'FAIL', 'physical_panel': 'User confirmed six pages and local controls normal; SW7 ON',
          'checks': {}, 'limits': ['Finite final functional run; no new absolute AC accuracy or overload qualification']}
baseline = json.loads((OUT/'baseline.json').read_text())['before']
original = bytes.fromhex(baseline['config'])
mode = bytes.fromhex(baseline['capture_config'])
app = u.QtWidgets.QApplication([])
u.configure_fonts(app)
w = None
client = None

def wait(predicate, seconds=20):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise TimeoutError('UI deadline: '+(w.logs.toPlainText()[-1500:] if w else ''))

def shot(name):
    app.processEvents()
    assert w.grab().save(str(OUT/(name+'.png')))

def restore(link):
    link.exchange(p.STOP, restoring=True)
    link.exchange(p.SET_RECORD, struct.pack('<II',16384,500000), restoring=True)
    link.exchange(p.SET_TRIGGER, original[8:32], restoring=True)
    link.exchange(p.SET_DDS, original[32:48], restoring=True)
    link.exchange(p.SET_CAPTURE_MODE, mode, restoring=True)
    assert link.exchange(p.GET_CONFIG, restoring=True).payload == original

try:
    client = u.SerialWorker('COM12', 921600)
    client.open_link()
    assert client.build_id == 0xAF311031 and client.capabilities == 63
    report['build'] = hex(client.build_id)
    before = client.read_status()
    client.exchange(p.STOP)
    client.exchange(p.SET_TRIGGER, struct.pack('<BBhHhhIIHI',0,0,0,2,-100,100,1,100,16383,2))
    report['frames'] = []
    for wave in range(4):
        client.exchange(p.STOP)
        client.stream_mode = None
        client.exchange(p.SET_DDS, struct.pack('<BBIIHi',wave,1,100000,0,819,0))
        frame = client.capture(8, acquisition_mode=0)
        x = 2047-(frame.words & 4095).astype(np.int64)
        m = frame.fpga_measurement
        assert len(x) == 16384 and frame.rate == 25000000
        assert m['minimum'] == int(x.min()) and m['maximum'] == int(x.max())
        assert m['sum'] == int(x.sum()) and m['square_sum'] == int((x*x).sum())
        assert m['vpp'] == int(np.ptp(x))
        assert abs(m['rms']-np.sqrt(np.mean(x.astype(float)**2))) <= .51
        assert not np.any(frame.words & 0x8000)
        if wave < 3:
            assert m['period_valid'] and abs(m['frequency']-100000) < 2000
            assert np.ptp(x) > 8
        repeated = client.exchange(p.READ_WAVE,struct.pack('<II',0,16384),wave=True,record_length=16384)
        assert repeated.timestamp == frame.timestamp and np.array_equal(repeated.words,frame.words)
        env = client.exchange(p.READ_ENVELOPE,struct.pack('<H',800),record_length=16384,envelope_buckets=800)
        for i,(lo,hi,otr) in enumerate(env.buckets):
            segment = x[i*16384//800:(i+1)*16384//800]
            assert (lo,hi) == (int(segment.min()),int(segment.max())) and not otr
        roi = client.exchange(p.READ_WAVE,struct.pack('<II',7000,1024),wave=True,record_length=16384,overview=env)
        assert np.array_equal(roi.words,frame.words[7000:8024])
        if wave < 3:
            peak = int(np.argmax(np.abs(np.fft.rfft(x[:1024]*np.hanning(1025)[:-1]))[1:511])+1)
            assert abs(peak-frame.fpga_spectrum['peak_bin']) <= 1
        np.save(OUT/f'wave_{wave}.npy',frame.words,allow_pickle=False)
        report['frames'].append({'wave':wave,'timestamp':frame.timestamp,'measurement':m,'saturation':frame.fpga_saturation})
    report['checks']['four_standard_dds_actual_adc_measurement_fft_envelope_roi_repeat'] = 'PASS'
    restore(client)
    after = client.read_status()
    assert after['counters'][:8] == before['counters'][:8]
    assert not any(client.parser.errors.values())
    report['checks']['protocol_no_new_errors'] = 'PASS'
    report['status_before'], report['status_after'] = before, after
    client.link.close()
    client = None

    w = u.ScopeWindow(profile_path=OUT/'isolated_ui_profile.json')
    w.install_absolute_profile(ROOT/'校正参数.json')
    w.resize(1600,1000)
    w.set_running(False)
    w.source.setCurrentIndex(1)
    w.port.setCurrentIndex(w.port.findData('COM12'))
    w.baud.setCurrentText('921600')
    w.show()
    w.toggle_connect()
    wait(lambda:w.hardware_connected and not w._commands_pending)
    assert w.device_build == 0xAF311031
    assert w.apply_absolute.isChecked(), w.absolute_status.text()
    w.acquisition_mode.setCurrentIndex(0)
    w.set_running(True)
    wait(lambda:w.capture_count >= 3)
    w.stop_capture()
    wait(lambda:not w.capture_busy and not w._commands_pending)
    assert w.current is not None and len(w.current.words) == 16384
    assert w.current.source == '硬件 UART'
    w.cursor_time.setChecked(True)
    w.cursor_volt.setChecked(True)
    w.autoscale()
    assert 'Δt' in w.cursor_readout.text() and 'ΔV' in w.cursor_readout.text()
    shot('ui_waveform')
    report['ui_metrics'] = {k:v.text() for k,v in w.metrics.items()}
    report['calibration_status'] = w.absolute_status.text()
    w.tabs.setCurrentIndex(1)
    app.processEvents()
    assert len(w.fft_curve.yData) == 513 and '1024' in w.fft_info.text()
    shot('ui_fft')
    w.tabs.setCurrentIndex(2)
    w.multires_mode.setChecked(True)
    old = w.current.timestamp
    w.single()
    wait(lambda:w.current.timestamp != old and not w.capture_busy and not w.single_pending)
    assert len(w.current.overview.buckets) == 800
    shot('ui_multires')
    report['checks']['ui_live_run_stop_single_cursors_autoscale_fft_multires_calibration'] = 'PASS'
    w.tabs.setCurrentIndex(3)
    w.start_hardware_calibration()
    wait(lambda:w.hardware_calibration_busy)
    wait(lambda:not w.hardware_calibration_busy,180)
    report['closed_loop_selftest'] = w.hardware_calibration
    selftest_passed = bool(w.hardware_calibration_valid and w.hardware_calibration and w.hardware_calibration['status'] == 'PASS')
    shot('ui_selftest')
    report['checks']['ui_real_closed_loop_selftest'] = 'PASS' if selftest_passed else 'FAIL'
    report['selftest_outcome'] = w.cal_result.text()
    w.tabs.setCurrentIndex(0)
    w.open_measurement_guide()
    assert '0xAF311031' in w.measurement_state.text()
    w.measurement_dialog.accept()
    w.toggle_connect()
    wait(lambda:w.worker is None)
    w.toggle_connect()
    wait(lambda:w.hardware_connected and not w._commands_pending)
    report['checks']['ui_disconnect_reconnect'] = 'PASS'
    report['result'] = 'PASS' if selftest_passed else 'FAIL'
except Exception as exc:
    report['error'] = repr(exc)
    report['traceback'] = traceback.format_exc()
finally:
    if w is not None:
        report['ui_log'] = w.logs.toPlainText()
        report['ui_selftest_text'] = w.cal_result.text()
        if w.worker is not None:
            w.worker.shutdown.set()
            w.worker.cancel_capture.set()
            w.worker.wait(10000)
            app.processEvents()
        w.close()
        app.processEvents()
    if client is not None and client.link:
        client.link.close()
    link = u.SerialWorker('COM12',921600)
    try:
        link.open_link()
        restore(link)
        report['restored'] = True
        report['final_status'] = link.read_status()
    except Exception as exc:
        report.update(result='FAIL',restore_error=repr(exc))
    finally:
        if link.link:
            link.link.close()
    (OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2,default=str),flush=True)
sys.exit(report['result'] != 'PASS')
