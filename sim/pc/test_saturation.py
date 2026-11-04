from dataclasses import replace
import struct
import unittest
from test_scope_ui import ui,FakeSerial
p,np=ui.proto,ui.np

def response(samples=0,events=0,diagnostic=False,timestamp=123456):
    return p.Frame(0xb4,timestamp=timestamp,sample_rate=25000000,trigger_index=8192,
        flags=p.RESPONSE,payload=struct.pack('<BBHIII',1,1|int(diagnostic)*2,0,16384,samples,events))

class SaturationSerial(FakeSerial):
    mismatch=False
    def write(self,wire):
        request=p.Parser().feed(wire)[0]
        if request.kind==p.READ_SATURATION:
            self.requests.append(request)
            f=replace(response(8,2,True,123457 if self.mismatch else 123456),sequence=request.sequence)
            self.buffer+=p.encode(f);return len(wire)
        return super().write(wire)

class SaturationTest(unittest.TestCase):
    def test_strict_decoder(self):
        for samples,events in ((0,0),(1,1),(16384,1),(8192,8192),(16383,2)):
            self.assertEqual(p.decode_saturation(response(samples,events))['saturated_samples'],samples)
        for samples,events in ((0,1),(1,0),(16385,1),(16384,2),(10,11)):
            with self.assertRaises(ValueError):p.decode_saturation(response(samples,events))
        f=response()
        for offset,value in ((0,2),(1,0),(1,5),(2,1),(4,1)):
            b=bytearray(f.payload);b[offset]=value
            with self.assertRaises(ValueError):p.decode_saturation(replace(f,payload=bytes(b)))

    def test_worker_reads_full_frame_count_with_preview(self):
        worker=ui.SerialWorker('unused',921600);worker.capabilities=p.CAP_SATURATION
        worker.link=SaturationSerial(np.full(16384,2047,dtype=np.uint16))
        frame=worker.capture(1,preview_points=128)
        self.assertEqual(len(frame.words),128)
        self.assertEqual(frame.fpga_saturation,{'count':16384,'saturated_samples':8,'events':2,'diagnostic':True})
        self.assertEqual(worker.link.requests[-1].kind,p.READ_SATURATION)

    def test_worker_rejects_stale_count(self):
        worker=ui.SerialWorker('unused',921600);worker.capabilities=p.CAP_SATURATION
        worker.link=SaturationSerial(np.full(16384,2047,dtype=np.uint16));worker.link.mismatch=True
        emitted=[];worker.frame_ready.connect(emitted.append)
        with self.assertRaisesRegex(ValueError,'身份不匹配'):worker.capture(1)
        self.assertFalse(emitted)

class SaturationUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])
    def test_summary_replaces_alarm_and_does_not_count_preview(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            w=ui.ScopeWindow(profile_path=Path(folder)/'profile.json');w.timer.stop();w.set_running(False)
            frame=ui.Capture(np.full(1024,2047,dtype=np.uint16),25000000,512,123,'硬件 UART',
                fpga_saturation={'count':16384,'saturated_samples':7000,'events':12,'diagnostic':True})
            w.current=frame;w.render_current()
            text=w.saturation_label.text()
            self.assertIn('7,000 / 16,384',text);self.assertIn('12',text);self.assertIn('诊断帧',text)
            self.assertNotIn('OTR',text);self.assertNotIn('ROI',text)
            w.current=replace(frame,fpga_saturation=None);w.render_current()
            self.assertIn('需要支持整帧计数',w.saturation_label.text())
            w.close();w.deleteLater();self.app.processEvents()

if __name__=='__main__':unittest.main()
