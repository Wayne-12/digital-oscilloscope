"""Explicit simulated fixtures for the real calibration transaction and failure recovery."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from test_scope_ui import ui
import hardware_calibration as hc

np,p = ui.np,ui.proto


class SimulatedCalibrationDevice:
    def __init__(self,gain=0.035):
        self.capabilities = 3
        self.shutdown = threading.Event()
        self.cancel_capture = threading.Event()
        self.parser = p.Parser()
        self.trigger_kind = 0
        self.trigger = struct.pack('<BBhHhhIIHI',0,0,4,2,-100,100,1,100,100,256)
        self.dds = struct.pack('<BBIIHi',2,1,54000,0x12345678,4915,0)
        self.initial = self.configuration()
        self.gain,self.bias = gain,4.0
        self.count = 0
        self.fail_at = None
        self.cancel_at = None
        self.restore_failure = False
        self.commands = []
        self.rng = np.random.default_rng(42)

    def configuration(self):
        return struct.pack('<II',16384,8192)+self.trigger+self.dds

    def exchange(self,kind,payload=b'',restoring=False):
        self.commands.append((kind,bytes(payload),restoring))
        if restoring and self.restore_failure and kind == p.SET_DDS:
            raise OSError('SIMULATED disconnect during restore')
        if kind == p.GET_CONFIG:
            return p.Frame(kind|128,payload=self.configuration())
        if kind == p.SET_TRIGGER:
            self.trigger = payload
        if kind == p.SET_DDS:
            self.dds = payload
        return p.Frame(kind|128,payload=b'\0')

    def capture(self,timeout):
        self.count += 1
        if self.count == self.fail_at:
            raise TimeoutError('SIMULATED acquisition timeout')
        if self.count == self.cancel_at:
            self.cancel_capture.set()
            raise InterruptedError('SIMULATED cancellation')
        wave,_enabled,freq,_phase,amplitude,offset = struct.unpack('<BBIIHi',self.dds)
        self.assert_stimulus_bounds(wave,amplitude,offset)
        t = np.arange(16384)/25000000
        actual = ((freq*(1<<32)+12500000)//25000000)*25000000/(1<<32)
        y = np.full(16384,self.bias+self.gain*offset)
        if wave != 3:
            attenuation = 1/np.sqrt(1+(freq/2e6)**2)
            y += self.gain*amplitude*attenuation*(np.sin(2*np.pi*actual*t)+0.003*np.sin(6*np.pi*actual*t))
        y += self.rng.normal(0,0.15,len(y))
        words = np.rint(2047-y).astype(np.uint16)
        return ui.Capture(words,25000000,8192,100000*self.count,'硬件 UART')

    @staticmethod
    def assert_stimulus_bounds(wave,amplitude,offset):
        assert amplitude <= hc.MAX_TEST_CODE and abs(offset) <= hc.MAX_TEST_CODE


class CalibrationTransactionTests(unittest.TestCase):
    def test_fingerprint_rejects_inconsistent_gain_ratio(self):
        valid=self.run_device(SimulatedCalibrationDevice())
        for key,value in (('gain',2),('reference_gain',valid['reference_gain']*2),
                          ('dc_gain',-valid['dc_gain'])):
            corrupted=copy.deepcopy(valid);corrupted[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                hc.validate_fingerprint(corrupted)

    def run_device(self,device,baseline=None):
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            output = Path(folder)/'run'
            result = hc.run_closed_loop(device,output,'SIMULATED-FIXTURE',baseline=baseline,settle_seconds=0)
            self.assertEqual(result,json.loads((output/'report.json').read_text(encoding='utf-8')))
            for frame in result['raw_frames']:
                self.assertEqual(len(np.load(output/frame['file'])),16384)
            return result

    def test_real_path_contract_and_exact_restoration(self):
        device = SimulatedCalibrationDevice()
        result = self.run_device(device)
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['restored'])
        self.assertEqual(device.configuration(),device.initial)
        self.assertAlmostEqual(result['dc_gain'],0.035,delta=0.00015)
        self.assertAlmostEqual(result['offset'],4.5*hc.SCALE,delta=0.0007)
        self.assertEqual(result['gain'],1)
        self.assertEqual(len(result['raw_frames']),35)
        self.assertLess(abs(result['holdout_dc_error_code']),0.5)
        self.assertEqual(result['response_frequency'],list(hc.FREQUENCIES))
        self.assertLess(result['response_db'][-1],-0.5)
        self.assertEqual(len(result['harmonic_amplitudes']),4)
        self.assertLess(result['tone_noise'],0.003)
        self.assertNotIn('thd',result)
        self.assertNotIn('snr',result)
        self.assertTrue(all(k not in result for k in ('sinad','sfdr','enob')))
        comparison = result['before_after']
        self.assertGreater(abs(comparison['zero']['before_error_volts']),0.009)
        self.assertLess(abs(comparison['zero']['after_error_volts']),0.001)
        self.assertLess(abs(comparison['dc_holdout']['after_error_volts']),0.001)
        self.assertFalse(any(k==p.SET_RECORD for k,_,_ in device.commands))
        self.assertEqual(result['configuration_before_hex'],result['configuration_after_hex'])

    def test_baseline_gain_correction_and_wrong_device_rejected(self):
        baseline = self.run_device(SimulatedCalibrationDevice())
        changed = self.run_device(SimulatedCalibrationDevice(0.0385),baseline)
        self.assertEqual(changed['status'],'PASS')
        self.assertAlmostEqual(changed['gain'],1.10,delta=0.006)
        comparison = changed['before_after']['dc_holdout']
        self.assertGreater(abs(comparison['before_error_volts']),0.01)
        self.assertLess(abs(comparison['after_error_volts']),0.001)
        self.assertEqual(changed['comparison_reference'],'saved-relative-baseline')
        other = copy.deepcopy(baseline)
        other['device_id'] = 'OTHER'
        rejected = self.run_device(SimulatedCalibrationDevice(),other)
        self.assertEqual(rejected['status'],'FAIL')
        self.assertTrue(rejected['restored'])

    def test_failure_cancel_disconnect_and_no_signal_never_publish_calibration(self):
        for mode in ('timeout','cancel','restore-failed','no-signal'):
            device = SimulatedCalibrationDevice(0 if mode=='no-signal' else 0.035)
            if mode == 'cancel':
                device.cancel_at = 5
            elif mode in ('timeout','restore-failed'):
                device.fail_at = 5
            device.restore_failure = mode=='restore-failed'
            result = self.run_device(device)
            self.assertEqual(result['status'],'CANCELLED' if mode=='cancel' else 'FAIL')
            self.assertEqual(result['restored'],mode!='restore-failed')
            if mode!='restore-failed':
                self.assertEqual(device.configuration(),device.initial)
            with self.assertRaises(ValueError):
                hc.validate_fingerprint(result)

    def test_comparison_known_observations_and_invalid_inputs(self):
        result = hc.relative_comparison(0.02,1.1,0.02,1.12,1.0)
        self.assertAlmostEqual(result['zero']['before_error_volts'],0.02)
        self.assertAlmostEqual(result['zero']['after_error_volts'],0)
        self.assertAlmostEqual(result['dc_holdout']['before_error_volts'],0.12)
        self.assertAlmostEqual(result['dc_holdout']['after_error_volts'],0)
        for values in ((0,0,0,1,1),(0,-1,0,1,1),(float('nan'),1,0,1,1),(0,1,0,float('inf'),1)):
            with self.assertRaises(ValueError):
                hc.relative_comparison(*values)

    def test_reverse_polarity_uses_signed_relative_target(self):
        baseline = self.run_device(SimulatedCalibrationDevice(-0.035))
        self.assertEqual(baseline['status'],'PASS')
        changed = self.run_device(SimulatedCalibrationDevice(-0.0385),baseline)
        self.assertEqual(changed['status'],'PASS')
        dc = changed['before_after']['dc_holdout']
        self.assertLess(dc['expected_volts'],0)
        self.assertLess(abs(dc['after_error_volts']),0.001)

    def test_configuration_decode_and_fingerprint_reject_corruption(self):
        device = SimulatedCalibrationDevice()
        self.assertEqual(hc.decode_configuration(device.initial)['dds'],device.dds)
        for payload in (b'',device.initial[:-1],struct.pack('<II',16384,16384)+device.initial[8:],
                        device.initial[:32]+struct.pack('<BBIIHi',4,1,100000,0,819,0)):
            with self.assertRaises(ValueError):
                hc.decode_configuration(payload)
        with self.assertRaises(ValueError):
            hc.validate_fingerprint({'format':'scope-ui-fingerprint-v1','source':'software-demo'})

    def test_raw_file_failure_restores_and_existing_run_is_preserved(self):
        device = SimulatedCalibrationDevice()
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            output = Path(folder)/'run'
            with patch.object(hc.np,'save',side_effect=OSError('SIMULATED disk error')):
                result = hc.run_closed_loop(device,output,'SIMULATED-FIXTURE',settle_seconds=0)
            self.assertEqual(result['status'],'FAIL')
            self.assertTrue(result['restored'])
            self.assertEqual(device.configuration(),device.initial)
            before = (output/'report.json').read_bytes()
            command_count = len(device.commands)
            repeat = hc.run_closed_loop(device,output,'SIMULATED-FIXTURE',settle_seconds=0)
            self.assertEqual(repeat['status'],'FAIL')
            self.assertEqual(len(device.commands),command_count)
            self.assertEqual((output/'report.json').read_bytes(),before)


class CalibrationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])

    def test_hardware_controls_range_and_immutable_raw(self):
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            device = SimulatedCalibrationDevice()
            result = hc.run_closed_loop(device,Path(folder)/'run','SIMULATED-FIXTURE',settle_seconds=0)
            w = ui.ScopeWindow(profile_path=Path(folder)/'profile.json')
            w.timer.stop()
            w.source.setCurrentIndex(1)
            w.hardware_connected = True
            w.device_capabilities = 3
            w.device_rate = 25000000
            w.hardware_calibration_busy = True
            w.cal_step = 0
            w.receive_hardware_calibration(result)
            self.assertTrue(w.apply_cal.isEnabled())
            self.assertTrue(w.cal_button.isEnabled())
            self.assertIn('实物独立复测',w.cal_comparison_note.text())
            self.assertAlmostEqual(float(w.cal_comparison.item(0,3).text()),
                                   result['before_after']['zero']['after_error_volts']*1000,places=3)
            raw = np.full(16384,2043,dtype=np.uint16)
            frame = ui.Capture(raw,25000000,8192,55,'硬件 UART')
            w.single_pending = True
            w.receive_capture(frame)
            w.single_pending = False
            w.apply_cal.setChecked(True)
            self.assertLess(abs(float(w.display_volts().mean())),0.001)
            np.testing.assert_array_equal(w.current.words,raw)
            w.current = ui.Capture(np.full(16384,1800,dtype=np.uint16),25000000,8192,56,'硬件 UART')
            self.assertIsNone(w.active_display_calibration())
            target = Path(folder)/'hardware.json'
            with patch.object(ui.QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(target),'JSON')):
                w.save_hardware_fingerprint()
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['source'],'hardware-uart')
            w.close()

    def test_demo_comparison_source_boundary_and_cancel(self):
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            w = ui.ScopeWindow(profile_path=Path(folder)/'profile.json')
            w.timer.stop()
            w.start_calibration()
            w.cal_timer.stop()
            for _ in range(7):
                w.calibration_tick()
            self.assertIn('软件演示',w.cal_comparison_note.text())
            self.assertGreater(abs(float(w.cal_comparison.item(0,2).text())),26)
            self.assertLess(abs(float(w.cal_comparison.item(0,3).text())),0.2)
            self.assertEqual(w.calibration['response_frequency'],list(hc.FREQUENCIES))
            self.assertEqual(w.calibration['response_db'][3],0)
            w.start_calibration()
            w.cal_timer.stop()
            for _ in range(3):
                w.calibration_tick()
            w.cancel_calibration()
            self.assertIsNone(w.calibration)
            self.assertFalse(w.apply_cal.isEnabled())
            self.assertEqual(w.cal_comparison.item(0,3).text(),'—')
            w.show_calibration_comparison(hc.relative_comparison(0,1,0,1,1),'软件演示')
            w.source.setCurrentIndex(1)
            self.assertEqual(w.cal_comparison.item(0,3).text(),'—')
            w.close()

    def test_busy_roi_and_failed_calibration_guard(self):
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            w = ui.ScopeWindow(profile_path=Path(folder)/'profile.json')
            w.timer.stop()
            w.source.setCurrentIndex(1)
            w.hardware_connected = True
            w.device_capabilities = 3
            w.device_rate = 25000000
            w.worker = Mock()
            w.worker.cancel_capture = threading.Event()
            w.worker.stop_requested = threading.Event()
            w.start_hardware_calibration()
            self.assertTrue(w.hardware_calibration_busy)
            self.assertFalse(w.side_panel.isEnabled())
            self.assertFalse(w.run_button.isEnabled())
            self.assertFalse(w.tabs.isTabEnabled(2))
            w.receive_hardware_calibration({'status': 'CANCELLED','restored': True,'error': 'cancelled','output_dir': folder})
            self.assertFalse(w.hardware_calibration_valid)
            self.assertFalse(w.apply_cal.isEnabled())
            self.assertTrue(w.side_panel.isEnabled())
            w.worker = None
            w.close()

    def test_running_selftest_waits_for_stop_then_starts(self):
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            w=ui.ScopeWindow(profile_path=Path(folder)/'profile.json');w.timer.stop()
            w.source.setCurrentIndex(1);w.hardware_connected=True;w.device_capabilities=63
            w.worker=Mock();w.worker.cancel_capture=threading.Event();w.worker.stop_requested=threading.Event()
            w.worker.stop_requested.set();w.running=True;w.capture_busy=True
            w.start_hardware_calibration()
            self.assertTrue(w._calibration_start_pending);self.assertFalse(w.running)
            self.assertFalse(w.hardware_calibration_busy);self.assertFalse(w.cal_button.isEnabled())
            w.capture_busy=False;w.worker.stop_requested.clear();w._wait_calibration_idle()
            self.assertTrue(w.hardware_calibration_busy);self.assertFalse(w._calibration_start_pending)
            w.receive_hardware_calibration(dict(status='CANCELLED',restored=True,error='test cleanup',output_dir=folder))
            w.worker=None;w.close()

    def test_cancel_while_waiting_never_submits_selftest(self):
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            w=ui.ScopeWindow(profile_path=Path(folder)/'profile.json');w.timer.stop()
            w.source.setCurrentIndex(1);w.hardware_connected=True;w.device_capabilities=63
            w.worker=Mock();w.worker.cancel_capture=threading.Event();w.worker.stop_requested=threading.Event()
            w.worker.stop_requested.set();w.capture_busy=True
            w.start_hardware_calibration();w.cancel_calibration();w._wait_calibration_idle()
            self.assertFalse(w._calibration_start_pending);w.worker.submit.assert_not_called()
            w.worker=None;w.close()


class AwgCalibrationDevice(SimulatedCalibrationDevice):
    def __init__(self):
        super().__init__();self.capabilities=63;self.selected=True
        self.mode=p.capture_mode_payload(1)
    def exchange(self,kind,payload=b'',restoring=False):
        if kind==p.GET_CAPTURE_CONFIG:return p.Frame(kind|128,payload=self.mode)
        if kind==ui.awg.STATUS:
            return p.Frame(kind|128,payload=struct.pack('<BBHHHHHI',1,1|int(self.selected)*4,0,1024,1024,0xabcd,0xabcd,0),flags=p.RESPONSE)
        if kind==ui.awg.SELECT:
            assert self.dds[1]==0,'selection must be changed with DDS disabled'
            self.selected=bool(payload[0])
            return p.Frame(kind|128,payload=b'\0',flags=p.RESPONSE)
        return super().exchange(kind,payload,restoring)
    def capture(self,timeout):
        assert not self.selected,'selftest must use standard DDS'
        return super().capture(timeout)

class AwgCalibrationRestoreTests(unittest.TestCase):
    def test_success_cancel_failure_preserve_selected_table(self):
        for state in ('success','cancel','fail'):
            with self.subTest(state=state),tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
                device=AwgCalibrationDevice()
                if state=='cancel':device.cancel_at=4
                if state=='fail':device.fail_at=4
                result=hc.run_closed_loop(device,Path(folder)/'run','AWG-FIXTURE',settle_seconds=0)
                self.assertEqual(result['status'],dict(success='PASS',cancel='CANCELLED',fail='FAIL')[state])
                self.assertTrue(result['restored']);self.assertTrue(device.selected)
                self.assertEqual(device.configuration(),device.initial)
                self.assertEqual(result['awg_after']['active_crc'],0xabcd)


if __name__ == '__main__':
    unittest.main()
