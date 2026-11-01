import sys,unittest,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
from scope_protocol import *
class CodecTests(unittest.TestCase):
    def test_crc_vectors(self):
        for message,value in ((b'',0xffff),(b'123456789',0x29b1),(b'abc',0x514a)):
            self.assertEqual(crc16(message),value)
    def test_fragmented_and_magic_payload(self):
        f=Frame(PING,65535,(1<<64)-1,65000000,131071,0,b'\x55\xaa'*512)
        wire=encode(f);p=Parser();out=[]
        for b in wire:out+=p.feed(bytes([b]))
        self.assertEqual(out,[f]);self.assertEqual(p.good_frames,1)
    def test_resync(self):
        good=encode(Frame(PING,0,payload=b'ok'));bad=bytearray(encode(Frame(PING,4,payload=b'bad!')));bad[-1]^=1
        for stream in (bytes(bad)+good,bytes(bad[:-3])+good,bytes(bad[:30])+b'\x17'+bytes(bad[30:])+good,b'\x55'+good):
            p=Parser();out=p.feed(stream)+p.expire();self.assertEqual(out[-1].payload,b'ok')
    def test_timeout(self):
        p=Parser();p.feed(encode(Frame(PING,payload=b'1234'))[:-3]);p.expire()
        self.assertEqual(p.errors['timeout'],1);self.assertEqual(p.feed(encode(Frame(PING)))[0].kind,PING)
    def test_wave_sequence_wrap_and_timestamp_carry(self):
        a=WaveAssembler();base=(1<<64)-2
        f=Frame(0xb0,65535,base,25000000,1,RESPONSE|FIRST|MORE,struct.pack('<IIHH',0,4,1,2))
        g=Frame(0xb0,0,0,25000000,1,RESPONSE|LAST,struct.pack('<IIHH',2,4,3,4))
        self.assertIsNone(a.accept(f));self.assertEqual(a.accept(g),[1,2,3,4])
        a=WaveAssembler();a.accept(f)
        with self.assertRaises(ValueError):a.accept(Frame(**{**g.__dict__,'sequence':2}))
if __name__=='__main__':unittest.main()
