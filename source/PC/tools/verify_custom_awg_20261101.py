"""Verify the user's CSV on the real DAC/ADC and production GUI."""
from pathlib import Path
import importlib.util
import json
import struct
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'PC/reports/custom_awg_20261101';OUT.mkdir(parents=True,exist_ok=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
    return value
u=module('custom_awg_ui',ROOT/'示波器显示界面.py')
reference=module('custom_awg_reference',ROOT/'FPGA/scripts/verify_awg_hardware.py')
p,awg,np=u.proto,u.awg,u.np
table=awg.load_table(ROOT/'任意波形.csv')
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
u.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
report={'result':'FAIL','file':str(ROOT/'任意波形.csv'),'points':len(table),
        'formula':'normalize(sin(theta)+0.35*sin(2*theta)+0.20*sin(3*theta))',
        'frames':[],'checks':{}}
link=u.SerialWorker('COM12',921600);w=None
original=mode=before_awg=old_table=None
def dds(enabled,frequency=100000,amplitude=819):
    awg.ack(link,p.SET_DDS,struct.pack('<BBIIHi',0,enabled,frequency,0,amplitude,0))
def wait(predicate,seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError(w.logs.toPlainText() if w else 'deadline')
def disconnect():
    if w and w.worker:
        w.toggle_connect();wait(lambda:w.worker is None)
try:
    link.open_link();assert link.capabilities&awg.CAPABILITY
    report['build']=hex(link.build_id)
    link.exchange(p.STOP)
    original=link.exchange(p.GET_CONFIG).payload
    mode=link.exchange(p.GET_CAPTURE_CONFIG).payload
    before_awg=awg.status(link)
    if before_awg['valid']:
        old_table=awg.read_table(link)
        (OUT/'original_table.json').write_text(json.dumps(old_table),encoding='utf-8')
    report['before_awg']=before_awg
    before=link.read_status()['counters']
    dds(0)
    uploaded=awg.upload(link,table)
    assert awg.read_table(link)==table
    report['table_crc']=f"{uploaded['active_crc']:04X}"
    report['checks']['upload_crc_exact_1024_point_readback']='PASS'
    awg.ack(link,awg.SELECT,b'\1')
    link.exchange(p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',6,0,0,8,-2048,2047,1,1,16383,2))
    report['measurement_hysteresis_codes']=8
    for frequency,amplitude in ((10000,819),(100000,819),(500000,819),(100000,1638)):
        link.exchange(p.STOP)
        dds(1,frequency,amplitude)
        time.sleep(.08)
        frame=link.capture(8,acquisition_mode=0)
        assert len(frame.words)==16384 and frame.rate==25000000
        assert not np.any(frame.words&0x8000)
        assert frame.fpga_saturation['saturated_samples']==frame.fpga_saturation['events']==0
        fit=reference.fit_table(frame.words,table,frequency)
        assert fit['adc_vpp']>=8 and fit['correlation']>.96 and fit['normalized_rms_error']<.28,fit
        assert frame.fpga_measurement['period_valid'] and abs(frame.fpga_measurement['frequency']/frequency-1)<.01,frame.fpga_measurement
        np.save(OUT/f'awg_{frequency}_{amplitude}.npy',frame.words,allow_pickle=False)
        report['frames'].append({'frequency_set_hz':frequency,'amplitude_code':amplitude,
            'fit':fit,'measurement':frame.fpga_measurement,'saturation':frame.fpga_saturation})
    ratio=report['frames'][3]['fit']['adc_vpp']/report['frames'][1]['fit']['adc_vpp']
    assert 1.8<ratio<2.2,ratio
    report['amplitude_double_ratio']=ratio
    report['checks']['three_frequencies_real_analog_shape_and_amplitude']='PASS'
    after=link.read_status()['counters'];assert after[:8]==before[:8]
    assert not any(link.parser.errors.values())
    report['counter_before'],report['counter_after']=before,after
    link.exchange(p.STOP);dds(0)
    link.link.close()

    w=u.ScopeWindow(profile_path=OUT/'ui_profile.json');w.install_absolute_profile(ROOT/'校正参数.json')
    w.resize(1480,980);w.set_running(False);w.source.setCurrentIndex(1)
    w.port.setCurrentIndex(w.port.findData('COM12'));w.baud.setCurrentText('921600')
    w.show();w.toggle_connect();wait(lambda:w.hardware_connected and not w._commands_pending)
    chooser=u.QtWidgets.QFileDialog.getOpenFileName
    try:
        u.QtWidgets.QFileDialog.getOpenFileName=lambda *args,**kwargs:(str(ROOT/'任意波形.csv'),'CSV (*.csv)')
        w.download_awg()
    finally:u.QtWidgets.QFileDialog.getOpenFileName=chooser
    wait(lambda:not w._commands_pending)
    assert '已校验' in w.awg_label.text()
    w.dds_wave.setCurrentIndex(4);w.dds_enable.setChecked(True)
    w.dds_freq.setValue(100);w.dds_amplitude.setValue(20);w.dds_offset.setValue(0);w.dds_phase.setValue(0)
    w.apply_dds();wait(lambda:not w._commands_pending)
    assert '已选择' in w.awg_label.text()
    w.trigger_type.setCurrentIndex(0);w.threshold.setValue(0);w.hysteresis.setValue(2*u.SCALE)
    w.apply_trigger();wait(lambda:not w._commands_pending)
    w.acquisition_mode.setCurrentIndex(0);w.set_running(True)
    wait(lambda:w.current is not None and w.current.source=='硬件 UART')
    w.autoscale();wait(lambda:w.running and not getattr(w,'_autoscale_pending',False) and not w._commands_pending)
    w.stop_capture();wait(lambda:not w.capture_busy and not w._commands_pending)
    gui_fit=reference.fit_table(w.current.words,table,100000)
    assert gui_fit['correlation']>.96 and gui_fit['normalized_rms_error']<.28,gui_fit
    w.control_tabs.setCurrentIndex(2);app.processEvents()
    assert w.grab().save(str(OUT/'ui_custom_awg.png'))
    report['ui_fit']=gui_fit
    report['checks']['ui_load_select_apply_adc_autoscale']='PASS'
    report['ui_awg_text']=w.awg_label.text()
    report['result']='PASS'
except Exception as exc:report.update(error=repr(exc),traceback=traceback.format_exc())
finally:
    try:
        disconnect()
        if link.link and link.link.is_open:link.link.close()
        if original is not None:
            link=u.SerialWorker('COM12',921600);link.open_link();link.exchange(p.STOP)
            disabled=bytearray(original[32:48]);disabled[1]=0
            link.exchange(p.SET_DDS,bytes(disabled),restoring=True)
            if old_table is not None:awg.upload(link,old_table)
            awg.ack(link,awg.SELECT,bytes([int(before_awg['selected'])]),restoring=True)
            link.exchange(p.SET_TRIGGER,original[8:32],restoring=True)
            link.exchange(p.SET_CAPTURE_MODE,mode,restoring=True)
            link.exchange(p.SET_DDS,original[32:48],restoring=True)
            assert link.exchange(p.GET_CONFIG,restoring=True).payload==original
            assert link.exchange(p.GET_CAPTURE_CONFIG,restoring=True).payload==mode
            if old_table is not None:assert awg.read_table(link)==old_table
            report['restored']=True
            report['after_awg']=awg.status(link)
            report['final_status']=link.read_status()
            report['remaining_table']='Original valid table restored' if old_table is not None else 'New custom table remains in volatile RAM, unselected; CSV is persistent on PC'
            link.link.close()
    except Exception as exc:report.update(result='FAIL',restore_error=repr(exc))
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if report['result']=='PASS' and w is not None:
    w._hardware_profile.clear()
    kind,_,threshold,hysteresis,low,high,wmin,wmax,amplitude,observation=struct.unpack('<BBhHhhIIHI',original[8:32])
    w.trigger_type.setCurrentIndex(kind);w.threshold.setValue((threshold+.5)*u.SCALE)
    w.hysteresis.setValue(hysteresis*u.SCALE)
    w.win_low.setValue((low+.5)*u.SCALE);w.win_high.setValue((high+.5)*u.SCALE)
    w.width_min.setValue(wmin/25);w.width_max.setValue(wmax/25)
    w.amp_limit.setValue(amplitude*u.SCALE);w.observation.setValue(observation)
    w.toggle_connect();wait(lambda:w.hardware_connected and not w._commands_pending)
    w.control_tabs.setCurrentIndex(0);w.tabs.setCurrentIndex(0)
    w.log('任意波形.csv 实物测试通过；已恢复原输出设置。')
    w.set_running(True)
    sys.exit(app.exec())
if w:w.close()
sys.exit(1)
