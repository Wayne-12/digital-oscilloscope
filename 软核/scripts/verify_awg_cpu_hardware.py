"""Real UART table readback and safe DAC->ADC loopback acceptance; no Flash writes."""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,importlib.util,json,os,struct,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]

def fit_table(raw,table,frequency):
    y=2047-(raw[:4096]&4095).astype(float);y-=y.mean()
    inc=round(frequency*2**32/25000000)
    phase=np.arange(len(y),dtype=np.uint64)*inc
    best=None
    for offset in range(1024):
        indices=(((phase+offset*2**22)&0xffffffff)>>22).astype(int)
        x=np.asarray(table,dtype=float)[indices];x-=x.mean()
        gain=float(x@y/(x@x));prediction=x*gain
        error=float(np.sqrt(np.mean((y-prediction)**2))/np.std(y))
        if best is None or error<best['normalized_rms_error']:
            best=dict(phase_index=offset,gain=gain,normalized_rms_error=error,
                correlation=float(np.corrcoef(x,y)[0,1]),adc_vpp=float(np.ptp(y)))
    return best

def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--output-dir',type=Path,required=True)
    cli.add_argument('--firmware',type=Path,required=True);cli.add_argument('--port',default='COM12');a=cli.parse_args()
    sys.stdout.reconfigure(encoding='utf-8');os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    spec=importlib.util.spec_from_file_location('awg_hardware_ui',ROOT/'示波器显示界面.py')
    ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
    p=ui.proto;awg=ui.awg;out=a.output_dir;out.mkdir(parents=True,exist_ok=False)
    worker=ui.SerialWorker(a.port,921600)
    result=dict(verdict='FAIL',build='0xA4261028',firmware_sha256=hashlib.sha256(a.firmware.read_bytes()).hexdigest(),
        frames=[],rejections=[],restored=False,started_at=datetime.now().astimezone().isoformat())
    original=mode=original_awg=original_table=None;expected_errors=0
    def reject(kind,payload):
        nonlocal expected_errors
        try:worker.exchange(kind,payload)
        except ValueError as exc:
            assert '状态码' in str(exc);expected_errors+=1;result['rejections'].append(dict(command=kind,error=str(exc)))
        else:raise AssertionError('invalid AWG operation was accepted')
    def dds(enabled,frequency=100000,amplitude=819):
        awg.ack(worker,p.SET_DDS,struct.pack('<BBIIHi',0,enabled,frequency,0,amplitude,0))
    try:
        worker.open_link();assert worker.capabilities==63
        assert struct.unpack_from('<I',worker.exchange(p.GET_VERSION).payload,4)[0]==0xA4261028
        worker.exchange(p.STOP);original=worker.exchange(p.GET_CONFIG).payload
        mode=worker.exchange(p.GET_CAPTURE_CONFIG).payload;original_awg=awg.status(worker)
        result['awg_before']=original_awg
        if original_awg['valid']:
            original_table=awg.read_table(worker)
            (out/'original_awg_table.json').write_text(json.dumps(original_table),encoding='utf-8')
        baseline=worker.read_status()['counters'];result['baseline_counters']=baseline
        dds(0)
        values=[(i*73)%65535-32767 for i in range(1024)]
        awg.upload(worker,values);result['digital_table_readback']='PASS_1024_WORDS_ALL_BITS'
        # Corrupt end-to-end CRC and incomplete replacement leave old active table intact.
        awg.ack(worker,awg.BEGIN,struct.pack('<I',1024))
        reject(awg.CHUNK,struct.pack('<Hh',0,-32768))
        reject(awg.CHUNK,struct.pack('<Hh',1,1))
        reject(awg.COMMIT,b'\0\0')
        assert awg.read_table(worker)==values
        awg.ack(worker,awg.BEGIN,struct.pack('<I',1024))
        data=awg.encode_table(values)
        for start in range(0,1024,256):awg.ack(worker,awg.CHUNK,struct.pack('<H',start)+data[start*2:(start+256)*2])
        reject(awg.COMMIT,struct.pack('<H',p.crc16(data)^1))
        assert awg.read_table(worker)==values
        result['failed_upload_preserves_active_table']=True
        worker.exchange(p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',6,0,0,2,-100,100,1,100,16383,2))
        for name in ('harmonic_mix','asymmetric_triangle','pulse_25percent','dc_quarter'):
            worker.exchange(p.STOP);dds(0)
            table=([8192]*1024 if name=='dc_quarter' else awg.load_table(ROOT/'PC/waveforms'/f'{name}.csv'))
            awg.upload(worker,table);awg.ack(worker,awg.SELECT,b'\1');dds(1)
            if name=='harmonic_mix':reject(awg.BEGIN,struct.pack('<I',1024))
            time.sleep(.08);frame=worker.capture(8)
            np.save(out/(name+'.npy'),frame.words)
            assert len(frame.words)==16384 and not np.any(frame.words&0x8000)
            assert frame.fpga_saturation['saturated_samples']==frame.fpga_saturation['events']==0
            row=dict(name=name,timestamp=frame.timestamp,table_crc=p.crc16(awg.encode_table(table)),
                     saturation=frame.fpga_saturation,measurement=frame.fpga_measurement)
            if name!='dc_quarter':
                fit=fit_table(frame.words,table,100000);row['shape_fit']=fit
                assert fit['adc_vpp']>=8 and abs(fit['correlation'])>.96 and fit['normalized_rms_error']<.28,fit
            else:
                assert np.ptp(frame.words&4095)<20,'DC table still contains substantial AC'
            result['frames'].append(row)
            (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        final=worker.read_status()['counters']
        delta=[(v-b)&0xffffffff for v,b in zip(final[:8],baseline[:8])]
        assert delta==[0,0,0,0,0,expected_errors,0,0],delta
        assert not any(worker.parser.errors.values())
        result.update(verdict='PASS',fpga_error_deltas=delta,expected_command_rejections=expected_errors,
            unexpected_fpga_errors=0,parser_errors=dict(worker.parser.errors))
    except BaseException as exc:result['error']=repr(exc)
    finally:
        try:
            if original is not None:
                worker.cancel_capture.clear();worker.exchange(p.STOP,restoring=True);dds(0)
                if original_table is not None:
                    awg.upload(worker,original_table)
                awg.ack(worker,awg.SELECT,bytes([int(original_awg['selected'])]))
                cfg=ui.hwcal.decode_configuration(original)
                worker.exchange(p.SET_RECORD,struct.pack('<II',16384,round(cfg['pre']*1e6/16383)),restoring=True)
                worker.exchange(p.SET_TRIGGER,original[8:32],restoring=True)
                worker.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
                worker.exchange(p.SET_DDS,original[32:48],restoring=True)
                assert worker.exchange(p.GET_CONFIG).payload==original
                assert worker.exchange(p.GET_CAPTURE_CONFIG).payload==mode
                after=awg.status(worker);result['awg_after']=after
                assert after['selected']==original_awg['selected']
                if original_table is not None:
                    assert after['valid'] and after['active_crc']==original_awg['active_crc']
                    assert awg.read_table(worker)==original_table
                    result['original_awg_table_restored']=True
                else:
                    result['original_awg_table_restored']=None
                    result['table_state_limitation']='No original valid table. Firmware has no clear-table command; the unselected diagnostic table may remain in RAM.'
                result['restored']=True
        except BaseException as exc:result.update(verdict='FAIL',restore_error=repr(exc))
        if worker.link is not None:worker.link.close()
        result['finished_at']=datetime.now().astimezone().isoformat()
        (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result['verdict']!='PASS' or not result['restored']
if __name__=='__main__':raise SystemExit(main())
