"""Wire-level summary validation, frame identity, and display provenance."""
from dataclasses import replace
import struct
import unittest
from test_scope_ui import ui, FakeSerial

p,np=ui.proto,ui.np

def measurement_payload():
    data=bytearray(64)
    data[0]=1
    struct.pack_into('<IhhhHH',data,4,16384,0,0,0,0,0)
    return data

def spectrum_payload():
    data=bytearray(96)
    data[:8]=bytes((1,1,0,0,0,4,1,0))
    struct.pack_into('<H',data,12,41)
    struct.pack_into('<IIIi',data,16,(41*25000000+512)//1024,100<<16,71<<16,0)
    for h in range(2,6):
        struct.pack_into('<BBHIII',data,32+(h-2)*16,h,1,41*h,(41*h*25000000+512)//1024,2<<16,0)
    return data

class AnalysisSerial(FakeSerial):
    mismatch=False
    def write(self,wire):
        request=p.Parser().feed(wire)[0]
        if request.kind in (p.READ_MEASURE,p.READ_SPECTRUM):
            payload=measurement_payload() if request.kind==p.READ_MEASURE else spectrum_payload()
            self.requests.append(request)
            self.buffer+=p.encode(p.Frame(request.kind|128,request.sequence,123457 if self.mismatch else 123456,
                                         25000000,8192,p.RESPONSE,bytes(payload)))
            return len(wire)
        return super().write(wire)

class FrozenAnalysisTests(unittest.TestCase):
    def test_decode_geometry_and_corruption(self):
        payload=spectrum_payload()
        frame=p.Frame(0xb3,sample_rate=25000000,flags=p.RESPONSE,payload=bytes(payload))
        result=p.decode_spectrum(frame)
        self.assertEqual(result['n'],1024)
        self.assertEqual(result['harmonics'][1]['order'],3)
        for offset,value in ((0,2),(5,8),(6,0),(14,1),(32,5),(33,0),(47,1)):
            bad=payload.copy();bad[offset]=value
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                p.decode_spectrum(replace(frame,payload=bytes(bad)))
        measured=p.Frame(0xb1,sample_rate=25000000,flags=p.RESPONSE,payload=bytes(measurement_payload()))
        self.assertEqual(p.decode_measurement(measured)['count'],16384)
        bad=bytearray(measured.payload);bad[18]=1
        with self.assertRaises(ValueError):p.decode_measurement(replace(measured,payload=bytes(bad)))

    def test_worker_attaches_matching_hardware_summary(self):
        worker=ui.SerialWorker('FAKE',921600)
        worker.link=AnalysisSerial(np.full(16384,2047,dtype=np.uint16))
        worker.capabilities=7
        frame=worker.capture(1)
        self.assertEqual(frame.fpga_measurement['count'],16384)
        self.assertEqual(frame.fpga_spectrum['peak_bin'],41)
        self.assertEqual([r.kind for r in worker.link.requests][-2:],[p.READ_MEASURE,p.READ_SPECTRUM])

    def test_worker_rejects_stale_summary_before_publishing_frame(self):
        worker=ui.SerialWorker('FAKE',921600)
        worker.link=AnalysisSerial(np.full(16384,2047,dtype=np.uint16))
        worker.link.mismatch=True;worker.capabilities=7
        emitted=[];worker.frame_ready.connect(emitted.append)
        with self.assertRaisesRegex(ValueError,'身份不匹配'):worker.capture(1)
        self.assertFalse(emitted)
