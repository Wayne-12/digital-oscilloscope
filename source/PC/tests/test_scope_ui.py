"""无硬件检查：数据保真、分析、UI 操作以及现有 UART 的实际编解码路径。"""
import importlib.util
import csv
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scope_ui", ROOT / "示波器显示界面.py")
ui = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ui
spec.loader.exec_module(ui)
np = ui.np
p = ui.proto


class FakeSerial:
    """只模拟串口字节端点；响应也经过正式 encode/Parser 和分包重组。"""
    def __init__(self, words):
        self.words = words
        self.buffer = bytearray()
        self.requests = []

    @property
    def in_waiting(self):
        return len(self.buffer)

    def write(self, wire):
        request = p.Parser().feed(wire)[0]
        self.requests.append(request)
        if request.kind == p.READ_WAVE:
            offset, count = struct.unpack("<II", request.payload)
            for index, start in enumerate(range(offset, offset+count, 508)):
                data = self.words[start:min(start+508, offset+count)]
                last = start+len(data) == offset+count
                flags = p.RESPONSE | (p.FIRST if index == 0 else 0) | (p.LAST if last else p.MORE)
                payload = struct.pack("<II", start, len(self.words)) + data.astype("<u2").tobytes()
                self.buffer += p.encode(p.Frame(0xB0, (request.sequence+index) & 65535,
                                                123456+start, 25000000, 8192, flags, payload))
        elif request.kind == p.GET_STATUS:
            payload = bytes([2, 0, 1, 0])+struct.pack("<II9I", len(self.words), 8192, *([0]*9))
            self.buffer += p.encode(p.Frame(0x83, request.sequence, sample_rate=25000000,
                                            flags=p.RESPONSE, payload=payload))
        else:
            self.buffer += p.encode(p.Frame(request.kind | 0x80, request.sequence,
                                            flags=p.RESPONSE, payload=b"\x00"))
        return len(wire)

    def read(self, count):
        # 故意跨越头部和数据边界拆成非对齐小块。
        size = min(count, 37, len(self.buffer))
        chunk = bytes(self.buffer[:size])
        del self.buffer[:size]
        return chunk


class HandshakeSerial(FakeSerial):
    def __init__(self, words, build_id=0x20261022):
        super().__init__(words)
        self.is_open = True
        self.build_id = build_id

    def reset_input_buffer(self):
        self.buffer.clear()

    def close(self):
        self.is_open = False

    def write(self, wire):
        request = p.Parser().feed(wire)[0]
        if request.kind in (p.PING, p.GET_VERSION):
            self.requests.append(request)
            payload = request.payload if request.kind == p.PING else b'\x01\x00\x00\x00'+struct.pack('<I', self.build_id)
            self.buffer += p.encode(p.Frame(request.kind|0x80, request.sequence, flags=p.RESPONSE, payload=payload))
            return len(wire)
        return super().write(wire)

    def read(self, count):
        if not self.buffer:
            time.sleep(.001)
        return super().read(count)


