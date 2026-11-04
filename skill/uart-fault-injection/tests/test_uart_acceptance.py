"""Acceptance must reject damaged/incomplete evidence and never promote an offline run."""
from pathlib import Path
import json
import math
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import scope_protocol as p
import uart_acceptance as a


class AcceptanceTests(unittest.TestCase):
    def client(self, fault=None):
        clock = a.VirtualClock()
        link = a.OfflineSerial(921600, clock)
        client = a.Client(link, 921600, clock)
        client.handshake(0xA0261025)
        client.status()
        link.fault = fault
        return client

    def test_exact_baud_and_build(self):
        client = self.client()
        self.assertEqual(client.baud, 921600)
        with self.assertRaisesRegex(ValueError, 'build'):
            client.handshake(0xA0261026)

    def test_echo_crc_missing_duplicate_noise_and_mismatch(self):
        for fault in ('crc', 'drop', 'duplicate', 'noise', 'echo'):
            with self.subTest(fault=fault):
                client = self.client(fault)
                with self.assertRaises((ValueError, TimeoutError)):
                    client.exchange(p.PING, b'\x55\xaa'+bytes(range(256)))

    def test_stream_gap(self):
        client = self.client('gap')
        with self.assertRaisesRegex(ValueError, 'sequence'):
            client.wave(0, 16384)

    def test_crc_error_kept_but_does_not_prevent_cleanup_commands(self):
        client = self.client('crc')
        with self.assertRaises(ValueError):
            client.exchange(p.PING, b'bad')
        client.link.fault = None
        client.exchange(p.STOP)
        self.assertEqual(client.parser.errors['crc'], 1)
        client.status()

    def test_overflow_and_device_reset(self):
        client = self.client('overflow')
        with self.assertRaisesRegex(ValueError, 'counter'):
            client.status()
        client = self.client()
        client.link.good = 0
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            client.status()

    def test_counter_and_sequence_wrap(self):
        client = self.client()
        client.link.good = 0xfffffffe
        client.baseline = None
        client.status()
        client.sequence = 65535
        client.wave(0, 16384)
        client.status()
        self.assertEqual(client.link.good, 1)
        self.assertEqual(client.status_deltas['crc'], 0)

    def test_full_and_multires_capture(self):
        client = self.client()
        full = client.capture(full=True)
        roi = client.capture()
        self.assertEqual(full['samples'], 16384)
        self.assertEqual(roi['samples'], 2048)
        self.assertGreater(roi['timestamp'], full['timestamp'])
        client.status()

    def test_stale_capture_timestamp(self):
        client = self.client()
        client.capture()
        client.link.timestamp -= 250000
        with self.assertRaisesRegex(ValueError, 'stale'):
            client.capture()

    def test_frozen_analysis_and_reject_stale_or_wrong_statistics(self):
        for fault in (None, 'stale-summary', 'wrong-sum', 'bad-spectrum'):
            with self.subTest(fault=fault):
                client = self.client()
                client.capabilities = 7
                write = client.link.write

                def summaries(wire):
                    result = write(wire)
                    request, = p.Parser().feed(wire)
                    if request.kind not in (p.READ_MEASURE, p.READ_SPECTRUM):
                        return result
                    if request.kind == p.READ_MEASURE:
                        values = [2047-word for word in client.link.words]
                        data = bytearray(64)
                        data[0] = 1
                        struct.pack_into('<IhhhHH', data, 4, 16384, min(values), max(values), 0,
                                         max(values)-min(values), round(math.sqrt(sum(x*x for x in values)/16384)))
                        struct.pack_into('<qQ', data, 20, sum(values)+(1 if fault == 'wrong-sum' else 0),
                                         sum(x*x for x in values))
                    else:
                        data = bytearray(96)
                        data[:8] = bytes((1, 0, 0, 0, 0, 4, 1, 0))
                        for h in range(2, 6):
                            data[32+(h-2)*16] = h
                        if fault == 'bad-spectrum':
                            data[0] = 2
                    client.link.buffer[:] = p.encode(p.Frame(request.kind | 128, request.sequence,
                            client.link.timestamp+(1 if fault == 'stale-summary' else 0),
                            25000000, 8192, p.RESPONSE, bytes(data)))
                    return result

                client.link.write = summaries
                if fault is None:
                    client.capture(full=True)
                    client.status()
                else:
                    with self.assertRaises(ValueError):
                        client.capture(full=True)

    def test_otr_and_reserved_words(self):
        for bit in (0x8000, 0x1000):
            with self.subTest(bit=bit):
                client = self.client()
                client.link.words[0] |= bit
                with self.assertRaises(ValueError):
                    client.capture(full=True)

    def test_short_or_wrong_last_and_wrong_raw_metadata(self):
        for fault in ('early-last', 'metadata'):
            client = self.client()
            write = client.link.write

            def damaged(wire):
                result = write(wire)
                request, = p.Parser().feed(wire)
                if request.kind == p.READ_WAVE:
                    frames = p.Parser().feed(client.link.buffer)
                    if fault == 'early-last':
                        f = frames[0]
                        frames = [p.Frame(f.kind, f.sequence, f.timestamp, f.sample_rate,
                                          f.trigger_index, p.RESPONSE | p.FIRST | p.LAST, f.payload)]
                    else:
                        f = frames[-1]
                        frames[-1] = p.Frame(f.kind, f.sequence, f.timestamp+1, f.sample_rate,
                                             f.trigger_index, f.flags, f.payload)
                    client.link.buffer[:] = b''.join(p.encode(f) for f in frames)
                return result

            client.link.write = damaged
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                client.wave(0, 16384)

    def test_offline_report_restores_and_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'run'
            report = a.run_acceptance(output, 115200, duration=20, uart_duration=1,
                                      min_bytes=2048, progress=lambda _: None)
            self.assertEqual(report['verdict'], 'OFFLINE_PASS')
            self.assertTrue(report['restored'])
            self.assertEqual(report['recovery'], 'PASS')
            self.assertEqual(report['qualified_bauds'], [])
            self.assertFalse(a.qualifies(report))
            self.assertTrue((output/'first_full_wave.bin').is_file())
            self.assertEqual(json.loads((output/'stable_rates.json').read_text())['qualified_bauds'], [])

    def test_interrupt_still_restores_and_saves(self):
        clock = a.VirtualClock()
        model = a.OfflineSerial(921600, clock)
        original = model.trigger

        def interrupted(message):
            if message.startswith('uart-complete'):
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as directory:
            report = a.run_acceptance(Path(directory)/'run', 921600, duration=1, uart_duration=.1,
                                      min_bytes=1, clock=clock, link_factory=lambda: model, progress=interrupted)
            self.assertEqual(report['verdict'], 'INTERRUPTED')
            self.assertTrue(report['restored'])
            self.assertEqual(model.trigger, original)
            self.assertFalse(a.qualifies(report))

    def test_restore_failure_disqualifies(self):
        clock = a.VirtualClock()
        model = a.OfflineSerial(921600, clock)

        def interrupted(message):
            if message.startswith('uart-complete'):
                model.fault = 'drop'
                raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as directory:
            report = a.run_acceptance(Path(directory)/'run', 921600, duration=1, uart_duration=.1,
                                      min_bytes=1, clock=clock, link_factory=lambda: model, progress=interrupted)
            self.assertEqual(report['verdict'], 'FAIL')
            self.assertFalse(report['restored'])
            self.assertIn('restore_error', report)
            self.assertEqual(report['qualified_bauds'], [])

    def test_fail_closed_qualification(self):
        complete = {'source': 'hardware-uart', 'verdict': 'PASS', 'restored': True, 'recovery': 'PASS',
                    'soak_seconds': 7200, 'echo_seconds': 600, 'echo_payload_bytes': 1048576, 'captures': 100,
                    'firmware_sha256': 'a'*64, 'device_id': 'board-1', 'pc_errors': {'crc': 0},
                    'fpga_error_deltas': {'crc': 0}, 'transport_errors': {'sequence': 0},
                    'unanswered_requests': 0, 'incomplete_captures': 0}
        self.assertTrue(a.qualifies(complete))
        for changes in ({'source': 'offline-model'}, {'verdict': 'SHORT_PASS'}, {'restored': False},
                        {'recovery': 'NOT_RUN'}, {'soak_seconds': 7199}, {'echo_seconds': 599},
                        {'echo_payload_bytes': 1048575}, {'pc_errors': {'crc': 1}},
                        {'fpga_error_deltas': {'overflow': 1}}, {'firmware_sha256': None}, {'device_id': ''}):
            with self.subTest(changes=changes):
                self.assertFalse(a.qualifies(complete | changes))

    def test_invalid_duration_and_missing_hardware_inputs(self):
        for duration in (0, -1, float('nan'), float('inf')):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                a.run_acceptance('unused', 921600, duration=duration)
        with self.assertRaises(ValueError):
            a.run_acceptance('unused', 921600, offline=False)


if __name__ == '__main__':
    unittest.main()
