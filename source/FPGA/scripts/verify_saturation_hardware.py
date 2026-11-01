"""Physical acceptance of full-frame raw-code saturation statistics.

Normal ADC records and explicitly tagged FPGA-injected diagnostic records
are reported separately. Never changes analog amplitude or programs Flash.
"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,importlib.util,json,os,struct,sys,threading,time
ROOT=Path(__file__).resolve().parents[2]

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--port',default='COM12');cli.add_argument('--firmware',type=Path,required=True)
    cli.add_argument('--output-dir',type=Path,required=True)
    cli.add_argument('--build',default='0xA2261027')
    a=cli.parse_args();sys.stdout.reconfigure(encoding='utf-8');os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    spec=importlib.util.spec_from_file_location('saturation_ui',ROOT/'示波器显示界面.py')
    ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
    import numpy as np
    p=ui.proto;out=a.output_dir;out.mkdir(parents=True,exist_ok=False)
    worker=ui.SerialWorker(a.port,921600)
    report={'verdict':'FAIL','source':'hardware-uart','started_at':datetime.now().astimezone().isoformat(),
        'port':a.port,'baud':921600,'firmware_sha256':hashlib.sha256(a.firmware.read_bytes()).hexdigest(),
        'frames':[],'restored':False,'diagnostic_scope':'FPGA capture-memory input only; ADC analog input not overdriven'}
    original=original_mode=None
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def acquire(**kwargs):
        timer=threading.Timer(10,worker.cancel_capture.set);timer.start()
        try:return worker.capture(8,**kwargs)
        finally:timer.cancel();timer.join()
    def verify(frame,mode,pre,label):
        stats=frame.fpga_saturation
        assert stats is not None and stats['diagnostic']==bool(mode)
        base=(frame.timestamp-frame.record_offset)%(1<<64)
        full=worker.exchange(p.READ_WAVE,struct.pack('<II',0,16384),wave=True,record_length=16384)
        assert full.timestamp==base and full.rate==frame.rate
        raw=full.words&4095;mask=(raw==0)|(raw==4095)
        samples=int(mask.sum());events=int(np.count_nonzero(mask & ~np.r_[False,mask[:-1]]))
        assert stats=={'count':16384,'saturated_samples':samples,'events':events,'diagnostic':bool(mode)}
        assert full.trigger==pre
        if mode:
            phase=(np.arange(16384,dtype=np.uint64)+base)%16
            expected=(np.full(16384,4095 if mode==2 else 2047,dtype=np.uint16) if mode!=1 else
                np.where(np.isin(phase,(0,1,2,15)),0,np.where(phase==7,4095,2047)))
            assert np.array_equal(raw,expected),'Injected capture words differ from the declared timestamp pattern'
        else:
            assert np.ptp(raw)>=8 and not np.any(full.words&0x8000),'Missing normal physical ADC loopback signal'
        if mode==2:assert samples==16384 and events==1
        if mode==3:assert samples==events==0
        measurement=worker.exchange(p.READ_MEASURE)
        assert measurement.timestamp==base
        m=p.decode_measurement(measurement);x=2047-raw.astype(np.int64)
        assert m['sum']==int(x.sum()) and m['square_sum']==int((x*x).sum()) and not m['error']
        assert (m['minimum'],m['maximum'])==(int(x.min()),int(x.max()))
        if frame.overview is not None:
            roi=worker.read_roi(frame,37,333)
            assert roi.fpga_saturation==stats
            assert np.array_equal(roi.words,full.words[37:370])
        repeated=worker.exchange(p.READ_SATURATION)
        assert repeated.timestamp==base and p.decode_saturation(repeated)==stats
        np.save(out/(label+'.npy'),full.words)
        report['frames'].append({'case':label,'diagnostic_mode':mode,'pretrigger':pre,'timestamp':base,
            'saturation':stats,'full_raw_verified':True,'roi_invariance':frame.overview is not None})
        save();print('SATURATION_PHYSICAL_FRAME_PASS '+label+' '+str(stats),flush=True)
    try:
        worker.open_link()
        version=worker.exchange(p.GET_VERSION);build=struct.unpack_from('<I',version.payload,4)[0]
        report['build']=hex(build);assert build==int(a.build,0) and worker.capabilities&31==31
        worker.exchange(p.STOP)
        original=worker.exchange(p.GET_CONFIG).payload;original_mode=worker.exchange(p.GET_CAPTURE_CONFIG).payload
        cfg=ui.hwcal.decode_configuration(original)
        assert cfg['enabled'] and cfg['amplitude']<=819
        baseline=worker.read_status()['counters'];report['baseline_counters']=list(baseline)
        # A guaranteed capture condition is independent of the diagnostic code.
        under=struct.pack('<BBhHhhIIHI',6,0,0,2,-100,100,1,100,16383,2)
        for ratio in (0,500000,1000000):
            worker.exchange(p.STOP)
            worker.exchange(p.SET_RECORD,struct.pack('<II',16384,ratio))
            worker.exchange(p.SET_TRIGGER,under)
            pre=(16383*ratio+500000)//1000000
            for mode in range(4):
                worker.exchange(p.STOP)
                worker.exchange(p.SET_DIAGNOSTIC,bytes([mode]))
                frame=acquire(multires_buckets=400)
                verify(frame,mode,pre,f'mode_{mode}_ratio_{ratio}')
        worker.exchange(p.STOP)
        worker.exchange(p.SET_RECORD,struct.pack('<II',16384,500000))
        worker.exchange(p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',0,0,4,2,-100,100,1,100,100,256))
        for mode in (0,1,2):
            worker.exchange(p.STOP)
            frame=acquire(acquisition_mode=mode)
            verify(frame,0,8192,f'normal_adc_capture_mode_{mode}')
        assert len({row['timestamp'] for row in report['frames']})==len(report['frames'])
        assert not any(worker.parser.errors.values())
        final=worker.read_status()['counters']
        report['error_deltas']=[(v-b)&0xffffffff for v,b in zip(final[:8],baseline[:8])]
        assert not any(report['error_deltas'])
        report['parser_errors']=worker.parser.errors.copy()
        report['verdict']='PASS'
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        try:
            if original is not None:
                worker.exchange(p.STOP)
                config=ui.hwcal.decode_configuration(original)
                ratio=(config['pre']*1000000+8191)//16383
                worker.exchange(p.SET_RECORD,struct.pack('<II',16384,ratio))
                worker.exchange(p.SET_TRIGGER,original[8:32])
                worker.exchange(p.SET_CAPTURE_MODE,original_mode)
                assert worker.exchange(p.GET_CONFIG).payload==original
                assert worker.exchange(p.GET_CAPTURE_CONFIG).payload==original_mode
                report['restored']=True
        except BaseException as exc:
            report['restore_error']=repr(exc);report['verdict']='FAIL'
        if worker.link is not None:worker.link.close()
        report['finished_at']=datetime.now().astimezone().isoformat();save()
        print('SATURATION_HARDWARE_'+report['verdict']+' '+str(out),flush=True)
    return report['verdict']!='PASS' or not report['restored']

if __name__=='__main__':raise SystemExit(main())
