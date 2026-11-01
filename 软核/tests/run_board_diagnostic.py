"""Exercise the running C/CPU path and compare frozen analysis to actual ADC data."""
from pathlib import Path
import importlib.util
import json
import os
import struct
import sys
import time
import numpy as np

root=Path(__file__).resolve().parents[2]
out=Path(os.environ.get('SCOPE_RUNTIME_REPORTS',str(root/'软核/reports/runtime_check_20261029')))
out.mkdir(exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'
spec=importlib.util.spec_from_file_location('runtime_check_ui',root/'示波器显示界面.py')
ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
p=ui.proto
worker=ui.SerialWorker('COM12',921600)
report={'result':'FAIL','frames':[],'checks':{},'scope':'running FPGA image, original C/CPU serial path, actual ADC capture; DDS configuration unchanged'}
original=mode=None
try:
    worker.open_link()
    report['build']=hex(worker.build_id);report['capabilities']=worker.capabilities
    report['before']=worker.read_status()
    original=worker.exchange(p.GET_CONFIG).payload
    mode=worker.exchange(p.GET_CAPTURE_CONFIG).payload
    report['configuration']=ui.hwcal.decode_configuration(original)
    worker.exchange(p.STOP)
    for i in range(3):
        start=time.monotonic()
        frame=worker.capture(4,acquisition_mode=0)
        x=2047-(frame.words&4095).astype(np.int64)
        np.save(out/f'adc_frame_{i}.npy',frame.words)
        m=frame.fpga_measurement
        assert len(x)==16384 and frame.rate==25000000,'frame geometry'
        assert m['count']==len(x),'measurement count'
        assert m['minimum']==int(x.min()) and m['maximum']==int(x.max()),'min/max mismatch'
        assert m['vpp']==int(np.ptp(x)),'Vpp mismatch'
        assert m['sum']==int(x.sum()) and m['square_sum']==int((x*x).sum()),'sum/square_sum mismatch'
        rms=float(np.sqrt(np.mean(x.astype(float)**2)))
        assert abs(m['rms']-rms)<=0.51,'RMS mismatch'
        readback=worker.exchange(p.READ_WAVE,struct.pack('<II',0,16384),wave=True,record_length=16384)
        assert readback.timestamp==frame.timestamp and np.array_equal(readback.words,frame.words),'frozen record changed'
        fft=np.abs(np.fft.rfft(x[:1024]*np.hanning(1025)[:-1]))
        k=int(np.argmax(fft[1:511])+1)
        spectrum=frame.fpga_spectrum
        if np.ptp(x)>8: assert abs(k-spectrum['peak_bin'])<=1,'FFT peak differs from ADC data'
        report['frames'].append({'index':i,'seconds':time.monotonic()-start,'timestamp':frame.timestamp,
             'measurement':m,'spectrum':spectrum,'host_fft_peak_bin':k,
             'host_rms':rms,'otr_samples':int(np.count_nonzero(frame.words&0x8000))})
    assert len({f['timestamp'] for f in report['frames']})==3,'capture did not advance'
    report['checks']['three_actual_adc_records_and_exact_statistics']='PASS'
    report['checks']['frozen_frame_repeat_read']='PASS'
    report['checks']['fft_peak_against_host']='PASS'
    report['after']=worker.read_status()
    report['error_deltas']=[(a-b)&0xffffffff for a,b in zip(report['after']['counters'][:8],report['before']['counters'][:8])]
    assert not any(report['error_deltas']),'new device communication errors'
    assert not any(worker.parser.errors.values()),'host parser error'
    report['parser_errors']=worker.parser.errors.copy()
    report['result']='PASS'
except Exception as exc:
    report['error']=repr(exc)
finally:
    if original is not None:
        try:
            worker.exchange(p.STOP,restoring=True)
            worker.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
            report['configuration_preserved']=worker.exchange(p.GET_CONFIG,restoring=True).payload==original
            assert report['configuration_preserved']
        except Exception as exc:
            report['restore_error']=repr(exc);report['result']='FAIL'
    if worker.link: worker.link.close()
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else int(v)),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else int(v)))
raise SystemExit(report['result']!='PASS')
