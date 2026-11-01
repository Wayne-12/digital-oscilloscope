"""User-requested doubled-amplitude self-test, with isolated UI state."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[2]
factor=int(os.environ.get('SCOPE_SELFTEST_FACTOR','2'))
assert factor in (1,2)
OUT=ROOT/'PC/reports/final_acceptance_20261101'/os.environ.get('SCOPE_SELFTEST_VARIANT','amplitude_x2')
OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('amplitude_retry_ui',ROOT/'示波器显示界面.py')
u=importlib.util.module_from_spec(spec);sys.modules[spec.name]=u;spec.loader.exec_module(u)
u.hwcal.MAX_TEST_CODE=819*factor
u.hwcal.DC_CODES=tuple(factor*x for x in u.hwcal.DC_CODES)
u.hwcal.AMPLITUDES=tuple(factor*x for x in u.hwcal.AMPLITUDES)
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
w=u.ScopeWindow(profile_path=OUT/'profile.json')
report={'result':'FAIL','digital_peak_before':819,'digital_peak_test':819*factor,'dc_codes':u.hwcal.DC_CODES,'amplitudes':u.hwcal.AMPLITUDES}
original_exchange=u.SerialWorker.exchange
def traced(self,kind,payload=b'',*args,**kwargs):
    try:return original_exchange(self,kind,payload,*args,**kwargs)
    except Exception as exc:
        report['failed_command']={'kind':hex(kind),'payload':payload.hex(),'error':repr(exc)}
        raise
u.SerialWorker.exchange=traced
def wait(predicate,seconds=30):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError(w.logs.toPlainText())
try:
    w.set_running(False);w.source.setCurrentIndex(1)
    w.port.setCurrentIndex(w.port.findData('COM12'));w.baud.setCurrentText('921600')
    w.resize(1600,1000);w.show();w.toggle_connect()
    wait(lambda:w.hardware_connected and not w._commands_pending)
    w.start_hardware_calibration();wait(lambda:w.hardware_calibration_busy)
    wait(lambda:not w.hardware_calibration_busy,180)
    report.update(result='PASS' if w.hardware_calibration_valid else 'FAIL',selftest=w.hardware_calibration,text=w.cal_result.text())
    w.grab().save(str(OUT/'ui_selftest.png'))
    w.toggle_connect();wait(lambda:w.worker is None)
    w.toggle_connect();wait(lambda:w.hardware_connected and not w._commands_pending)
    report['reconnect']='PASS'
except Exception as exc:report.update(result='FAIL',error=repr(exc),traceback=traceback.format_exc())
finally:
    report['ui_log']=w.logs.toPlainText()
    if w.worker is not None:
        w.worker.shutdown.set();w.worker.cancel_capture.set();w.worker.wait(10000);app.processEvents()
    w.close();app.processEvents()
    link=u.SerialWorker('COM12',921600)
    try:
        link.open_link();p=u.proto
        baseline=json.loads((OUT.parent/'baseline.json').read_text())['before']
        cfg=bytes.fromhex(baseline['config'])
        link.exchange(p.STOP,restoring=True)
        link.exchange(p.SET_TRIGGER,cfg[8:32],restoring=True)
        link.exchange(p.SET_DDS,cfg[32:48],restoring=True)
        link.exchange(p.SET_CAPTURE_MODE,bytes.fromhex(baseline['capture_config']),restoring=True)
        report['restored']=link.exchange(p.GET_CONFIG,restoring=True).payload==cfg
        report['final_status']=link.read_status()
    except Exception as exc:report.update(restore_error=repr(exc),result='FAIL')
    finally:
        if link.link:link.link.close()
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2,default=str),flush=True)
sys.exit(report['result']!='PASS')
