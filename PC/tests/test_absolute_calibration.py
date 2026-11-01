"""Synthetic external-reference fixtures. No results in this file qualify a real ADC."""
import copy
import csv
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_scope_ui import ui
import absolute_calibration as ac

np = ui.np


def frame_at(raw, timestamp):
    words = (raw+np.tile(np.array([-1, 0, 1, 0]), 4096)).astype(np.uint16)
    x = 2047-words.astype(np.int64)
    return ui.Capture(words, 25000000, 8192, timestamp, '硬件 UART', firmware_build=0xA4261027,
                      fpga_saturation={'count': 16384, 'saturated_samples': 0, 'events': 0, 'diagnostic': False},
                      fpga_measurement={'count': 16384, 'minimum': int(x.min()), 'maximum': int(x.max()),
                                            'sum': int(x.sum()), 'square_sum': int((x*x).sum()),
                                            'vpp': int(np.ptp(x)), 'period_valid': False, 'duty_valid': False,
                                            'period_q16': 0, 'duty_ppm': 0, 'frequency': 0},
                      fpga_spectrum={'clipped': False})


def metadata(reference=0, role='fit'):
    return {'reference_volts': reference, 'reference_error_volts': .0001, 'role': role,
                'device_id': 'SYNTHETIC-ADC', 'instrument': 'SYNTHETIC-METER; bounded-error fixture',
                'conditions': 'SYNTHETIC: fixed original range, 23C, stable DC', 'externally_measured': True}


def points_in(folder):
    return [ac.save_point(folder, frame_at(raw, (i+1)*100000),
                          **metadata(5.2-.0025*raw, 'fit' if i < 3 else 'check'))
            for i, raw in enumerate((2600, 2080, 1500, 2350, 1800))]


