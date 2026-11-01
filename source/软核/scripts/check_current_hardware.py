"""Current integrated CPU release: real ADC, analysis, calibration and host handoff.
Never programs FPGA/Flash or changes DDS/trigger/record settings.
"""
from pathlib import Path
import importlib.util,json,os,struct,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'软核/reports/version_sync_20261030'
OUT.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
spec=importlib.util.spec_from_file_location('current_cpu_ui',ROOT/'示波器显示界面.py')
ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
p=ui.proto;worker=ui.SerialWorker('COM12',921600)
report=dict(result='FAIL',pc_release=ui.PC_RELEASE,frames=[],checks={},limitations=['No physical display available; VGA image and keys not visually revalidated','No new overvoltage or long-duration qualification'])
original=mode=None
try:
 worker.open_link();report.update(build=hex(worker.build_id),capabilities=worker.capabilities,device_id=worker.device_identity)
 assert worker.build_id==0xA7261029 and worker.capabilities==63,'unexpected integrated CPU release'
 original=worker.exchange(p.GET_CONFIG).payload;mode=worker.exchange(p.GET_CAPTURE_CONFIG).payload
 report['before']=worker.read_status()
 profile=ui.abscal.load_profile(ROOT/'校正参数.json')
 assert ui.abscal.firmware_matches(profile,worker.build_id)
 for i in range(3):
  frame=worker.capture(5,acquisition_mode=0)
  raw=(frame.words&4095).astype(np.int64);x=2047-raw;m=frame.fpga_measurement
  assert len(raw)==16384 and frame.rate==25000000
  assert m['count']==len(x) and m['minimum']==int(x.min()) and m['maximum']==int(x.max())
  assert m['sum']==int(x.sum()) and m['square_sum']==int((x*x).sum()) and m['vpp']==int(np.ptp(x))
  assert abs(m['rms']-np.sqrt(np.mean(x.astype(float)**2)))<=.51
  repeat=worker.exchange(p.READ_WAVE,struct.pack('<II',0,16384),wave=True,record_length=16384)
  assert repeat.timestamp==frame.timestamp and np.array_equal(repeat.words,frame.words)
  envelope=worker.exchange(p.READ_ENVELOPE,struct.pack('<H',800),record_length=16384,envelope_buckets=800)
  assert envelope.timestamp==frame.timestamp and envelope.length==16384
  roi=worker.exchange(p.READ_WAVE,struct.pack('<II',7000,1024),wave=True,record_length=16384,overview=envelope)
  assert np.array_equal(roi.words,frame.words[7000:8024]),'ROI differs from frozen full frame'
  fft=np.abs(np.fft.rfft(x[:1024]*np.hanning(1025)[:-1]))
  peak=int(np.argmax(fft[1:511])+1)
  if np.ptp(x)>8:assert abs(peak-frame.fpga_spectrum['peak_bin'])<=1,'FFT peak mismatch'
  corrected=profile['slope_volts_per_raw']*raw+profile['intercept_volts']
  applicable=ui.abscal.applicable(profile,frame,worker.device_identity)
  np.save(OUT/f'frame_{i}.npy',frame.words,allow_pickle=False)
  report['frames'].append(dict(timestamp=frame.timestamp,mean_raw=float(raw.mean()),vpp_codes=int(np.ptp(x)),
   nominal_mean_volts=float(frame.volts().mean()),correction_applicable=applicable,
   calibrated_mean_volts=float(corrected.mean()) if applicable else None,
   calibrated_rms_volts=float(np.sqrt(np.mean(corrected**2))) if applicable else None,
   otr_samples=int(np.count_nonzero(frame.words&0x8000))))
 assert len({r['timestamp'] for r in report['frames']})==3
 report['checks'].update(three_real_frames='PASS',exact_measurement_moments='PASS',frozen_repeat='PASS',envelope_identity='PASS',roi='PASS',fft_peak='PASS',calibration_profile='PASS')
 report['after']=worker.read_status()
 assert not any((a-b)&0xffffffff for a,b in zip(report['after']['counters'][:8],report['before']['counters'][:8]))
 assert not any(worker.parser.errors.values())
 report['checks']['communication']='PASS';report['result']='PASS'
except Exception as exc:report['error']=repr(exc)
finally:
 if original is not None:
  try:
   worker.exchange(p.STOP,restoring=True)
   worker.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
   assert worker.exchange(p.GET_CONFIG,restoring=True).payload==original
   report['configuration_preserved']=True
  except Exception as exc:report.update(result='FAIL',restore_error=repr(exc))
 if worker.link:worker.link.close()
 (OUT/'hardware.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2,default=str))
raise SystemExit(report['result']!='PASS')
