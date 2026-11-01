"""Open the current UI and connect once; SW7 handoffs are managed by the UI."""
from pathlib import Path
import importlib.util
import sys
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('latest_scope_ui',ROOT/'示波器显示界面.py')
u=importlib.util.module_from_spec(spec);sys.modules[spec.name]=u;spec.loader.exec_module(u)
app=u.QtWidgets.QApplication([]);u.configure_fonts(app)
u.pg.setConfigOptions(antialias=True,foreground='#aabbd2',background='#0c1421')
w=u.ScopeWindow();w.resize(1480,980);w.set_running(False);w.source.setCurrentIndex(1)
index=w.port.findData('COM12')
if index>=0:w.port.setCurrentIndex(index)
w.baud.setCurrentText('921600');w.show()
u.QtCore.QTimer.singleShot(100,w.toggle_connect)
sys.exit(app.exec())
