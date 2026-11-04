"""Offline layout evidence only; no serial link or external-reference measurement."""
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
spec = importlib.util.spec_from_file_location('absolute_preview_ui', ROOT/'示波器显示界面.py')
ui = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ui
spec.loader.exec_module(ui)
app = ui.QtWidgets.QApplication([])
ui.configure_fonts(app)
window = ui.ScopeWindow()
window.timer.stop()
window.set_running(False)
window.source.setCurrentIndex(1)
window.tabs.setCurrentIndex(3)
window.show()
for width, height in ((1480, 940), (1120, 760)):
    window.resize(width, height)
    app.processEvents()
    assert window.grab().save(str(OUT/f'calibration_page_{width}.png'))
dialog = ui.AbsoluteCalibrationDialog(window)
dialog.show()
app.processEvents()
assert dialog.grab().save(str(OUT/'external_reference_dialog.png'))
state = dict(source='offline-ui-layout-only', absolute_calibration_status='NOT_CALIBRATED',
             status_text=window.absolute_status.text(), profile_present=window.absolute_calibration is not None,
             apply_enabled=window.apply_absolute.isEnabled(), serial_opened=False,
             physical_accuracy_verified=False, dialog_note=dialog.status.text())
assert not state['profile_present'] and not state['apply_enabled']
(OUT/'ui_state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
dialog.close()
window.close()
