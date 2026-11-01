"""COM12 physical acceptance for AUTO/NORMAL/SINGLE; no programming or Flash.

Requires the 0xA1261026 image, manually enabled and the established OUTA-IN loop.
Uses only the existing DDS output. Restores trigger/record/DDS and mode settings.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import importlib.util
import json
import os
import struct
import sys
import time
import threading

ROOT=Path(__file__).resolve().parents[2]

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--port',default='COM12')
    cli.add_argument('--firmware',type=Path,required=True)
    cli.add_argument('--output-dir',type=Path,required=True)
    a=cli.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    sys.stdout.reconfigure(encoding='utf-8')
    spec=importlib.util.spec_from_file_location('capture_modes_ui',ROOT/'示波器显示界面.py')
    ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
    import numpy as np
    p=ui.proto
    a.output_dir.mkdir(parents=True,exist_ok=False)
    out=a.output_dir
    worker=ui.SerialWorker(a.port,921600)
    report={'source':'hardware-uart','verdict':'FAIL','started_at':datetime.now().astimezone().isoformat(),
            'port':a.port,'baud':921600,'firmware_sha256':hashlib.sha256(a.firmware.read_bytes()).hexdigest(),
            'frames':[],'checks':{},'restored':False}
    original=original_mode=None
    def save():
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def trigger(kind=0,threshold=4):
        return struct.pack('<BBhHhhIIHI',kind,0,threshold,2,-100,100,1,100,100,256)
    def capture(**kwargs):
        # NORMAL deliberately waits indefinitely in the product. The automated
        # acceptance has its own finite watchdog and preserves restore handling.
        timer=threading.Timer(8,worker.cancel_capture.set)
        timer.start()
        try:
            return worker.capture(5,**kwargs)
        finally:
            timer.cancel();timer.join()
    def record(frame,label):
        assert len(frame.words)==16384 and frame.rate==25000000
        assert not np.any(frame.words&0x8000),'OTR in physical frame'
        x=2047-(frame.words&4095).astype(np.int64)
        m=frame.fpga_measurement
        assert m and not m['error'] and m['sum']==int(x.sum()) and m['square_sum']==int((x*x).sum())
        assert (m['minimum'],m['maximum'])==(int(x.min()),int(x.max()))
        assert m['vpp']>=8,'Missing physical loopback signal'
        np.save(out/f'{label}.npy',frame.words)
        report['frames'].append({'case':label,'timestamp':frame.timestamp,'trigger':frame.trigger,'measurement':m})
        save()
    try:
        worker.open_link()
        version=worker.exchange(p.GET_VERSION)
        report['build']=hex(struct.unpack_from('<I',version.payload,4)[0])
        assert report['build']=='0xa1261026' and worker.capabilities==15
        worker.exchange(p.STOP)
        original=worker.exchange(p.GET_CONFIG).payload
        original_mode=worker.exchange(p.GET_CAPTURE_CONFIG).payload
        cfg=ui.hwcal.decode_configuration(original)
        assert cfg['enabled'] and cfg['amplitude']<=819,'Existing <=10% enabled DDS required'
        baseline=worker.read_status()['counters']
        report['baseline_counters']=list(baseline)
        worker.exchange(p.SET_TRIGGER,trigger(threshold=4095))
        for i in range(6):
            frame=capture(acquisition_mode=0)
            record(frame,f'auto_impossible_{i}')
            assert p.decode_capture_configuration(worker.exchange(p.GET_CAPTURE_CONFIG))==(0,2500000)
            before=worker.exchange(p.READ_MEASURE)
            time.sleep(.15)
            after=worker.exchange(p.READ_MEASURE)
            assert (before.timestamp,before.payload)==(after.timestamp,after.payload)
        assert len({f['timestamp'] for f in report['frames']})==6
        report['checks']['auto_timeout_and_backpressure']='PASS'
        worker.exchange(p.STOP)
        worker.exchange(p.SET_CAPTURE_MODE,p.capture_mode_payload(1))
        worker.exchange(p.RUN)
        for _ in range(10):
            time.sleep(.05)
            status=worker.read_status()
            assert status['flags']&1 and not status['flags']&2,'NORMAL captured without a possible trigger'
        worker.exchange(p.STOP)
        assert not worker.read_status()['flags']&1
        report['checks']['normal_wait_and_stop']='PASS'
        for kind in (0,1):
            worker.exchange(p.STOP)
            worker.exchange(p.SET_TRIGGER,trigger(kind))
            for i in range(8):
                frame=capture(acquisition_mode=1)
                record(frame,f'normal_edge_{kind}_{i}')
                assert abs(frame.fpga_measurement['frequency']-cfg['frequency'])<=max(1000,cfg['frequency']*.01)
                x=2047-(frame.words&4095).astype(np.int64)
                k=frame.trigger
                # Detector is pipelined; establish polarity over a small interval.
                slope=int(x[k+8])-int(x[k-8])
                assert slope>0 if kind==0 else slope<0
        report['checks']['normal_rise_fall_and_rearm']='PASS'
        worker.exchange(p.STOP)
        worker.exchange(p.SET_TRIGGER,trigger())
        for i in range(3):
            frame=capture()
            record(frame,f'single_{i}')
            time.sleep(.3)
            state=worker.read_status()
            stable=worker.exchange(p.READ_MEASURE)
            assert state['flags']&2 and not state['flags']&1 and stable.timestamp==frame.timestamp
        report['checks']['single_hold_and_repeat']='PASS'
        worker.exchange(p.STOP)
        # Exercise the actual worker path once more after STOP.
        record(capture(acquisition_mode=0),'stop_restart_auto')
        assert len({f['timestamp'] for f in report['frames']})==len(report['frames'])
        assert not any(worker.parser.errors.values())
        final=worker.read_status()['counters']
        report['error_deltas']=[(v-b)&0xffffffff for v,b in zip(final[:8],baseline[:8])]
        assert not any(report['error_deltas'])
        report['parser_errors']=worker.parser.errors.copy()
        report['checks']['stop_restart_and_integrity']='PASS'
        report['verdict']='PASS'
    except BaseException as exc:
        report['error']=repr(exc)
        raise
    finally:
        try:
            if original is not None:
                worker.exchange(p.STOP)
                worker.exchange(p.SET_TRIGGER,original[8:32])
                worker.exchange(p.SET_CAPTURE_MODE,original_mode)
                assert worker.exchange(p.GET_CONFIG).payload==original
                assert worker.exchange(p.GET_CAPTURE_CONFIG).payload==original_mode
                report['restored']=True
        except BaseException as exc:
            report['restore_error']=repr(exc);report['verdict']='FAIL'
        if worker.link is not None:worker.link.close()
        report['finished_at']=datetime.now().astimezone().isoformat()
        save()
        print('CAPTURE_MODES_HARDWARE_'+report['verdict']+' '+str(out),flush=True)
    return report['verdict']!='PASS' or not report['restored']

if __name__=='__main__':raise SystemExit(main())
