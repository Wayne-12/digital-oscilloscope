"""Regression for absent edges, AUTO faults and DDS acknowledgement persistence."""
import struct
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

import test_scope_ui as fixture

ui, p = fixture.ui, fixture.p


class TriggerDiagnosticsTests(unittest.TestCase):
    setUpClass = fixture.UiTests.__dict__['setUpClass']
    setUp = fixture.UiTests.setUp
    tearDown = fixture.UiTests.tearDown
    wait_for = fixture.UiTests.wait_for
    def make_worker(self):
        worker = ui.SerialWorker('unused', 921600)
        worker.capabilities = p.CAP_CAPTURE_MODES | 2
        trigger = struct.pack('<BBhHhhIIHI', 0, 0, 2, 4, -205, 204, 25, 500, 410, 1024)
        dds = struct.pack('<BBIIHi', 1, 1, 100000, 0, 0, 0)
        config = struct.pack('<II', 16384, 8192) + trigger + dds
        worker.exchange = Mock(side_effect=lambda kind, *a, **k: p.Frame(kind|128,
                               flags=p.RESPONSE, payload=config if kind == p.GET_CONFIG else b'\0'))
        return worker

    def test_single_timeout_reports_actual_zero_dds_and_crossing_limits(self):
        worker = self.make_worker()
        with self.assertRaises(ui.TriggerWaitExpired) as raised:
            worker.capture(0, acquisition_mode=2)
        self.assertIn('幅度为 0 码', str(raised.exception))
        self.assertIn('-3.66～15.87 mV', str(raised.exception))
        self.assertIn('AUTO', str(raised.exception))
        self.assertEqual([call.args[0] for call in worker.exchange.call_args_list],
                         [p.SINGLE, p.STOP, p.GET_CONFIG])

    def test_auto_timeout_is_acquisition_fault_not_trigger_wait(self):
        worker = self.make_worker()
        with self.assertRaises(TimeoutError) as raised:
            worker.capture(0, acquisition_mode=0)
        self.assertNotIsInstance(raised.exception, ui.TriggerWaitExpired)
        self.assertIn('SW0', str(raised.exception))

    def test_wait_completion_stops_ui_but_retains_connection(self):
        w = self.window
        w.running = w.single_pending = w.hardware_connected = True
        w.trigger_wait_finished('未收到触发；DDS 幅度为 0 码')
        self.assertFalse(w.running or w.single_pending)
        self.assertTrue(w.hardware_connected)
        self.assertIn('未收到触发', w.state_label.text())
        self.assertIn('DDS 幅度为 0 码', w.logs.toPlainText())

    def test_real_dds_readback_replaces_stale_display(self):
        w = self.window
        w.dds_amplitude.setValue(10)
        w.receive_dds_configuration(struct.pack('<BBIIHi', 1, 1, 100000, 0, 0, 0))
        self.assertEqual(w.dds_amplitude.value(), 0)
        self.assertEqual(w.dds_wave.currentIndex(), 1)

    def test_awg_path_saves_only_acknowledged_dds_snapshot(self):
        w = self.window
        w.source.setCurrentIndex(1)
        w.hardware_connected = True
        w.device_capabilities = ui.awg.CAPABILITY
        w.dds_amplitude.setValue(10)
        queued = Mock()
        queued.submit.return_value = True
        w.worker = queued
        try:
            w.apply_dds()
            self.assertFalse(self.profile_path.exists())
            payload = queued.submit.call_args.args[1]['payload']
            w.dds_amplitude.setValue(0)
            w.remember_confirmed_command(p.SET_DDS, payload)
            self.assertEqual(ui.read_hardware_profile(self.profile_path)['dds']['amplitude'], .1)
        finally:
            w.worker = None

    def test_worker_emits_dds_confirmation_only_after_exact_readback(self):
        for mismatch in (False, True):
            with self.subTest(mismatch=mismatch):
                worker = self.make_worker()
                worker.capabilities |= ui.awg.CAPABILITY
                base = worker.exchange(p.GET_CONFIG).payload
                payload = struct.pack('<BBIIHi', 0, 1, 100000, 0, 819, 0)
                calls = []
                def exchange(kind, data=b'', **kwargs):
                    calls.append(kind)
                    if kind == p.GET_CONFIG:
                        body = base if mismatch or calls.count(kind) == 1 else base[:32]+payload
                    elif kind == ui.awg.STATUS:
                        body = struct.pack('<BBHHHHHI', 1, 0, 0, 1024, 0, 0, 0, 0)
                    else:
                        body = b'\0'
                    return p.Frame(kind|128, flags=p.RESPONSE, payload=body)
                worker.exchange = exchange
                worker.open_link = Mock()
                worker.read_status = Mock()
                worker.link = SimpleNamespace(is_open=False)
                confirmed, faults = [], []
                worker.command_confirmed.connect(lambda kind, data: confirmed.append((kind, data)))
                worker.fault.connect(faults.append)
                worker.command_done.connect(worker.shutdown.set)
                worker.submit('awg', {'action': 'apply', 'selected': False, 'payload': payload})
                worker.run()
                self.assertEqual(confirmed, [] if mismatch else [(p.SET_DDS, payload)])
                self.assertEqual(bool(faults), mismatch)

    def test_worker_trigger_wait_uses_dedicated_signal_without_second_stop(self):
        worker = self.make_worker()
        worker.open_link = Mock()
        worker.read_status = Mock()
        worker.link = SimpleNamespace(is_open=False)
        messages, faults = [], []
        worker.trigger_wait_expired.connect(messages.append)
        worker.fault.connect(faults.append)
        worker.cycle_done.connect(worker.shutdown.set)
        worker.submit('capture', (0, None, None, 2))
        worker.run()
        self.assertEqual(len(messages), 1)
        self.assertEqual(faults, [])
        self.assertEqual(sum(call.args[0] == p.STOP for call in worker.exchange.call_args_list), 1)