class AbsoluteCalibrationTests(unittest.TestCase):
    def test_final_display_firmware_preserves_calibration_scope(self):
        report = {'firmware_build': 0xA4261027}
        self.assertTrue(ac.firmware_matches(report, 0xAF311031))
        self.assertFalse(ac.firmware_matches(report, 0xAF311032))
        report = {'firmware_build': 0xAF311031}
        self.assertTrue(ac.firmware_matches(report, 0xA7261029))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.points = points_in(self.folder)

    def test_known_gain_offset_and_independent_error_table(self):
        report = ac.fit(self.points, self.folder, .02)
        self.assertAlmostEqual(report['slope_volts_per_raw'], -.0025, places=12)
        self.assertAlmostEqual(report['intercept_volts'], 5.2, places=12)
        self.assertEqual(report['status'], 'VERIFIED_DC_POINTS')
        self.assertIn('no AC', report['scope'])
        for point in report['verification']:
            self.assertLess(abs(point['after_error_volts']), 1e-10)
            self.assertLess(point['acceptance_bound_volts'], .02)
        raw = np.asarray([1800, 2350])
        nominal = 5-ac.SCALE*raw
        corrected = (nominal-report['display_offset'])/report['display_gain']
        np.testing.assert_allclose(corrected, 5.2-.0025*raw, atol=1e-12)

    def test_requires_independent_measured_reference_and_clean_full_frame(self):
        frame = frame_at(2080, 1)
        for changes in ({'externally_measured': False}, {'reference_error_volts': 0},
                        {'reference_volts': float('nan')}, {'instrument': ''}, {'conditions': ''}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ac.point_from_frame(frame, **{**metadata(), **changes})
        altered = (replace(frame, source='软件演示'), replace(frame, words=frame.words[:1024], trigger=512),
                   replace(frame, words=frame.words | 0x8000),
                   replace(frame, fpga_saturation={**frame.fpga_saturation, 'diagnostic': True}),
                   replace(frame, words=np.arange(16384, dtype=np.uint16) % 4096))
        for bad in altered:
            with self.subTest(), self.assertRaises(ValueError):
                ac.point_from_frame(bad, **metadata())

    def test_no_instrument_leaves_no_session_directory(self):
        out = self.folder/'should_not_exist'
        with self.assertRaises(ValueError):
            ac.save_point(out, frame_at(2080, 1), **{**metadata(), 'externally_measured': False})
        self.assertFalse(out.exists())

    def test_reference_error_and_holdout_failure_prevent_publication(self):
        for bad in (lambda points: points[-1].update(reference_volts=1.),
                    lambda points: points[0].update(reference_error_volts=.1)):
            points = copy.deepcopy(self.points)
            bad(points)
            with self.assertRaises(ValueError):
                ac.fit(points, self.folder, .02)
        with self.assertRaises(ValueError):
            ac.fit(self.points, self.folder, 1e-5)

    def test_duplicate_foreign_and_reused_fit_points_refused(self):
        mutations = (lambda points: points[-1].update(timestamp=points[0]['timestamp']),
                     lambda points: points[-1].update(device_id='other'),
                     lambda points: points[-1].update(firmware_build=123),
                     lambda points: points[-1].update(role='fit'),
                     lambda points: points[0].update(timestamp=9999999))
        for change in mutations:
            points = copy.deepcopy(self.points)
            change(points)
            with self.subTest(), self.assertRaises(ValueError):
                ac.fit(points, self.folder, .02)

    def test_hash_paths_coefficients_and_saved_pass_flags_not_trusted(self):
        report = ac.fit(self.points, self.folder, .02)
        path = self.folder/'calibration.json'
        ac.save_profile(path, report)
        self.assertEqual(ac.load_profile(path), report)
        bad = copy.deepcopy(report)
        bad['display_gain'] *= 2
        path.write_text(json.dumps(bad), encoding='utf-8')
        with self.assertRaises(ValueError):
            ac.load_profile(path)
        bad = copy.deepcopy(report)
        bad['verification'] = [{'passed': True}]
        self.assertEqual(ac.validate_profile(bad, self.folder)['verification'], report['verification'])
        bad = copy.deepcopy(report)
        bad['points'][0]['raw_file'] = '../outside.npy'
        with self.assertRaises(ValueError):
            ac.validate_profile(bad, self.folder)
        raw_path = self.folder/report['points'][0]['raw_file']
        raw_path.write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            ac.validate_profile(report, self.folder)

    def test_atomic_profile_save_preserves_previous_file(self):
        report = ac.fit(self.points, self.folder, .02)
        path = self.folder/'calibration.json'
        path.write_text('previous', encoding='utf-8')
        with patch.object(ac.os, 'replace', side_effect=PermissionError('fixture locked')):
            with self.assertRaises(PermissionError):
                ac.save_profile(path, report)
        self.assertEqual(path.read_text(), 'previous')
        self.assertFalse(list(self.folder.glob('.absolute-*')))

    def test_no_extrapolation_foreign_device_or_clipped_preview(self):
        report = ac.fit(self.points, self.folder, .02)
        frame = frame_at(2000, 800000)
        self.assertTrue(ac.applicable(report, frame, 'SYNTHETIC-ADC'))
        self.assertFalse(ac.applicable(report, frame, 'other'))
        self.assertFalse(ac.applicable(report, replace(frame, firmware_build=123), 'SYNTHETIC-ADC'))
        self.assertFalse(ac.applicable(report, frame_at(3000, 9), 'SYNTHETIC-ADC'))
        changed = replace(frame, fpga_measurement={**frame.fpga_measurement, 'minimum': -1000})
        self.assertFalse(ac.applicable(report, changed, 'SYNTHETIC-ADC'))
        changed = replace(frame, fpga_saturation={**frame.fpga_saturation, 'saturated_samples': 1})
        self.assertFalse(ac.applicable(report, changed, 'SYNTHETIC-ADC'))


class AbsoluteCalibrationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        points = points_in(self.folder)
        self.report = ac.fit(points, self.folder, .02)
        self.path = self.folder/'calibration.json'
        ac.save_profile(self.path, self.report)
        self.w = ui.ScopeWindow(profile_path=self.folder/'profile.json')
        self.w.timer.stop()
        self.w.set_running(False)

    def tearDown(self):
        self.w.worker = None
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()

    def configure_window(self):
        self.w.source.setCurrentIndex(1)
        self.w.hardware_connected = True
        self.w.worker = Mock(device_identity='SYNTHETIC-ADC')
        self.w.current = frame_at(2000, 1000000)
        self.w.device_frame_identity = self.w.current.timestamp
        self.w.install_absolute_profile(self.path)
        self.w.apply_absolute.setChecked(True)

    def test_empty_dialog_no_false_calibration_or_hardware_commands(self):
        dialog = ui.AbsoluteCalibrationDialog(self.w)
        dialog.add_point()
        dialog.publish()
        self.assertIsNone(self.w.absolute_calibration)
        self.assertIsNone(dialog.folder)
        self.assertIn('未发布', dialog.status.text())
        self.assertIn('可载入已有标定参数', self.w.absolute_status.text())
        dialog.close()
        dialog.deleteLater()

    def test_dialog_reopening_keeps_draft_for_next_dc_capture(self):
        self.configure_window()
        self.w.open_absolute_calibration()
        dialog = self.w.absolute_dialog
        self.assertFalse(dialog.isModal())
        dialog.instrument.setText('SYNTHETIC-METER specification')
        dialog.conditions.setText('SYNTHETIC DC original range')
        dialog.reference.setValue(.2)
        dialog.reference_error.setValue(.1)
        dialog.measured.setChecked(True)
        dialog.add_point()
        self.assertEqual(len(dialog.points), 1)
        dialog.accept()
        self.w.open_absolute_calibration()
        self.assertIs(self.w.absolute_dialog, dialog)
        self.assertEqual(len(dialog.points), 1)
        self.w.worker.submit.assert_not_called()

    def test_absolute_display_full_frame_moments_and_exclusive_relative(self):
        self.configure_window()
        raw = self.w.current.words.copy()
        np.testing.assert_allclose(self.w.display_volts(), 5.2-.0025*raw, atol=1e-12)
        m = self.w.current_measurement()
        expected = 5.2-.0025*raw
        self.assertAlmostEqual(m['mean'], float(np.mean(expected)))
        self.assertAlmostEqual(m['rms'], float(np.sqrt(np.mean(expected**2))))
        self.assertAlmostEqual(m['vpp'], float(np.ptp(expected)))
        np.testing.assert_array_equal(self.w.current.words, raw)
        self.assertNotIn('交流精度未验收', self.w.summary.text())
        self.w.apply_cal.setChecked(True)
        self.assertFalse(self.w.apply_absolute.isChecked())
        self.w.apply_absolute.setChecked(True)
        self.assertFalse(self.w.apply_cal.isChecked())

    def test_corrupt_load_preserves_old_profile_and_range_rejects_application(self):
        self.configure_window()
        previous = self.w.absolute_calibration
        self.path.write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.w.install_absolute_profile(self.path)
        self.assertIs(self.w.absolute_calibration, previous)
        self.w.current = frame_at(3000, 2000000)
        self.w.render_current()
        self.assertIsNone(self.w.active_display_calibration())
        self.assertIn('未应用', self.w.summary.text())
        self.w.connection_changed(False)
        self.assertFalse(self.w.apply_absolute.isChecked())

    def test_csv_and_summary_record_actual_conversion_without_changing_raw(self):
        self.configure_window()
        path = self.folder/'wave.csv'
        metadata = self.w.voltage_calibration_metadata()
        ui.CsvExportWorker(path, self.w.current, self.w.active_display_calibration(), metadata).run()
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream))
        self.assertIn('external-reference-dc', rows[0][-1])
        self.assertEqual(int(rows[2][2]), int(self.w.current.words[0]))
        self.assertAlmostEqual(float(rows[2][-1]), 5.2-.0025*self.w.current.words[0])
        report = self.w.report_measurement()
        self.assertEqual(report['voltage_calibration']['mode'], 'external-reference-dc')
        self.assertAlmostEqual(report['display_pc']['mean'], .2)
        self.w.worker.submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
