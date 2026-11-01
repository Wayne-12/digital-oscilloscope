"""Actual CPU frame transfer, envelope/ROI consistency and production Qt UI."""
from pathlib import Path
import importlib.util,sys,os,time,json,struct,threading
ROOT=Path(__file__).resolve().parents[1]
os.environ['QT_QPA_PLATFORM']='offscreen'
spec=importlib.util.spec_from_file_location('cpu_physical_ui',ROOT.parent/'示波器显示界面.py')
ui=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ui;spec.loader.exec_module(ui)
np=ui.np;p=ui.proto
out=Path(os.environ.get('SCOPE_UI_TEST_REPORTS',str(ROOT/'reports/hardware/ui_multires')));out.mkdir(parents=True,exist_ok=True)
report={'result':'FAIL','transfers':[],'buckets':[],'roi':[]}
worker=ui.SerialWorker('COM12',921600)
original=mode=None
try:
 worker.open_link();assert worker.build_id==0xa4261028 and worker.capabilities==63
 worker.exchange(p.STOP);original=worker.exchange(p.GET_CONFIG).payload;mode=worker.exchange(p.GET_CAPTURE_CONFIG).payload
 worker.exchange(p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',6,0,0,2,-100,100,1,100,16383,2))
 frame=worker.capture(8);words=frame.words
 np.save(out/'full_frame.npy',words)
 for _ in range(6):
  start=time.perf_counter()
  again=worker.exchange(p.READ_WAVE,struct.pack('<II',0,16384),wave=True,record_length=16384)
  elapsed=time.perf_counter()-start
  assert again.timestamp==frame.timestamp and np.array_equal(again.words,words)
  report['transfers'].append({'seconds':elapsed,'wire_bytes':33956,'wire_bytes_per_second':33956/elapsed,
                               'uart_line_utilization':33956/elapsed/92160})
 x=2047-(words&4095).astype(np.int64)
 for count in (100,200,400,800):
  env=worker.exchange(p.READ_ENVELOPE,struct.pack('<H',count),record_length=16384,envelope_buckets=count)
  assert env.timestamp==frame.timestamp
  for i,(low,high,otr) in enumerate(env.buckets):
   a=i*16384//count;b=(i+1)*16384//count
   assert (low,high)==(int(x[a:b].min()),int(x[a:b].max()))
   assert bool(otr)==bool(np.any(words[a:b]&0x8000))
  report['buckets'].append(count)
 for start,count in ((0,1),(1000,2048),(14336,2048)):
  roi=worker.exchange(p.READ_WAVE,struct.pack('<II',start,count),wave=True,record_length=16384,overview=env)
  assert roi.timestamp==frame.timestamp+start and np.array_equal(roi.words,words[start:start+count])
  report['roi'].append([start,count])
 assert not any(worker.parser.errors.values())
 report['worker_parser_errors']=worker.parser.errors.copy()
finally:
 if original is not None:
  worker.exchange(p.STOP,restoring=True);worker.exchange(p.SET_TRIGGER,original[8:32],restoring=True)
  worker.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
  assert worker.exchange(p.GET_CONFIG,restoring=True).payload==original
 if worker.link:worker.link.close()

app=ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])
ui.configure_fonts(app)
window=ui.ScopeWindow(profile_path=out/'ui_test_profile.json')
window.resize(1600,1000);window.source.setCurrentIndex(1);window.set_running(False)
index=window.port.findData('COM12');assert index>=0
window.port.setCurrentIndex(index);window.baud.setCurrentText('921600')
window.show();window.toggle_connect()
state={'stage':'connect','deadline':time.monotonic()+20}
timer=ui.QtCore.QTimer();timer.setInterval(50)
def tick():
 try:
  if time.monotonic()>state['deadline']:raise TimeoutError(f'UI timeout at {state["stage"]}')
  if state['stage']=='connect' and window.hardware_connected and not window._commands_pending:
   assert window.device_build==0xa4261028 and window.device_capabilities==63
   window.single();state['stage']='capture'
  elif state['stage']=='capture' and window.current is not None and not window.capture_busy:
   f=window.current
   assert f.source=='硬件 UART' and len(f.words)==16384 and f.fpga_measurement
   assert window.metrics['frequency'].text()!='—'
   window.stop_capture();state['stage']='render';state['ready']=time.monotonic()+.5
  elif state['stage']=='render' and time.monotonic()>state['ready']:
   assert window.grab().save(str(out/'cpu_hardware_ui.png'))
   report['ui']={'build':hex(window.device_build),'capabilities':window.device_capabilities,
       'source':window.current.source,'samples':len(window.current.words),
       'frequency_text':window.metrics['frequency'].text(),'device_text':window.device_info.text()}
   report['result']='PASS';window.close();state['stage']='closing'
  elif state['stage']=='closing' and window.worker is None:
   timer.stop();app.quit()
 except Exception as error:
  report['error']=repr(error);timer.stop()
  if window.worker:window.worker.shutdown.set();window.worker.cancel_capture.set();window.worker.wait(4000)
  window.close();app.quit()
timer.timeout.connect(tick);timer.start();app.exec()
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(report['result']!='PASS')
