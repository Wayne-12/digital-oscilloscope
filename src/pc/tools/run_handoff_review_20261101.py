"""Observe real switch handoffs without injecting switch or key events."""
from pathlib import Path
import importlib.util
import json
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'pc/reports/control_handoff_20261101';OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('handoff_review_ui',ROOT/'scope_ui.py')
u=importlib.util.module_from_spec(spec);sys.modules[spec.name]=u;spec.loader.exec_module(u)
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
u.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
w=u.ScopeWindow(profile_path=OUT/'ui_profile.json');w.install_absolute_profile(ROOT/'voltage_calibration.json')
w.resize(1480,980);w.set_running(False);w.source.setCurrentIndex(1)
w.port.setCurrentIndex(w.port.findData('COM12'));w.baud.setCurrentText('921600')
report={'started':time.time(),'events':[],'snapshots':[]};started=time.monotonic()
def save():
    report.update(current={'connected':w.hardware_connected,'local_control':w._local_control,
        'running':w.running,'frames':w.capture_count,'state':w.state_label.text(),
        'footer':w.footer.text(),'logs':w.logs.toPlainText()})
    target=OUT/'review.json';tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(target)
def event(name):
    report['events'].append({'seconds':time.monotonic()-started,'event':name,
        'frames':w.capture_count,'dds_hz':w.dds_freq.value()*1000,
        'threshold_v':w.threshold.value(),'mode':w.acquisition_mode.currentIndex()})
    save()
old_local=w.handle_local_control
def local():
    changed=not w._local_control;old_local();w._handoff_resume=True
    if changed:event('LOCAL_CONTROL')
w.handle_local_control=local
old_connected=w.connection_changed
def connected(value):
    old_connected(value)
    if value:event('PC_CONNECTED')
w.connection_changed=connected
last_frames=0
def tick():
    global last_frames
    if w.current is not None and w.current.source=='硬件 UART' and w.capture_count>=last_frames+10:
        last_frames=w.capture_count
        report['snapshots'].append({'seconds':time.monotonic()-started,'frames':w.capture_count,
                                   'parser_errors':w.worker.parser.errors.copy() if w.worker else {}})
    save()
timer=u.QtCore.QTimer();timer.setInterval(500);timer.timeout.connect(tick);timer.start()
w.show();w.toggle_connect()
sys.exit(app.exec())
