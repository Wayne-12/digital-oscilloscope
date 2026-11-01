"""Read-only measurement guide and explicit PC/FPGA version scopes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from test_scope_ui import ui


class MeasurementGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp')
        self.addCleanup(self.temp.cleanup)
        self.window=ui.ScopeWindow(profile_path=Path(self.temp.name)/'profile.json')
        self.window.timer.stop()
        self.window.set_running(False)

    def tearDown(self):
        self.window.worker=None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_guide_shows_resolved_status_and_sends_no_commands(self):
        w=self.window
        w.worker=Mock()
        w.open_measurement_guide()
        self.assertTrue(w.measurement_browser.isReadOnly())
        self.assertEqual(w.absolute_button.text(), '载入电压校正参数…')
        text=w.measurement_browser.toPlainText()
        for phrase in ('OTR','真实模拟过载验收：已完成','老师帮助','12.5 MHz','载入电压校正参数','真正断电'):
            self.assertIn(phrase,text)
        self.assertEqual(w.overload_acceptance_label.text(), ui.OVERLOAD_ACCEPTANCE)
        self.assertIn('2026-10-30', w.overload_acceptance_label.toolTip())
        self.assertIn(ui.OVERLOAD_ACCEPTANCE, w.measurement_state.text())
        self.assertIn(w.absolute_status.text(), w.measurement_state.text())
        for phrase in ('NOT_CALIBRATED', 'INCOMPLETE', '未标定', '待验收'):
            self.assertNotIn(phrase, text)
        self.assertIn(ui.PC_RELEASE,w.measurement_state.text())
        self.assertIn(ui.PC_RELEASE,w.windowTitle())
        self.assertEqual(w.dds_freq.maximum(),12500)
        w.worker.submit.assert_not_called()

    def test_guide_reopens_with_current_device_identity_and_keeps_scope_note_visible(self):
        w=self.window
        w.open_measurement_guide()
        original=w.measurement_dialog
        original.accept()
        w.hardware_connected=True
        w.device_build=0xA4261027
        w.open_measurement_guide()
        self.assertIs(w.measurement_dialog,original)
        self.assertIn('0xA4261027',w.measurement_state.text())
        self.assertIn('已测频点',w.dds_validation_note.text())
        self.assertIn('8 MHz',w.dds_validation_note.text())


if __name__=='__main__':
    unittest.main()
