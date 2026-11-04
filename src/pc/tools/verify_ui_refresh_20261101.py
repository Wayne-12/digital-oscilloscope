"""Live UI review; leaves the verified window open for the user."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'pc/reports'/os.environ.get('SCOPE_UI_REVIEW_DIR','ui_refresh_20261101');OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('refreshed_scope_ui',ROOT/'scope_ui.py')
u=importlib.util.module_from_spec(spec);sys.modules[spec.name]=u;spec.loader.exec_module(u)
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
u.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
w=u.ScopeWindow(profile_path=OUT/'review_profile.json')
w.install_absolute_profile(ROOT/'voltage_calibration.json')
w.resize(1480,980);w.set_running(False);w.source.setCurrentIndex(1)
w.port.setCurrentIndex(w.port.findData('COM12'));w.baud.setCurrentText('921600');w.show()
report={'result':'FAIL','release':u.PC_RELEASE}
def wait(predicate,timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError(w.logs.toPlainText())
def shot(name):
    for _ in range(10):app.processEvents()
    assert w.grab().save(str(OUT/(name+'.png')))
try:
    w.toggle_connect();wait(lambda:w.hardware_connected and not w._commands_pending)
    w.set_running(True);wait(lambda:w.capture_count>=2)
    report['before']={'timebase':w.timebase.currentText(),'vertical':w.volts_div.currentText()}
    raw=w.current.words.copy();frame=w.current
    w.autoscale()
    wait(lambda:w.running and not getattr(w,'_autoscale_pending',False) and not w._commands_pending)
    wait(lambda:w.current is not frame)
    w.stop_capture();wait(lambda:not w.capture_busy and not w._commands_pending)
    u.np.testing.assert_array_equal(frame.words,raw)
    report['after']={'timebase':w.timebase.currentText(),'vertical':w.volts_div.currentText(),
                     'center':w.display_center.value(),'frequency':w.metrics['frequency'].text(),
                     'vpp':w.metrics['vpp'].text()}
    shot('waveform_autoscale')
    w.tabs.setCurrentIndex(1);shot('fft_spacing')
    assert '<table' in w.fft_info.text() and 'H5' in w.fft_info.text()
    report['fft_label_width']=w.fft_info.width()
    w.tabs.setCurrentIndex(3);shot('closed_loop_clean')
    assert w.cal_note.isHidden()
    assert not any('实物测量与验收说明' in b.text() for b in w.findChildren(u.QtWidgets.QPushButton))
    w.tabs.setCurrentIndex(0);w.control_tabs.setCurrentIndex(3);shot('tools_cursor_options')
    assert w.cursor_time.objectName()==w.cursor_volt.objectName()=='cursorOption'
    if hasattr(w,'header_capture'):
        w.update_header_status()
        assert w.device_info.isHidden()
        assert w.header_capture.text()=='波形已暂停'
        assert w.header_rate.text()=='采样率 25 MSPS'
        assert w.header_record.text()=='记录长度 16 K 点'
        report['header']={'title':w.header_title.text(),'rate':w.header_rate.text(),'record':w.header_record.text()}
    w.cursor_time.setChecked(True);w.cursor_volt.setChecked(True)
    assert 'Δt' in w.cursor_readout.text() and 'ΔV' in w.cursor_readout.text()
    w.cursor_time.setChecked(False);w.cursor_volt.setChecked(False)
    w.control_tabs.setCurrentIndex(0)
    report.update(result='PASS',parser_errors=w.worker.parser.errors.copy(),build=hex(w.device_build))
    w.set_running(True)
except Exception as exc:
    report.update(error=repr(exc),traceback=traceback.format_exc())
    if w.worker:w.worker.shutdown.set();w.worker.cancel_capture.set();w.worker.wait(10000)
    w.close()
finally:
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if report['result']=='PASS':sys.exit(app.exec())
sys.exit(1)
