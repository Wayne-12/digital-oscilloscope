import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
import scope_protocol as p

class CaptureModesTest(unittest.TestCase):
    def test_configuration_roundtrip(self):
        for mode in range(3):
            for ticks in (1,2500000,0xffffffff):
                payload=p.capture_mode_payload(mode,ticks)
                frame=p.Parser().feed(p.encode(p.Frame(0x93,flags=p.RESPONSE,payload=payload)))[0]
                self.assertEqual(p.decode_capture_configuration(frame),(mode,ticks))

    def test_invalid_fields(self):
        for mode,ticks in ((3,1),(-1,1),(0,0),(0,2**32),(True,1),(1,1.5)):
            with self.assertRaises(ValueError):p.capture_mode_payload(mode,ticks)
        payload=bytearray(p.capture_mode_payload(0));payload[2]=1
        with self.assertRaises(ValueError):p.decode_capture_configuration(p.Frame(0x93,flags=p.RESPONSE,payload=payload))

if __name__=='__main__':unittest.main()
