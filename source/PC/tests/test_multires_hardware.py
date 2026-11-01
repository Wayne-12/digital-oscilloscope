"""Hardware-mode byte transport and UI contract; all fixtures are explicitly simulated."""
from dataclasses import replace
import csv
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_scope_ui import ui, HandshakeSerial

np, p = ui.np, ui.proto


def fixture_words():
    raw = np.rint(2047-40*np.sin(2*np.pi*np.arange(16384)/250)).astype(np.uint16)
    raw[0] = 0x8fff  # OTR and one-point negative spike, outside the default ROI
    raw[-1] = 0  # positive spike at the final sample
    return raw


def envelope_packets(words, sequence=0, count=800, base=123456):
    entries = []
    for i in range(count):
        block = words[i*len(words)//count:(i+1)*len(words)//count]
        signed = 2047-(block & 4095).astype(np.int32)
        entries.append((int(signed.min()), int(signed.max()), int(bool(np.any(block & 32768)))))
    packets = []
    for k, start in enumerate(range(0, count, 202)):
        data = entries[start:start+202]
        flags = p.RESPONSE | (p.FIRST if start == 0 else 0) | (p.LAST if start+len(data) == count else p.MORE)
        payload = struct.pack('<IIHH', start, len(words), count, 1)
        payload += b''.join(struct.pack('<hhB', *b) for b in data)
        packets.append(p.Frame(0xb2, (sequence+k)&65535, base, 25000000, 8192, flags, payload))
    return entries, packets


class MultiSerial(HandshakeSerial):
    def __init__(self, words):
        super().__init__(words, build_id=0xa0261024)
        self.base = 123456
        self.wire_bytes = 0

    def write(self, wire):
        request = p.Parser().feed(wire)[0]
        if request.kind not in (p.GET_CAPABILITIES, p.READ_ENVELOPE, p.READ_WAVE):
            return super().write(wire)
        self.requests.append(request)
        if request.kind == p.GET_CAPABILITIES:
            packets = [p.Frame(0x84, request.sequence, flags=p.RESPONSE, payload=struct.pack('<IHH',1,800,2048))]
        elif request.kind == p.READ_ENVELOPE:
            _, packets = envelope_packets(self.words,request.sequence,struct.unpack('<H',request.payload)[0],self.base)
        else:
            offset, count = struct.unpack('<II', request.payload)
            packets = []
            for k,start in enumerate(range(offset,offset+count,508)):
                raw = self.words[start:min(start+508,offset+count)]
                flags = p.RESPONSE | (p.FIRST if start == offset else 0) | (p.LAST if start+len(raw) == offset+count else p.MORE)
                packets.append(p.Frame(0xb0,(request.sequence+k)&65535,(self.base+start)&((1<<64)-1),
                                       25000000,8192,flags,struct.pack('<II',start,len(self.words))+raw.astype('<u2').tobytes()))
        for packet in packets:
            data = p.encode(packet)
            self.buffer += data
            self.wire_bytes += len(data)
        return len(wire)


class HardwareMultiresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])

    def worker_and_frame(self):
        worker = ui.SerialWorker('SIMULATED',921600)
        link = MultiSerial(fixture_words())
        worker.link = link
        worker.capabilities = 1
        frames = []
        worker.frame_ready.connect(frames.append,ui.QtCore.Qt.ConnectionType.DirectConnection)
        worker.capture(2,None,800)
        return worker,link,frames[-1]

    def test_fragmented_compact_transfer_retains_spikes_and_otr(self):
        worker,link,frame = self.worker_and_frame()
        self.assertEqual(len(frame.words),2048)
        self.assertEqual(frame.record_offset,7168)
        self.assertEqual(frame.overview.length,16384)
        self.assertEqual(len(frame.overview.buckets),800)
        self.assertEqual(frame.overview.buckets[0][0],-2048)
        self.assertEqual(frame.overview.buckets[0][2],1)
        self.assertEqual(frame.overview.buckets[-1][1],2047)
        self.assertTrue(ui.capture_clipped(frame))
        np.testing.assert_array_equal(frame.words,link.words[7168:9216])
        self.assertEqual(link.wire_bytes,4160+4276)
        self.assertEqual([struct.unpack('<II',r.payload) for r in link.requests if r.kind==p.READ_WAVE],[(7168,2048)])
        self.assertFalse(any(worker.parser.errors.values()))

    def test_capability_marker_and_legacy_no_probe(self):
        for build,expected in ((0xa0261024,1),(0x20261024,0)):
            worker = ui.SerialWorker('SIMULATED',921600)
            link = MultiSerial(fixture_words()) if expected else HandshakeSerial(fixture_words(),build)
            with patch.object(ui.serial,'Serial',return_value=link):
                worker.open_link()
            self.assertEqual(worker.capabilities,expected)
            self.assertEqual(sum(r.kind==p.GET_CAPABILITIES for r in link.requests),expected)
            self.assertFalse(any(r.kind==p.SET_DDS for r in link.requests))

    def test_roi_outside_trigger_and_stale_frame_rejected(self):
        worker,link,frame = self.worker_and_frame()
        for start,count in ((0,512),(10000,1601),(16384-2048,2048)):
            roi = worker.read_roi(frame,start,count)
            self.assertEqual(roi.trigger,8192-start)
            np.testing.assert_array_equal(roi.words,link.words[start:start+count])
            np.testing.assert_array_equal(roi.times(),(np.arange(start,start+count)-8192)/25000000)
        link.base += 100000
        with self.assertRaises(ValueError):
            worker.read_roi(frame,0,512)
        self.assertEqual(sum(r.kind==p.SINGLE for r in link.requests),1)

    def test_cancelled_roi_sends_no_read_command(self):
        worker,link,frame = self.worker_and_frame()
        before = len(link.requests)
        worker.cancel_capture.set()
        # exchange checks cancellation after its write; prevent sending at entry, too.
        with self.assertRaises(InterruptedError):
            worker.read_roi(frame,0,512)
        self.assertEqual(len(link.requests),before)

    def test_parser_rejects_gaps_mixed_frames_formats_and_bad_samples(self):
        expected,packets = envelope_packets(fixture_words(),65535)
        assembly = p.EnvelopeAssembler(65535,800,16384)
        for frame in packets:
            result = assembly.accept(frame)
        self.assertEqual(result,expected)
        changes = [{'sequence':3},{'timestamp':9},{'sample_rate':0},{'trigger_index':16384},
                   {'flags':p.RESPONSE|p.FIRST|p.LAST},{'payload':packets[1].payload[:-1]},
                   {'payload':struct.pack('<IIHH',202,16384,800,2)+packets[1].payload[12:]},
                   {'payload':packets[1].payload[:12]+struct.pack('<hhB',-2049,1,0)+packets[1].payload[17:]},
                   {'payload':packets[1].payload[:12]+struct.pack('<hhB',2,1,0)+packets[1].payload[17:]},
                   {'payload':packets[1].payload[:12]+struct.pack('<hhB',-1,1,2)+packets[1].payload[17:]}]
        for change in changes:
            assembly = p.EnvelopeAssembler(65535,800,16384)
            assembly.accept(packets[0])
            with self.assertRaises(ValueError):
                assembly.accept(replace(packets[1],**change))

    def test_hardware_page_and_roi_history_never_fabricate_full_raw(self):
        worker,_link,frame = self.worker_and_frame()
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            w = ui.ScopeWindow(profile_path=Path(folder)/'profile.json')
            w.timer.stop()
            w.source.setCurrentIndex(1)
            w.hardware_connected = True
            w.single_pending = True
            w.receive_capture(frame)
            w.single_pending = False
            w.tabs.setCurrentIndex(2)
            self.assertIn('FPGA 实物包络',w.envelope_info.text())
            self.assertIn('来自 ROI',w.summary.text())
            self.assertIn('整帧饱和统计',w.saturation_label.text())
            self.assertNotIn('OTR',w.saturation_label.text())
            self.assertIn('需要支持整帧计数',w.saturation_label.text())
            self.assertEqual(len(w.env_curve.xData),1600)
            old = w.current
            w.roi_region.setRegion((-300e-6,-290e-6))
            w.render_roi()
            self.assertIsNone(w.roi_curve.yData)
            self.assertIn('未缓存',w.roi_status.text())
            w.worker = Mock()
            w.worker.submit.return_value = True
            w.worker.cancel_capture = worker.cancel_capture
            w.request_hardware_roi()
            self.assertTrue(w.roi_busy)
            args = w.worker.submit.call_args.args
            self.assertEqual(args[0],'roi')
            _,start,count = args[1]
            self.assertLessEqual(count,2048)
            roi = worker.read_roi(old,start,count)
            w.receive_roi(old,roi)
            w.roi_finished()
            self.assertIs(w.current,roi)
            self.assertIs(w.history[0][1],roi)
            self.assertEqual(w.capture_count,2)  # initial demo frame + one hardware acquisition
            w.device_frame_identity += 1
            w.request_hardware_roi()
            self.assertIn('历史帧',w.roi_status.text())
            w.worker = None
            w.close()

    def test_envelope_csv_exports_full_index_ranges_and_real_codes(self):
        _worker,_link,frame = self.worker_and_frame()
        with tempfile.TemporaryDirectory(dir=ui.ROOT/'tmp') as folder:
            path = Path(folder)/'envelope.csv'
            w = ui.ScopeWindow(profile_path=Path(folder)/'profile.json')
            w.timer.stop()
            w.current = frame
            with patch.object(ui.QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(path),'CSV')):
                w.export_envelope_csv()
            with path.open(encoding='utf-8-sig',newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows),802)
            self.assertEqual(rows[0][1],'FPGA envelope')
            self.assertEqual([int(v) for v in rows[2][1:6]],[0,19,*frame.overview.buckets[0]])
            self.assertEqual(int(rows[-1][2]),16383)
            self.assertAlmostEqual(float(rows[2][6]),(-2048+0.5)*ui.SCALE)
            w.close()


if __name__ == '__main__':
    unittest.main()
