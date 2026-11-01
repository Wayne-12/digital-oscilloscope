"""Synthetic fixtures for survey gates and recovery. Not physical frequency evidence."""
import copy
import math
from pathlib import Path
import struct
import tempfile
import unittest

from test_scope_ui import ui
from test_analog_acceptance import AnalogFixture
import dds_sweep as ds

np = ui.np


def tone(frequency, wave=0, phase=0, amplitude=80):
    angle = 2*np.pi*frequency*np.arange(ds.N)/ds.RATE+math.radians(phase)
    normalized = (np.sin(angle) if wave == 0 else np.where(np.sin(angle) >= 0, 1., -1.)
                  if wave == 1 else 2/np.pi*np.arcsin(np.sin(angle)))
    return np.rint(2047-amplitude*normalized).astype(np.uint16)


class SweepFixture(AnalogFixture):
    port = 'SYNTHETIC-TEST-ONLY'

    def capture(self, timeout):
        self.count += 1
        if self.count == self.fail_at:
            raise TimeoutError('SYNTHETIC timeout')
        if self.count == self.cancel_at:
            self.cancel_capture.set()
            raise InterruptedError('SYNTHETIC cancellation')
        wave, enabled, frequency, phase, peak, offset = struct.unpack('<BBIIHi', self.dds)
        if not enabled:
            raise AssertionError('Capture must follow explicit enable')
        if not (peak == 819 and offset == 0):
            raise AssertionError('Survey may not increase amplitude or offset')
        words = tone(frequency, wave, phase*360/2**32)
        x = 2047-words.astype(np.int64)
        self.frame = ui.Capture(words, ds.RATE, self.pre, self.count*1000000, '硬件 UART',
            firmware_build=self.build_id,
            fpga_saturation={'count':ds.N, 'saturated_samples':0, 'events':0, 'diagnostic':False},
            fpga_measurement={'stats_valid':True, 'error':False, 'count':ds.N, 'minimum':int(x.min()),
                              'maximum':int(x.max()), 'sum':int(x.sum()), 'square_sum':int((x*x).sum())},
            fpga_spectrum={'clipped':False})
        return self.frame