class NumericalTests(unittest.TestCase):
    def test_capture_rejects_invalid_data_and_owns_immutable_words(self):
        raw = np.array([1, 2, 3], dtype=np.uint16)
        frame = ui.Capture(raw, 25000000, 1, 5, "test")
        raw[0] = 100
        self.assertEqual(frame.words[0], 1)
        with self.assertRaises(ValueError):
            frame.words[0] = 99
        for words, rate, trigger, stamp in [([], 25, 0, 0), ([0x1000], 25, 0, 0),
                                           ([0], 0, 0, 0), ([0], 25, 1, 0),
                                           ([0], 25, 0, -1), ([0], 25, 0, 1 << 64)]:
            with self.subTest(words=words, rate=rate, trigger=trigger):
                with self.assertRaises(ValueError):
                    ui.Capture(np.asarray(words, dtype=np.uint16), rate, trigger, stamp, "test")

    def test_vector_measure_with_noise_and_high_frequency(self):
        rng = np.random.default_rng(721)
        for rate, frequency in [(25000000, 10000), (25000000, 100000), (25000000, 10000000)]:
            y = np.sin(2*np.pi*frequency*np.arange(16384)/rate)+rng.normal(0, .005, 16384)
            current = ui.measure(y, rate)
            self.assertAlmostEqual(current["frequency"], frequency, delta=frequency*.001)
            self.assertAlmostEqual(current["rms"], 1/math.sqrt(2), delta=.003)

    def test_module_polarity_and_otr_untouched(self):
        words = np.array([0, 4095, 0x8000 | 2048], dtype=np.uint16)
        frame = ui.Capture(words.copy(), 25000000, 1, 5, "test")
        self.assertAlmostEqual(frame.volts()[0], 5)
        self.assertAlmostEqual(frame.volts()[1], -5)
        np.testing.assert_array_equal(frame.words, words)
        self.assertAlmostEqual(frame.times()[1], 0)

    def test_envelope_retains_impulses_and_final_sample(self):
        y = np.zeros(16384)
        y[17], y[999], y[-1] = 4.7, -4.8, 4.9
        _, low, high = ui.envelope(np.arange(len(y)), y, 800)
        self.assertEqual(len(low), 800)
        self.assertEqual(low.min(), -4.8)
        self.assertEqual(high.max(), 4.9)
        self.assertEqual(high[-1], 4.9)

    def test_frequency_and_short_record_invalid(self):
        rate = 25000000
        y = np.sin(2*np.pi*10000*np.arange(16384)/rate)
        result = ui.measure(y, rate)
        self.assertAlmostEqual(result["frequency"], 10000, delta=1)
        self.assertAlmostEqual(result["duty"], 50, delta=0.02)
        self.assertTrue(math.isnan(ui.measure(y[:1024], rate)["frequency"]))

    def test_fft_fixed_1024_amplitude_and_harmonic_summary(self):
        rate, n = 25000000, 1024
        phase = 2*np.pi*41*np.arange(n)/n
        y = 2*np.sin(phase)+.04*np.sin(3*phase)
        freq, db, peak, harmonics, spacing = ui.spectrum(y, rate, n, True)
        self.assertEqual(peak,41)
        self.assertAlmostEqual(freq[peak],41*rate/n)
        self.assertAlmostEqual(db[peak],20*np.log10(2/5),delta=.01)
        self.assertAlmostEqual(harmonics[1][2],.04,delta=.001)
        self.assertEqual(spacing,rate/n)
        self.assertEqual(ui.spectrum(np.sin(2*np.pi*np.arange(n)/n),rate,n,True)[3],[])

    def test_fft_rejects_extended_size_and_short_frames(self):
        for n,y in ((2048,np.ones(2048)),(1024,np.ones(512))):
            with self.assertRaises(ValueError):
                ui.spectrum(y,25000000,n,True)

    def test_serial_fragmented_complete_capture(self):
        words = (np.arange(16384) % 4096).astype(np.uint16)
        words[777] |= 0x8000
        worker = ui.SerialWorker("FAKE", 115200)
        worker.link = FakeSerial(words)
        frames = []
        worker.frame_ready.connect(frames.append)
        worker.capture(1)
        self.assertEqual(len(frames), 1)
        np.testing.assert_array_equal(frames[0].words, words)
        self.assertEqual(frames[0].timestamp, 123456)
        self.assertEqual(frames[0].trigger, 8192)
        self.assertEqual([r.kind for r in worker.link.requests], [p.SINGLE, p.GET_STATUS, p.READ_WAVE])

    def test_serial_cancel_before_single_sends_nothing(self):
        worker = ui.SerialWorker("FAKE", 115200)
        worker.link = FakeSerial(np.zeros(16384, dtype=np.uint16))
        worker.cancel_capture.set()
        with self.assertRaises(InterruptedError):
            worker.capture(1)
        self.assertEqual(worker.link.requests, [])

    def test_high_speed_handshake_falls_back_to_legacy_without_dds_commands(self):
        worker = ui.SerialWorker("FAKE", 921600)
        links = [HandshakeSerial(np.zeros(16384, dtype=np.uint16)) for _ in range(2)]
        original = worker.exchange
        def exchange(kind, *args, **kwargs):
            if worker.baud == 921600:
                raise TimeoutError("Old firmware")
            return original(kind, *args, **kwargs)
        with patch.object(ui.serial, "Serial", side_effect=links) as serial_factory:
            with patch.object(worker, "exchange", side_effect=exchange):
                worker.open_link()
        self.assertEqual([c.args[1] for c in serial_factory.call_args_list], [921600,115200])
        self.assertFalse(links[0].is_open)
        self.assertEqual(worker.baud, 115200)
        self.assertEqual([r.kind for r in links[1].requests], [p.PING,p.GET_VERSION])

    def test_high_speed_handshake_has_no_legacy_attempt_when_successful(self):
        worker = ui.SerialWorker("FAKE", 921600)
        link = HandshakeSerial(np.zeros(16384, dtype=np.uint16))
        with patch.object(ui.serial, "Serial", return_value=link) as serial_factory:
            worker.open_link()
        self.assertEqual(serial_factory.call_count, 1)
        self.assertEqual(worker.baud, 921600)

    def test_live_preview_reads_trigger_window_with_absolute_metadata(self):
        words = (np.arange(16384) % 4096).astype(np.uint16)
        words[8193] |= 0x8000
        worker = ui.SerialWorker("FAKE", 115200)
        worker.link = FakeSerial(words)
        frames = []
        worker.frame_ready.connect(frames.append)
        worker.capture(1, 2000)
        request = worker.link.requests[-1]
        self.assertEqual(struct.unpack("<II", request.payload), (7192, 2000))
        np.testing.assert_array_equal(frames[0].words, words[7192:9192])
        self.assertEqual(frames[0].trigger, 1000)
        self.assertEqual(frames[0].timestamp, 123456+7192)

    def test_preview_rejects_wrong_start_total_and_extra_samples(self):
        for start, total, size in [(7191, 16384, 8), (7192, 16383, 8), (7192, 16384, 9)]:
            worker = ui.SerialWorker("FAKE", 115200)
            link = FakeSerial(np.zeros(16384, dtype=np.uint16))
            def write(wire):
                request = p.Parser().feed(wire)[0]
                payload = struct.pack("<II", start, total)+np.ones(size, dtype="<u2").tobytes()
                link.buffer += p.encode(p.Frame(0xB0, request.sequence, 123456+start, 25000000,
                                                7196, p.RESPONSE|p.FIRST|p.LAST, payload))
                return len(wire)
            link.write = write
            worker.link = link
            with self.subTest(start=start, total=total, size=size):
                with self.assertRaises(ValueError):
                    worker.exchange(p.READ_WAVE, struct.pack("<II", 7192, 8), wave=True,
                                    record_length=16384)

    def test_serial_rejects_malformed_success_and_partial_write(self):
        for payload in (b"", b"\x01", b"\x00\x00"):
            worker = ui.SerialWorker("FAKE", 115200)
            link = FakeSerial(np.zeros(16384, dtype=np.uint16))
            def write(wire):
                f = p.Parser().feed(wire)[0]
                link.buffer += p.encode(p.Frame(0xA1, f.sequence, flags=p.RESPONSE, payload=payload))
                return len(wire)
            link.write = write
            worker.link = link
            with self.assertRaises(ValueError):
                worker.exchange(p.STOP)
        worker.link.write = lambda wire: len(wire)-1
        with self.assertRaises(OSError):
            worker.exchange(p.STOP)

    def test_serial_rejects_duplicate_first_and_inconsistent_total(self):
        for repeated, total in [(True, 4), (False, 8)]:
            worker = ui.SerialWorker("FAKE", 115200)
            link = FakeSerial(np.zeros(4, dtype=np.uint16))
            def write(wire):
                f = p.Parser().feed(wire)[0]
                first = p.Frame(0xB0, f.sequence, 1234, 25000000, 1, p.RESPONSE|p.FIRST|p.MORE,
                                struct.pack("<IIHH", 0, total, 1, 2))
                last = p.Frame(0xB0, (f.sequence+1)&65535, 1236, 25000000, 1,
                               p.RESPONSE|p.LAST|(p.FIRST if repeated else 0), struct.pack("<IIHH", 2, total, 3, 4))
                link.buffer += p.encode(first)+p.encode(last)
                return len(wire)
            link.write = write
            worker.link = link
            with self.assertRaises(ValueError):
                worker.exchange(p.READ_WAVE, struct.pack("<II", 0, 4), wave=True)

    def test_request_queue_is_bounded_and_status_is_coalesced(self):
        worker = ui.SerialWorker("FAKE", 115200)
        with self.assertRaises(ValueError):
            worker.submit("stop")  # STOP 通过独立事件处理，禁止进入普通请求队列。
        self.assertTrue(worker.submit("status"))
        self.assertFalse(worker.submit("status"))
        for i in range(15):
            self.assertTrue(worker.submit("command", (p.SET_DDS, b"")))
        self.assertFalse(worker.submit("command", (p.SET_DDS, b"")))
        worker.request_stop()
        self.assertTrue(worker.stop_requested.is_set())
        self.assertTrue(worker.cancel_capture.is_set())

    def test_wire_sample_and_metadata_validation_remains_enforced(self):
        for rate, trigger, word in [(0, 0, 1), (25000000, 2, 1), (25000000, 0, 0x1000),
                                    (125000001, 0, 1)]:
            with self.subTest(rate=rate, trigger=trigger, word=word):
                worker = ui.SerialWorker("FAKE", 115200)
                link = FakeSerial(np.zeros(2, dtype=np.uint16))
                def write(wire):
                    request = p.Parser().feed(wire)[0]
                    payload = struct.pack("<IIHH", 0, 2, word, 1)
                    link.buffer += p.encode(p.Frame(0xB0, request.sequence, 1234, rate, trigger,
                                                    p.RESPONSE|p.FIRST|p.LAST, payload))
                    return len(wire)
                link.write = write
                worker.link = link
                with self.assertRaises(ValueError):
                    worker.exchange(p.READ_WAVE, struct.pack("<II", 0, 2), wave=True)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])
        ui.configure_fonts(cls.app)

    def setUp(self):
        self.profile_directory = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.profile_directory.cleanup)
        self.profile_path = Path(self.profile_directory.name) / "hardware.json"
        self.window = ui.ScopeWindow(profile_path=self.profile_path)
        self.window.timer.stop()
        self.window.stop_capture()

    def tearDown(self):
        if self.window.worker:
            self.window.worker.shutdown.set()
            self.wait_for(lambda: self.window.worker is None)
        if self.window.csv_worker:
            self.wait_for(lambda: self.window.csv_worker is None)
        self.window.close()

    def wait_for(self, predicate, timeout=4):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def test_single_bram_capture_and_roi(self):
        w = self.window
        self.assertIn('16384', w.record.text())
        w.apply_record()
        w.single()
        self.assertEqual(len(w.current.words), 16384)
        self.assertFalse(w.running)
        self.assertFalse(w.single_pending)
        self.assertIsNone(w.roi_curve.xData)  # 隐藏页延迟绘制。
        w.tabs.setCurrentIndex(2)
        self.assertGreater(len(w.roi_curve.xData), 500)

    def test_fpga_summary_display_and_short_roi_keep_harmonics(self):
        from test_frozen_analysis import measurement_payload, spectrum_payload
        w = self.window
        measured = p.decode_measurement(p.Frame(0xb1,sample_rate=25000000,
                                                flags=p.RESPONSE,payload=bytes(measurement_payload())))
        spectral = p.decode_spectrum(p.Frame(0xb3,sample_rate=25000000,
                                             flags=p.RESPONSE,payload=bytes(spectrum_payload())))
        w.current = ui.Capture(np.full(16384,2047,dtype=np.uint16),25000000,8192,123456,
                               '硬件 UART',fpga_measurement=measured,fpga_spectrum=spectral)
        w.render_current()
        self.assertAlmostEqual(w.current_measurement()['rms'],.5*ui.SCALE)
        self.assertIn('FPGA 整帧测量',w.summary.text())
        w.tabs.setCurrentIndex(1)
        self.assertEqual(w.fft_size.text(), '1024 点 · 固定')
        self.assertEqual(len(w.fft_curve.yData),513)
        self.assertIn('H5',w.fft_info.text())
        w.current = ui.Capture(np.full(512,2047,dtype=np.uint16),25000000,256,123456,
                               '硬件 UART',fpga_measurement=measured,fpga_spectrum=spectral)
        w.render_spectrum()
        self.assertIsNone(w.fft_curve.yData)
        self.assertIn('H5',w.fft_info.text())
        self.assertIn('不足 1024 点',w.fft_info.text())

    def test_roi_window_export_preserves_full_record_identity(self):
        worker = ui.SerialWorker('unused', 921600)
        worker.link = FakeSerial(np.full(16384, 2047, dtype=np.uint16))
        frame = worker.capture(1, preview_points=1024)
        self.assertEqual((frame.record_length, frame.record_offset), (16384, 7680))
        self.window.current = frame
        exported = self.window.report_measurement()
        self.assertEqual(exported['record_length'], 16384)
        self.assertEqual(exported['read_samples'], 1024)
        self.assertEqual(exported['trigger_index'], 8192)
        self.assertEqual(exported['timestamp'], frame.timestamp - 7680)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'roi.csv'
            ui.CsvExportWorker(path, frame).run()
            with path.open(encoding='utf-8-sig', newline='') as stream:
                metadata = next(csv.reader(stream))
            self.assertEqual(metadata[metadata.index('record_length')+1], '16384')
            self.assertEqual(metadata[metadata.index('record_offset')+1], '7680')
            self.assertEqual(metadata[metadata.index('scope')+1], 'raw-roi')





    def test_hardware_source_reads_full_frames_without_fitting_or_dds_override(self):
        w = self.window
        self.assertEqual([w.source.itemText(i) for i in range(w.source.count())], ['演示模式', '硬件串口'])
        w.source.setCurrentIndex(1)
        w.receive_capture(w.demo_capture(force=True))
        self.assertIsNone(w.current)
        w.port.clear()
        w.port.addItem('TEST', 'TEST')
        phase = 2*np.pi*100000*np.arange(16384)/25000000
        def words(amplitude):
            return np.rint(4095-(amplitude*np.sin(phase)+.027+5)/ui.SCALE).astype(np.uint16)
        link = HandshakeSerial(words(.12))
        with patch.object(ui.serial, 'Serial', return_value=link):
            w.toggle_connect()
            self.wait_for(lambda: w.hardware_connected and w._commands_pending == 0)
            w.single()
            self.wait_for(lambda: w.current is not None and not w.capture_busy)
            first = w.current
            self.assertEqual(len(first.words), 16384)
            self.assertEqual(first.record_offset, 0)
            self.assertTrue(w.trigger_box.isEnabled())
            self.assertFalse(hasattr(w, 'link_curve'))
            link.words = words(.24)
            w.single()
            self.wait_for(lambda: w.current is not first and not w.capture_busy)
            self.assertAlmostEqual(np.ptp(w.current.volts())/np.ptp(first.volts()), 2, delta=.04)
            self.assertFalse(any(r.kind == p.SET_DDS for r in link.requests))
            self.assertTrue(all(struct.unpack('<II', r.payload) == (0,16384)
                                for r in link.requests if r.kind == p.READ_WAVE))
            w.toggle_connect()
            self.wait_for(lambda: w.worker is None)

    def test_profile_saves_acknowledged_snapshot_not_later_edits(self):
        w = self.window
        w.source.setCurrentIndex(1)
        w.hardware_connected = True
        w.threshold.setValue(.010)
        w.hysteresis.setValue(.005)
        queued = Mock()
        queued.submit.return_value = True
        with patch.object(w, "worker", queued):
            w.apply_trigger()
            self.assertFalse(self.profile_path.exists())
            kind, payload = queued.submit.call_args.args[1]
            w.threshold.setValue(.4)  # Draft edit while the request is in flight.
            w.remember_confirmed_command(kind, payload)
            saved = ui.read_hardware_profile(self.profile_path)
            self.assertEqual(saved["trigger"]["threshold"], .010)
            self.assertEqual(saved["trigger"]["hysteresis"], .005)
            original = self.profile_path.read_bytes()
            w.apply_trigger()
            kind, payload = queued.submit.call_args.args[1]
            with patch.object(ui.os, "replace", side_effect=PermissionError("locked")):
                w.remember_confirmed_command(kind, payload)
            self.assertEqual(self.profile_path.read_bytes(), original)
            self.assertFalse(list(self.profile_path.parent.glob(".scope-profile-*.tmp")))

    def test_profile_survives_reopen_and_cold_reconnect_without_enabling_dds(self):
        trigger = {**self.window.trigger_config(), "threshold": .010, "hysteresis": .005}
        dds = {**self.window.dds_config(), "amplitude": .1}
        self.profile_path.write_text(json.dumps({"format": "scope-ui-hardware-v1",
                                               "trigger": trigger, "dds": dds}), encoding="utf-8")
        w = ui.ScopeWindow(profile_path=self.profile_path)
        w.timer.stop()
        w.stop_capture()
        try:
            w.source.setCurrentIndex(1)
            self.assertEqual(w.threshold.value(), .010)
            self.assertEqual(w.hysteresis.value(), .005)
            self.assertEqual(w.dds_amplitude.value(), 10)
            w.port.clear()
            w.port.addItem("TEST", "TEST")
            for build_id in (0x20261022, 0x20261024):
                link = HandshakeSerial(np.zeros(16384, dtype=np.uint16), build_id=build_id)
                with patch.object(ui.serial, "Serial", return_value=link):
                    w.toggle_connect()
                    self.wait_for(lambda: w.hardware_connected and w._commands_pending == 0)
                    requests = [r for r in link.requests if r.kind == p.SET_TRIGGER]
                    self.assertEqual(requests, [])
                    self.assertFalse(any(r.kind == p.SET_DDS for r in link.requests))
                    self.assertIn("板端 DDS 未启用", w.logs.toPlainText())
                    w.toggle_connect()
                    self.wait_for(lambda: w.worker is None)
        finally:
            if w.worker:
                w.worker.shutdown.set()
                self.wait_for(lambda: w.worker is None)
            w.close()

    def test_local_owner_is_explicit_and_does_not_look_like_uart_timeout(self):
        class LocalSerial(HandshakeSerial):
            def write(self, wire):
                request=p.Parser().feed(wire)[0]
                self.requests.append(request)
                self.buffer+=p.encode(p.Frame(request.kind|128,request.sequence,
                    flags=p.RESPONSE|p.ERROR,payload=b'\x06'))
                return len(wire)
        worker=ui.SerialWorker('TEST',921600)
        worker.link=LocalSerial(np.zeros(16384,dtype=np.uint16))
        with self.assertRaises(ui.LocalControlActive):worker.exchange(p.PING,b'SCOPE_UI')
        self.assertTrue(worker.panel_owns_control)
        w=self.window
        w.source.setCurrentIndex(1)
        w.running=True
        w.handle_local_control();w.handoff_timer.stop()
        self.assertFalse(w.running)
        self.assertTrue(w._handoff_resume)
        self.assertIn('显示屏控制',w.state_label.text())

    def test_backend_readback_updates_controls_without_writing_settings(self):
        w=self.window
        w.source.setCurrentIndex(1)
        cfg={'length':16384,'pre':4096,
             'trigger':struct.pack('<BBhHhhIIHI',1,0,12,8,-100,100,25,2500,200,256)}
        queued=Mock()
        with patch.object(w,'worker',queued):
            w.receive_backend_configuration((cfg,1))
            self.assertEqual(w.trigger_type.currentIndex(),1)
            self.assertAlmostEqual(w.threshold.value(),12.5*ui.SCALE,places=5)
            self.assertEqual(w.acquisition_mode.currentIndex(),1)
            queued.submit.assert_not_called()

    def test_rejected_trigger_never_overwrites_confirmed_profile(self):
        class RejectTrigger(HandshakeSerial):
            def write(self, wire):
                request = p.Parser().feed(wire)[0]
                if request.kind == p.SET_TRIGGER:
                    self.requests.append(request)
                    self.buffer += p.encode(p.Frame(request.kind | 0x80, request.sequence,
                                                    flags=p.RESPONSE | p.ERROR, payload=b"\x02"))
                    return len(wire)
                return super().write(wire)

        w = self.window
        saved = {"format": "scope-ui-hardware-v1", "trigger": w.trigger_config()}
        self.profile_path.write_text(json.dumps(saved), encoding="utf-8")
        before = self.profile_path.read_bytes()
        w.source.setCurrentIndex(1)
        w.port.clear()
        w.port.addItem("TEST", "TEST")
        link = RejectTrigger(np.zeros(16384, dtype=np.uint16))
        with patch.object(ui.serial, "Serial", return_value=link):
            w.toggle_connect()
            self.wait_for(lambda: w.hardware_connected)
            w.threshold.setValue(.020)
            w.apply_trigger()
            self.wait_for(lambda: "固件拒绝命令" in w.logs.toPlainText() and w._commands_pending == 0)
            self.assertEqual(self.profile_path.read_bytes(), before)
            self.assertEqual(w._profile_requests, {})
            w.toggle_connect()
            self.wait_for(lambda: w.worker is None)

    def test_profile_rejects_corruption_and_demo_never_saves_hardware(self):
        w = self.window
        w.apply_trigger()
        w.apply_dds()
        self.assertFalse(self.profile_path.exists())
        trigger = w.trigger_config()
        for change in ({"threshold": float("nan")}, {"kind": True}, {"hysteresis": 20}):
            data = {"format": "scope-ui-hardware-v1", "trigger": {**trigger, **change}}
            self.profile_path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                ui.read_hardware_profile(self.profile_path)
        self.profile_path.write_text("broken JSON", encoding="utf-8")
        reopened = ui.ScopeWindow(profile_path=self.profile_path)
        reopened.timer.stop()
        try:
            self.assertIn("未载入硬件参数", reopened.logs.toPlainText())
            reopened.source.setCurrentIndex(1)
            self.assertEqual(reopened.threshold.value(), 0)
        finally:
            reopened.close()

    def test_autoscale_undo_and_calibration_does_not_modify_raw(self):
        w = self.window
        before = (w.timebase.currentIndex(), w.volts_div.currentIndex(), w.threshold.value())
        raw = w.current.words.copy()
        w.autoscale()
        self.assertTrue(w.undo_button.isEnabled())
        w.undo_autoscale()
        self.assertEqual(before, (w.timebase.currentIndex(), w.volts_div.currentIndex(), w.threshold.value()))
        w.start_calibration()
        w.cal_timer.stop()
        for _ in range(7):
            w.calibration_tick()
        self.assertAlmostEqual(w.calibration["offset"], 0.027, delta=0.001)
        self.assertAlmostEqual(w.calibration["gain"], 0.973, delta=0.001)
        w.apply_cal.setChecked(True)
        np.testing.assert_array_equal(w.current.words, raw)
        self.assertNotIn("sinad",w.calibration)
        self.assertTrue(np.isfinite(w.calibration["noise"]))

    def test_calibration_results_remain_separate_with_large_fonts_and_small_windows(self):
        w = self.window
        w.tabs.setCurrentIndex(3)
        w.show()
        for font_size in (12, 18):
            w.setStyleSheet(ui.STYLE + f"\nQWidget {{ font-size:{font_size}px; }}")
            for width, height in ((1480, 940), (1120, 760)):
                with self.subTest(font=font_size, window=(width, height)):
                    w.resize(width, height)
                    for row in range(7):
                        w.cal_table.item(row, 1).setText("完成 · 排版验证")
                        w.cal_table.item(row, 2).setText(
                            "组合链路噪声 1.894 mV RMS；H2 0.101 mV；H3 0.040 mV；"
                            "相对校准系数就绪，原 DDS 与触发配置已恢复。")
                    w.cal_comparison_note.setText("独立复测，同一原始帧，仅改变显示换算；" * 4)
                    w.cal_result.setText("完成后的长结果说明，需要随窗口宽度自动换行并显示完整。" * 4)
                    for _ in range(20):
                        self.app.processEvents()
                    widgets = [w.cal_progress, w.cal_table, w.cal_comparison_note,
                               w.cal_comparison, w.response_plot, w.cal_result]
                    for previous, following in zip(widgets, widgets[1:]):
                        self.assertGreaterEqual(following.y(), previous.geometry().bottom()+8)
                    for label in (w.cal_note, w.absolute_status, w.cal_comparison_note, w.cal_result):
                        self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
                    for table in (w.cal_table, w.cal_comparison):
                        last_row = table.rowCount()-1
                        self.assertLessEqual(table.rowViewportPosition(last_row)+table.rowHeight(last_row),
                                             table.viewport().height())
                        self.assertEqual(table.verticalScrollBar().maximum(), 0)
                    scroll = w.tabs.widget(3)
                    self.assertLess(w.cal_result.geometry().bottom(), scroll.widget().height())
                    self.assertGreater(scroll.verticalScrollBar().maximum(), 0)

    def test_calibration_table_fits_after_result_text_changes(self):
        w = self.window
        w.tabs.setCurrentIndex(3)
        w.show()
        for _ in range(15):
            self.app.processEvents()
        original_height = w.cal_table.height()
        w.cal_table.item(5, 2).setText("长结果说明，原始数据保留，参数已经恢复。" * 30)
        self.wait_for(lambda: w.cal_table.height() > original_height)
        w.cal_table.item(5, 2).setText("完成")
        self.wait_for(lambda: w.cal_table.height() == original_height)

    def test_trigger_payload_and_invalid_window(self):
        w = self.window
        self.assertEqual(len(w.trigger_payload(w.trigger_config())), 24)
        w.trigger_type.setCurrentIndex(2)
        w.win_low.setValue(1)
        w.win_high.setValue(-1)
        with self.assertRaises(ValueError):
            w.trigger_payload(w.trigger_config())

    def test_voltage_units_preserve_values_signals_and_protocol(self):
        w = self.window
        w.threshold.setValue(.011)
        before = w.trigger_payload(w.trigger_config())
        changes = []
        w.threshold.valueChanged.connect(changes.append)
        fields = [w.display_center, w.threshold, w.hysteresis, w.win_low, w.win_high, w.amp_limit]
        for field in fields:
            expected = field.value()
            self.assertEqual(field.unit_combo.currentText(), "mV")
            for _ in range(10):
                field.unit_combo.setCurrentText("V")
                self.assertAlmostEqual(field.spinbox.value(), expected)
                field.unit_combo.setCurrentText("mV")
                self.assertAlmostEqual(field.spinbox.value(), expected*1000)
            self.assertEqual(field.value(), expected)
        self.assertEqual(changes, [])
        self.assertEqual(w.trigger_payload(w.trigger_config()), before)
        self.assertAlmostEqual(w.level_line.value(), .011)

    def test_voltage_steps_and_display_center_use_selected_unit(self):
        w = self.window
        w.threshold.setValue(.011)
        w.threshold.spinbox.stepUp()
        self.assertEqual(w.threshold.value(), .012)
        self.assertAlmostEqual(w.level_line.value(), .012)
        w.threshold.unit_combo.setCurrentText("V")
        w.threshold.spinbox.stepUp()
        self.assertEqual(w.threshold.value(), 1.012)
        w.display_center.spinbox.setValue(25)
        low, high = w.wave_plot.viewRange()[1]
        self.assertAlmostEqual((low+high)/2, .025)
        w.win_low.setEnabled(False)
        self.assertFalse(w.win_low.spinbox.isEnabled())
        self.assertFalse(w.win_low.unit_combo.isEnabled())

    def test_switching_voltage_unit_commits_pending_input_in_old_unit(self):
        field = self.window.threshold
        field.spinbox.lineEdit().setText("12.345")
        field.unit_combo.setCurrentText("V")
        self.assertAlmostEqual(field.value(), .012345)
        self.assertAlmostEqual(field.spinbox.value(), .012345)

    def test_cursor_and_source_boundary(self):
        w = self.window
        w.cursor_time.setChecked(True)
        w.cursor_volt.setChecked(True)
        self.assertIn("Δt", w.cursor_readout.text())
        self.assertIn("ΔV", w.cursor_readout.text())
        w.source.setCurrentIndex(1)
        self.assertIsNone(w.current)
        self.assertFalse(w.cal_button.isEnabled())
        self.assertFalse(hasattr(w, 'demo_rate'))
        self.assertTrue(w.glitch.isHidden())
        self.assertEqual(w.metrics["vpp"].text(), "—")

    def test_export_raw_csv_and_screenshot(self):
        w = self.window
        output = ROOT / "tmp" / "ui-check"
        output.mkdir(parents=True, exist_ok=True)
        csv_path = output / "capture.csv"
        png_path = output / "capture.png"
        csv_path.unlink(missing_ok=True)
        w.show()
        self.app.processEvents()
        with patch.object(ui.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(csv_path), "CSV")):
            w.export_csv()
        self.wait_for(lambda: w.csv_worker is None)
        with patch.object(ui.QtWidgets.QFileDialog, "getSaveFileName", return_value=(str(png_path), "PNG")):
            w.export_png()
        text = csv_path.read_text(encoding="utf-8-sig")
        self.assertIn("raw_code_12bit", text)
        self.assertEqual(len(text.splitlines()), len(w.current.words)+2)
        self.assertGreater(png_path.stat().st_size, 10000)

    def test_refresh_preserves_zoom_roi_and_skips_hidden_fft(self):
        w = self.window
        w.wave_plot.setXRange(1e-6, 3e-6, padding=0)
        expected = w.wave_plot.viewRange()[0]
        with patch.object(ui, "spectrum", wraps=ui.spectrum) as calculate:
            w.receive_capture(w.demo_capture(force=True))
            self.assertEqual(calculate.call_count, 0)
            self.assertEqual(w.wave_plot.viewRange()[0], expected)
            w.tabs.setCurrentIndex(1)
            self.assertEqual(calculate.call_count, 1)
        w.tabs.setCurrentIndex(2)
        w.roi_region.setRegion((-4e-6, 7e-6))
        w.render_roi()
        expected = w.roi_region.getRegion()
        w.receive_capture(w.demo_capture(force=True))
        self.assertEqual(w.roi_region.getRegion(), expected)

    def test_late_hardware_frame_and_cross_source_frame_are_dropped(self):
        w = self.window
        raw = w.current.words
        hardware = ui.Capture(raw, 25000000, 8192, 50, "硬件 UART")
        old = w.current
        w.receive_capture(hardware)
        self.assertIs(w.current, old)
        w.source.setCurrentIndex(1)
        w.hardware_connected = True
        w.receive_capture(hardware)
        self.assertIsNone(w.current)
        w.single_pending = True
        w.receive_capture(hardware)
        self.assertIs(w.current, hardware)
        w.stop_capture()
        w.receive_capture(ui.Capture(raw, 25000000, 8192, 100, "硬件 UART"))
        self.assertIs(w.current, hardware)

    def test_export_locks_frame_before_dialog_and_does_not_block(self):
        w = self.window
        initial = w.current
        path = ROOT / "tmp/ui-check/locked.csv"
        def select_path(*args):
            w.receive_capture(w.demo_capture(force=True))
            return str(path), "CSV"
        with patch.object(ui.QtWidgets.QFileDialog, "getSaveFileName", side_effect=select_path):
            w.export_csv()
        self.assertIsNotNone(w.csv_worker)
        self.wait_for(lambda: w.csv_worker is None)
        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file))
        self.assertEqual(int(rows[0][7]), initial.timestamp)
        self.assertEqual(int(rows[2][2]), int(initial.words[0]))

    def test_malformed_fingerprint_preserves_baseline_and_sampling(self):
        w = self.window
        path = ROOT / "tmp/ui-check/bad-fingerprint.json"
        w.baseline = dict(offset=0, gain=1, noise=.001)
        baseline = w.baseline.copy()
        w.set_running(True)
        cases = [{"offset": "0.1", "gain": 1, "noise": .01},
                 {"offset": 0, "gain": float("nan"), "noise": .01},
                 {"offset": 0, "gain": 0, "noise": .01},
                 {"offset": 0, "gain": 1, "noise": -1}]
        for values in cases:
            path.write_text(json.dumps(dict(format="scope-ui-fingerprint-v1", source="software-demo", calibration=values)), encoding="utf-8")
            with patch.object(ui.QtWidgets.QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
                w.load_fingerprint()
            self.assertEqual(w.baseline, baseline)
            self.assertTrue(w.running)

    def test_failed_export_preserves_previous_file_and_cleans_temporary(self):
        w = self.window
        path = ROOT / "tmp/ui-check/atomic.csv"
        path.write_text("original", encoding="utf-8")
        worker = ui.CsvExportWorker(path, w.current)
        failures = []
        worker.failed.connect(failures.append)
        with patch.object(ui.os, "replace", side_effect=PermissionError("locked")):
            worker.run()
        self.assertEqual(path.read_text(encoding="utf-8"), "original")
        self.assertEqual(len(failures), 1)
        self.assertEqual(list(path.parent.glob(".scope-*.tmp")), [])

    def test_threaded_connection_command_capture_and_disconnect(self):
        w = self.window
        w.source.setCurrentIndex(1)
        w.port.clear()
        w.port.addItem("TEST", "TEST")
        link = HandshakeSerial(np.arange(16384, dtype=np.uint16) % 4096)
        with patch.object(ui.serial, "Serial", return_value=link):
            w.toggle_connect()
            self.wait_for(lambda: w.hardware_connected)
            w.apply_trigger()
            self.assertEqual(w._commands_pending, 1)
            w.set_running(True)
            self.assertFalse(w.running)
            self.wait_for(lambda: w._commands_pending == 0)
            w.single()
            self.wait_for(lambda: w.current is not None and not w.capture_busy)
            self.assertEqual(w.current.source, "硬件 UART")
            w.toggle_connect()
            self.wait_for(lambda: w.worker is None)
            self.assertFalse(w.hardware_connected)
            self.assertFalse(link.is_open)

    def test_close_does_not_wait_on_gui_thread(self):
        w = self.window
        w.source.setCurrentIndex(1)
        w.port.clear()
        w.port.addItem("TEST", "TEST")
        link = HandshakeSerial(np.zeros(16384, dtype=np.uint16))
        with patch.object(ui.serial, "Serial", return_value=link):
            w.toggle_connect()
            self.wait_for(lambda: w.hardware_connected)
            with patch.object(w.worker, "wait", side_effect=AssertionError("GUI must not block")):
                event = ui.QtGui.QCloseEvent()
                w.closeEvent(event)
                self.assertFalse(event.isAccepted())
                self.wait_for(lambda: w.worker is None)

    def test_fingerprint_size_and_encoding_limits(self):
        path = ROOT / "tmp/ui-check/oversized.json"
        for content in (b"x"*(1024*1024+1), b"\xff\xfe"):
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                ui.read_fingerprint(path)

    def test_unfocused_wheel_does_not_edit_parameters(self):
        w = self.window
        for control in (w.dds_amplitude, w.dds_offset, w.dds_wave):
            control.clearFocus()
            before = control.currentIndex() if isinstance(control, ui.QtWidgets.QComboBox) else control.value()
            event = ui.QtGui.QWheelEvent(ui.QtCore.QPointF(4, 4), ui.QtCore.QPointF(4, 4),
                                        ui.QtCore.QPoint(0, 0), ui.QtCore.QPoint(0, 120),
                                        ui.QtCore.Qt.MouseButton.NoButton, ui.QtCore.Qt.KeyboardModifier.NoModifier,
                                        ui.QtCore.Qt.ScrollPhase.NoScrollPhase, False)
            control.wheelEvent(event)
            after = control.currentIndex() if isinstance(control, ui.QtWidgets.QComboBox) else control.value()
            self.assertEqual(before, after)
            self.assertFalse(event.isAccepted())


if __name__ == "__main__":
    unittest.main()
