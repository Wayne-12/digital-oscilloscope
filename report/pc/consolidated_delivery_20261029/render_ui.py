"""Offline visual QA for the consolidated UI; no serial connection or generated hardware data."""
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ['QT_QPA_PLATFORM']='offscreen'
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
spec=importlib.util.spec_from_file_location('consolidated_ui_preview',ROOT/'示波器显示界面.py')
ui=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=ui
spec.loader.exec_module(ui)
app=ui.QtWidgets.QApplication([])
ui.configure_fonts(app)
ui.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
w=ui.ScopeWindow()
w.timer.stop()
w.set_running(False)
w.source.setCurrentIndex(1)
w.port.setCurrentIndex(w.port.findData('COM12'))
w.control_tabs.setCurrentIndex(2)
w.tabs.setCurrentIndex(3)
w.show()
for width,height in ((1480,940),(1120,760)):
    w.resize(width,height)
    app.processEvents()
    assert w.grab().save(str(OUT/f'ui_output_{width}.png'))
w.control_tabs.setCurrentIndex(3)
w.open_measurement_guide()
app.processEvents()
assert w.measurement_dialog.grab().save(str(OUT/'measurement_guide.png'))
state={'source':'offline-ui-layout-only','pc_release':ui.PC_RELEASE,'serial_opened':False,
       'dds_digital_limit_hz':w.dds_freq.maximum()*1000,'dds_note':w.dds_validation_note.text(),
       'absolute_calibration_present':w.absolute_calibration is not None,
       'guide_loaded':'OTR' in w.measurement_browser.toPlainText(),
       'no_false_absolute_calibration':'未标定' in w.measurement_state.text()}
(OUT/'ui_state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
w.close()