class SweepTests(unittest.TestCase):
    def test_sine_known_frequency_and_amplitude(self):
        for frequency in (10000, 100000, 1000000, 5000000, 12490000):
            for phase in (0, 90):
                with self.subTest(frequency=frequency, phase=phase):
                    a = ds.analyze(tone(frequency, phase=phase), frequency, 0)
                    self.assertTrue(a['basic_pass'])
                    # Integer ADC quantization can bias a five-sample cycle;
                    # allow half of one raw ADC code in the recovered peak.
                    self.assertAlmostEqual(a['fitted_peak_adc_codes'], 80, delta=.5)
                    self.assertLess(a['fundamental_residual_ratio'], .01)
                    self.assertLessEqual(a['fft_peak_error_hz'], ds.RATE/ds.N)

    def test_low_and_nyquist_observations_cannot_qualify(self):
        for frequency, status in ((0,'DC_BOUNDARY_OBSERVATION'), (1,'INSUFFICIENT_RECORD_CYCLES'),
                                  (1000,'INSUFFICIENT_RECORD_CYCLES'),
                                  (12499000,'INSUFFICIENT_RECORD_CYCLES'),
                                  (12500000,'NYQUIST_BOUNDARY_ONLY')):
            a = ds.analyze(tone(frequency), frequency, 0)
            self.assertFalse(a['basic_pass'])
            self.assertEqual(a['status'], status)

    def test_missing_wrong_frequency_distortion_and_overload_refused(self):
        for words in (np.full(ds.N, 2047, dtype=np.uint16), tone(500000), tone(100000, wave=1)):
            self.assertFalse(ds.analyze(words, 100000, 0)['basic_pass'])
        for word in (0, 4095, 0x8001):
            words = tone(100000)
            words[777] = word
            with self.assertRaises(ValueError):
                ds.analyze(words, 100000, 0)

    def test_square_and_triangle_have_separate_criteria(self):
        for wave in (1, 2):
            a = ds.analyze(tone(100000, wave), 100000, wave)
            self.assertTrue(a['basic_pass'])
            self.assertIn('shape quality not qualified', a['criterion'])
            self.assertIn('in_band_h2_h5_ratios_not_thd', a)
        self.assertNotIn('in_band_h2_h5_ratios_not_thd', ds.analyze(tone(5000000),5000000,0))

    def test_limit_and_small_stimulus_remain_unchanged(self):
        self.assertEqual(ds.actual_frequency(12500000), 12500000)
        with self.assertRaises(ValueError):
            ds.stimulus(0, 12500001)
        for wave, frequency, phase in ds.plan():
            values = struct.unpack('<BBIIHi', ds.stimulus(wave,frequency,phase))
            self.assertEqual((values[4], values[5]), (819,0))
        self.assertIn((0,12500000,0), ds.plan())
        self.assertIn((0,12500000,90), ds.plan())

    def run_fixture(self, device, cases):
        before, mode = device.config(), device.mode
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            report = ds.run(device, Path(folder)/'survey', cases=cases, settle_seconds=0,
                            progress=lambda message:None)
            if report['restored']:
                self.assertEqual((device.config(), device.mode), (before,mode))
            for row in report['frames']:
                self.assertEqual(len(np.load(Path(folder)/'survey'/row['file'])),ds.N)
            return report

    def test_completed_survey_distinguishes_passed_points_and_observations(self):
        cases=((0,10000,0),(0,100000,0),(0,5000000,0),(0,5000000,90),
               (0,12500000,0),(0,12500000,90),(1,100000,0),(2,100000,0))
        r = self.run_fixture(SweepFixture(), cases)
        self.assertEqual(r['verdict'],'SURVEY_COMPLETE',r.get('error'))
        self.assertTrue(r['restored'])
        self.assertEqual(r['digital_limit_hz'],12500000)
        self.assertFalse(r['independent_dac_quality_qualified'])
        self.assertEqual(r['summary']['sine']['passed_discrete_hz'],[10000,100000,5000000])
        self.assertEqual(r['summary']['sine']['observation_only_hz'],[12500000])
        entries=copy.deepcopy(r['frames'])
        target=next(row for row in entries if row['frequency_hz']==5000000)
        target['analysis']['fitted_peak_adc_codes']*=2
        self.assertIn(5000000,ds.summarize(entries)['sine']['not_passed_discrete_hz'])

    def test_missing_second_phase_does_not_pass_high_frequency(self):
        r=self.run_fixture(SweepFixture(),((0,5000000,0),))
        self.assertIn(5000000,r['summary']['sine']['not_passed_discrete_hz'])

    def test_capture_failure_cancel_and_restore_failure_cannot_complete(self):
        for key,value,status in (('fail_at',3,'FAIL'),('cancel_at',3,'CANCELLED'),('fail_restore',True,'FAIL')):
            with self.subTest(key=key):
                device=SweepFixture()
                setattr(device,key,value)
                r=self.run_fixture(device,((0,100000,0),))
                self.assertEqual(r['verdict'],status)
                if key=='fail_restore':
                    self.assertTrue(r['fallback_dds_disabled'])
                else:
                    self.assertTrue(r['restored'])

    def test_ui_keeps_digital_limit_and_separates_measured_scope(self):
        SweepTests.app=ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            window=ui.ScopeWindow(profile_path=Path(folder)/'profile.json')
            window.timer.stop(); window.set_running(False)
            self.assertEqual(window.dds_freq.maximum(),12500)
            window.dds_freq.setValue(12500)
            self.assertEqual(window.dds_config()['frequency'],12500000)
            self.assertIn('数字设置上限',window.dds_freq.toolTip())
            self.assertIn('未逐点验收',window.dds_freq.toolTip())
            window.close(); window.deleteLater(); self.app.processEvents()


if __name__=='__main__':
    unittest.main()
