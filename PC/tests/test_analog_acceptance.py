"""Synthetic fixtures exercise the real acceptance gate; these are not hardware evidence."""
from dataclasses import replace
from pathlib import Path
import json
import struct
import tempfile
import threading
import unittest

from test_scope_ui import ui
import analog_acceptance as aa

np, p = ui.np, ui.proto


class AnalogFixture:
    capabilities = 31
    build_id = 0xA4261027
    device_identity = 'SYNTHETIC-TEST-FIXTURE'
    baud = 921600

    def __init__(self, gain=.1):
        self.shutdown = threading.Event()
        self.cancel_capture = threading.Event()
        self.parser = p.Parser()
        self.pre = 4096
        self.dds = aa.native_dds(0, 819)
        self.trigger = aa.trigger_payload(0)
        self.mode = p.capture_mode_payload(1, 1234567)
        self.trigger_kind = 0
        self.gain = gain
        self.count = 0
        self.fail_at = None
        self.bad_summary = False
        self.fail_restore = False
        self.cancel_at = None
        self.commands = []

    def config(self):
        return struct.pack('<II', 16384, self.pre)+self.trigger+self.dds

    def exchange(self, kind, payload=b'', restoring=False, **kwargs):
        self.commands.append((kind, payload, restoring))
        if restoring and self.fail_restore and kind == p.SET_TRIGGER:
            raise OSError('SYNTHETIC restoration failure')
        if kind == p.SET_DIAGNOSTIC:
            raise AssertionError('Analog acceptance must not use digital injection')
        if kind == p.GET_CONFIG:
            return p.Frame(kind|128, payload=self.config())
        if kind == p.GET_CAPTURE_CONFIG:
            return p.Frame(kind|128, payload=self.mode)
        if kind == p.GET_STATUS:
            return p.Frame(kind|128, payload=bytes([4, 0, 1, 0])
                           +struct.pack('<II9I', 16384, self.pre, *([0]*9)))
        if kind == p.SET_CAPTURE_MODE:
            self.mode = payload
        if kind == p.SET_TRIGGER:
            self.trigger = payload
        if kind == p.SET_DDS:
            self.dds = payload
        if kind == p.SET_RECORD:
            self.pre = (16383*struct.unpack('<II', payload)[1]+500000)//1000000
        if kind == p.READ_ENVELOPE:
            buckets = []
            for i in range(400):
                block = self.frame.words[i*16384//400:(i+1)*16384//400]
                x = 2047-(block & 4095).astype(np.int64)
                buckets.append((int(x.min()), int(x.max()), int(bool(np.any(block & 0x8000)))))
            return ui.HardwareEnvelope(tuple(buckets), 16384, 25000000, self.pre, self.frame.timestamp)
        if kind == p.READ_SATURATION:
            s = self.frame.fpga_saturation
            return p.Frame(0xb4, timestamp=self.frame.timestamp, sample_rate=25000000,
                           trigger_index=self.pre, flags=p.RESPONSE,
                           payload=struct.pack('<BBHIII', 1, 1, 0, 16384, s['saturated_samples'], s['events']))
        return p.Frame(kind|128, flags=p.RESPONSE, payload=b'\0')

    def capture(self, timeout):
        self.count += 1
        if self.count == self.fail_at:
            raise TimeoutError('SYNTHETIC acquisition timeout')
        if self.count == self.cancel_at:
            self.cancel_capture.set()
            raise InterruptedError('SYNTHETIC cancellation')
        wave, enabled, freq, phase, peak, offset = struct.unpack('<BBIIHi', self.dds)
        aa.native_dds(wave, peak, offset, freq)
        cycle = np.rint(self.gain*(offset+peak*np.sin(2*np.pi*np.arange(250)/250)))
        if wave == 3:
            cycle = np.full(250, round(self.gain*offset))
        otr_cycle = (cycle > 2047) | (cycle < -2048)
        start = 0
        if self.trigger[0] == 8:
            crossing = np.flatnonzero(otr_cycle & ~np.roll(otr_cycle, 1))
            if not len(crossing):
                raise TimeoutError('SYNTHETIC no physical OTR edge')
            start = int(crossing[0])-self.pre
        idx = (np.arange(16384)+start) % 250
        words = (2047-np.clip(cycle[idx], -2048, 2047)).astype(np.uint16)
        words |= otr_cycle[idx].astype(np.uint16)*0x8000
        s = aa.raw_statistics(words)
        saturation = {k: s[k] for k in ('count', 'saturated_samples', 'events')}
        saturation['diagnostic'] = False
        if self.bad_summary:
            saturation['saturated_samples'] += 1
        x = 2047-(words & 4095).astype(np.int64)
        measurement = dict(stats_valid=True, error=False, count=16384, minimum=int(x.min()),
                           maximum=int(x.max()), sum=int(x.sum()), square_sum=int((x*x).sum()))
        self.frame = ui.Capture(words, 25000000, self.pre, self.count*100000,
                                '硬件 UART', firmware_build=self.build_id,
                                fpga_saturation=saturation, fpga_measurement=measurement,
                                fpga_spectrum=dict(clipped=bool(np.any(words[:1024] & 0x8000))))
        return self.frame

    def read_roi(self, frame, start, count):
        return replace(frame, words=self.frame.words[start:start+count], record_offset=start,
                       trigger=self.pre-start, timestamp=self.frame.timestamp+start)

    def read_status(self):
        return dict(counters=[0]*9, backend_error=0, flags=4)


class AnalogAcceptanceTests(unittest.TestCase):
    def run_fixture(self, device):
        original = device.config(), device.mode
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            out = Path(folder)/'run'
            report = aa.run(device, out, settle_seconds=0, progress=lambda message: None)
            self.assertEqual(report, json.loads((out/'report.json').read_text(encoding='utf-8')))
            for row in report['frames']:
                self.assertEqual(len(np.load(out/row['file'])), 16384)
            if report['restored']:
                self.assertEqual((device.config(), device.mode), original)
            self.assertFalse(any(k == p.SET_DIAGNOSTIC for k, _, _ in device.commands))
            return report

    def test_zero_counts_cannot_pass_analog_acceptance(self):
        report = self.run_fixture(AnalogFixture(.1))
        self.assertEqual(report['verdict'], 'INCOMPLETE')
        self.assertTrue(report['restored'])
        self.assertTrue(report['coverage']['normal_clean'])
        for key in ('nonzero_saturation', 'physical_otr', 'otr_trigger', 'recovery'):
            self.assertIn(key, report['missing'])

    def test_overload_trigger_roi_and_recovery_required_to_pass(self):
        report = self.run_fixture(AnalogFixture(.4))
        self.assertEqual(report['verdict'], 'PASS', report.get('error'))
        self.assertFalse(report['missing'])
        triggers = [f for f in report['frames'] if f.get('otr_trigger_verified')]
        self.assertEqual([f['trigger'] for f in triggers], [0, 8192, 16383])
        self.assertEqual(len([f for f in report['frames'] if f['case'].startswith('recovery')]), 4)

    def test_failed_raw_frame_saved_and_restored(self):
        device = AnalogFixture()
        device.bad_summary = True
        report = self.run_fixture(device)
        self.assertEqual(report['verdict'], 'FAIL')
        self.assertTrue(report['restored'])
        self.assertEqual(len(report['frames']), 1)
        self.assertFalse(report['frames'][0]['verified'])

    def test_timeout_cancel_and_restoration_failure_do_not_pass(self):
        for key, value, verdict in (('fail_at', 3, 'FAIL'), ('cancel_at', 3, 'CANCELLED'),
                                    ('fail_restore', True, 'FAIL')):
            with self.subTest(key=key):
                device = AnalogFixture()
                setattr(device, key, value)
                report = self.run_fixture(device)
                self.assertEqual(report['verdict'], verdict)
                if key == 'fail_restore':
                    self.assertFalse(report['restored'])
                    self.assertTrue(report['fallback_dds_disabled'])
                else:
                    self.assertTrue(report['restored'])

    def test_otr_alignment_diagnostic_and_counter_mismatch_rejected(self):
        device = AnalogFixture()
        frame = device.capture(1)
        for changed in (replace(frame, words=frame.words | 0x8000),
                        replace(frame, fpga_saturation={**frame.fpga_saturation, 'diagnostic': True}),
                        replace(frame, fpga_spectrum={'clipped': True})):
            with self.subTest(), self.assertRaises(ValueError):
                aa.verify_record(changed)
        # Rails without OTR still count; OTR does not define saturation.
        words = np.full(16384, 2047, dtype=np.uint16)
        words[:3] = [0, 4095, 0]
        words[-1] = 4095
        s = aa.raw_statistics(words)
        self.assertEqual((s['saturated_samples'], s['events'], s['otr_samples']), (4, 2, 0))

    def test_native_stimulus_rejects_digital_clipping(self):
        for peak, offset in ((8192, 0), (8191, 1), (0, 8192), (1, -8192), (-1, 0)):
            with self.subTest(peak=peak, offset=offset), self.assertRaises(ValueError):
                aa.native_dds(0, peak, offset)

    def test_clipping_check_uses_complete_summary_outside_preview(self):
        frame = AnalogFixture().capture(1)
        preview = replace(frame, words=frame.words[:1024], trigger=512,
                          fpga_saturation={'count': 16384, 'saturated_samples': 5, 'events': 1, 'diagnostic': False})
        self.assertTrue(ui.capture_clipped(preview))


if __name__ == '__main__':
    unittest.main()
