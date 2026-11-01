"""Load and verify a visibly distinct five-level staircase, leave demo running."""
from pathlib import Path
import importlib.util
import json
import struct
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'PC/reports/demo_awg_20261101';OUT.mkdir(parents=True,exist_ok=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
u=module('demo_staircase_ui',ROOT/'示波器显示界面.py')
reference=module('demo_staircase_fit',ROOT/'FPGA/scripts/verify_awg_hardware.py')
p,awg,np=u.proto,u.awg,u.np
table=awg.load_table(ROOT/'任意波形.csv')
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
u.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
report={'result':'FAIL','file':str(ROOT/'任意波形.csv'),'levels':[-1,-.5,0,.5,1,.5,0,-.5],
        'points_per_step':128,'frequency_hz':10000,'digital_amplitude_percent':20}
original=mode=old_table=old_awg=None;w=None
link=u.SerialWorker('COM12',921600)
def wait(predicate,seconds=25):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError(w.logs.toPlainText() if w else 'deadline')
try:
    link.open_link();link.exchange(p.STOP)
    original=link.exchange(p.GET_CONFIG).payload;mode=link.exchange(p.GET_CAPTURE_CONFIG).payload
    old_awg=awg.status(link)
    if old_awg['valid']:old_table=awg.read_table(link)
    (OUT/'before.json').write_text(json.dumps({'config':original.hex(),'mode':mode.hex(),'awg':old_awg,'table':old_table},indent=2),encoding='utf-8')
    before=link.read_status()['counters'];link.link.close()
    w=u.ScopeWindow(profile_path=OUT/'demo_profile.json');w.install_absolute_profile(ROOT/'校正参数.json')
    w.resize(1480,980);w.set_running(False);w.source.setCurrentIndex(1)
    w.port.setCurrentIndex(w.port.findData('COM12'));w.baud.setCurrentText('921600')
    w.show();w.toggle_connect();wait(lambda:w.hardware_connected and not w._commands_pending)
    chooser=u.QtWidgets.QFileDialog.getOpenFileName
    try:
        u.QtWidgets.QFileDialog.getOpenFileName=lambda *args,**kwargs:(str(ROOT/'任意波形.csv'),'CSV (*.csv)')
        w.download_awg()
    finally:u.QtWidgets.QFileDialog.getOpenFileName=chooser
    wait(lambda:not w._commands_pending);assert '已校验' in w.awg_label.text()
    w.dds_wave.setCurrentIndex(4);w.dds_enable.setChecked(True);w.dds_freq.setValue(10)
    w.dds_amplitude.setValue(20);w.dds_offset.setValue(0);w.dds_phase.setValue(0)
    w.apply_dds();wait(lambda:not w._commands_pending)
    w.trigger_type.setCurrentIndex(0);w.threshold.setValue(0);w.hysteresis.setValue(8*u.SCALE)
    w.apply_trigger();wait(lambda:not w._commands_pending)
    w.acquisition_mode.setCurrentIndex(0);w.set_running(True)
    wait(lambda:w.current is not None and w.current.source=='硬件 UART')
    w.autoscale();wait(lambda:w.running and not getattr(w,'_autoscale_pending',False) and not w._commands_pending)
    frame=w.current;wait(lambda:w.current is not frame)
    w.stop_capture();wait(lambda:not w.capture_busy and not w._commands_pending)
    frame=w.current
    fit=reference.fit_table(frame.words,table,10000)
    assert fit['correlation']>.95 and fit['normalized_rms_error']<.3,fit
    assert frame.fpga_measurement['period_valid'] and abs(frame.fpga_measurement['frequency']-10000)<100
    assert not np.any(frame.words&0x8000) and frame.fpga_saturation['saturated_samples']==0
    np.save(OUT/'demo_adc.npy',frame.words,allow_pickle=False)
    w.control_tabs.setCurrentIndex(2);app.processEvents()
    assert w.grab().save(str(OUT/'现场演示.png'))
    report.update(shape_fit=fit,measurement=frame.fpga_measurement,saturation=frame.fpga_saturation,
                  ui_awg_text=w.awg_label.text(),timebase=w.timebase.currentText(),vertical=w.volts_div.currentText())
    w.toggle_connect();wait(lambda:w.worker is None)
    link=u.SerialWorker('COM12',921600);link.open_link()
    assert awg.read_table(link)==table
    state=awg.status(link);assert state['valid'] and state['selected']
    after=link.read_status()['counters'];assert after[:8]==before[:8]
    assert not any(link.parser.errors.values())
    report.update(result='PASS',table_crc=f"{state['active_crc']:04X}",table_exact_readback=True,
                  counters_before=before,counters_after=after,parser_errors=link.parser.errors.copy())
    link.link.close()
except Exception as exc:
    report.update(error=repr(exc),traceback=traceback.format_exc())
    try:
        if w and w.worker:
            w.worker.shutdown.set();w.worker.cancel_capture.set();w.worker.wait(10000);app.processEvents()
        if link.link and link.link.is_open:link.link.close()
        if original is not None:
            link=u.SerialWorker('COM12',921600);link.open_link();link.exchange(p.STOP)
            disabled=bytearray(original[32:48]);disabled[1]=0;link.exchange(p.SET_DDS,bytes(disabled),restoring=True)
            if old_table is not None:awg.upload(link,old_table)
            awg.ack(link,awg.SELECT,bytes([int(old_awg['selected'])]),restoring=True)
            link.exchange(p.SET_TRIGGER,original[8:32],restoring=True)
            link.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
            link.exchange(p.SET_DDS,original[32:48],restoring=True)
            assert link.exchange(p.GET_CONFIG).payload==original
            link.link.close();report['failure_restored']=True
    except Exception as restore_exc:report['restore_error']=repr(restore_exc)
finally:
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if report['result']=='PASS':
    w.toggle_connect();wait(lambda:w.hardware_connected and not w._commands_pending)
    w.dds_wave.setCurrentIndex(4)
    w.set_running(True);w.log('现场演示：五电平阶梯波 · 10 kHz · 20%数字幅度')
    sys.exit(app.exec())
if w:w.close()
sys.exit(1)
