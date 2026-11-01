"""Mode dispatch through the production worker and demo controls."""
import tempfile
from pathlib import Path
import time
import threading
import struct
import unittest
from test_scope_ui import ui, FakeSerial

p=ui.proto

class WorkerCaptureModesTest(unittest.TestCase):
    def test_continuous_dispatch_uses_run_and_release(self):
        worker=ui.SerialWorker('unused',921600)
        worker.link=FakeSerial(ui.np.full(16384,2047,dtype=ui.np.uint16))
        worker.capabilities=p.CAP_CAPTURE_MODES
        worker.capture(1,acquisition_mode=0)
        worker.capture(1,acquisition_mode=0)
        kinds=[r.kind for r in worker.link.requests]
        self.assertEqual(kinds.count(p.RUN),1)
        self.assertEqual(kinds.count(p.RELEASE_FRAME),1)
        self.assertNotIn(p.SINGLE,kinds)
        worker.capture(1,acquisition_mode=1)
        self.assertEqual(worker.link.requests[-3].kind,p.RUN)
        worker.capture(1)
        self.assertEqual(worker.stream_mode,None)
        self.assertEqual(worker.link.requests[-3].kind,p.SINGLE)

    def test_old_firmware_cannot_claim_auto(self):
        worker=ui.SerialWorker('unused',921600)
        with self.assertRaisesRegex(ValueError,'AUTO/NORMAL'):
            worker.capture(1,acquisition_mode=0)

    def test_normal_waits_until_manual_stop(self):
        class WaitingSerial(FakeSerial):
            def write(self,wire):
                request=p.Parser().feed(wire)[0]
                if request.kind!=p.GET_STATUS:
                    return super().write(wire)
                self.requests.append(request)
                payload=bytes([1,0,1,0])+struct.pack('<II9I',16384,8192,*([0]*9))
                self.buffer+=p.encode(p.Frame(0x83,request.sequence,sample_rate=25000000,
                    flags=p.RESPONSE,payload=payload))
                return len(wire)
        worker=ui.SerialWorker('unused',921600)
        worker.link=WaitingSerial(ui.np.full(16384,2047,dtype=ui.np.uint16))
        worker.capabilities=p.CAP_CAPTURE_MODES
        timer=threading.Timer(.05,worker.request_stop);timer.start()
        try:
            with self.assertRaises(InterruptedError):
                worker.capture(.001,acquisition_mode=1)
        finally:
            timer.cancel();timer.join()

class DemoCaptureModesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=ui.QtWidgets.QApplication.instance() or ui.QtWidgets.QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.window=ui.ScopeWindow(profile_path=Path(self.temp.name)/'profile.json')
        self.window.timer.stop()
        self.window.set_running(False)

    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.processEvents();self.temp.cleanup()

    def test_auto_times_out_and_normal_waits(self):
        w=self.window
        w.demo_trigger['threshold']=5
        w.acquisition_mode.setCurrentIndex(0)
        w.set_running(True);w.demo_wait_started=time.monotonic()-1
        before=w.capture_count;w.tick()
        self.assertEqual(w.capture_count,before+1)
        w.acquisition_mode.setCurrentIndex(1)
        w.demo_wait_started=time.monotonic()
        before=w.capture_count;w.tick()
        self.assertEqual(w.capture_count,before)
        self.assertTrue(w.running)

    def test_single_selection_runs_once(self):
        w=self.window
        w.acquisition_mode.setCurrentIndex(2)
        self.assertTrue(w.set_running(True))
        self.assertFalse(w.running);self.assertTrue(w.single_pending)
        before=w.capture_count;w.tick();w.tick()
        self.assertEqual(w.capture_count,before+1)
        self.assertFalse(w.single_pending)

if __name__=='__main__':unittest.main()
