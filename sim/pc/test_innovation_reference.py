import sys,unittest,struct,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
from innovation_reference import *
from scope_protocol import Frame,encode
def example():
    words=[2050,0x8800,2045,2043];m=moments(words);h=bytearray(128);h[:8]=b'SCAP\x01\x00\x80\x00'
    for o,x in [(8,7),(12,4),(16,2),(20,2),(24,1),(28,25000000),(60,1),(64,m['crc']),(68,4),(92,m['otr'])]:struct.pack_into('<I',h,o,x)
    for o,x in [(32,(1<<64)-2),(40,0),(48,1),(80,m['square_sum'])]:struct.pack_into('<Q',h,o,x)
    struct.pack_into('<HH',h,56,1,2);struct.pack_into('<q',h,72,m['sum']);struct.pack_into('<hh',h,88,m['minimum'],m['maximum']);h[96]=1
    body=b'R'+struct.pack('<H',words[1])+struct.pack('<BHhh',0x42,0,m['minimum'],m['maximum'])+(0).to_bytes(3,'little')+(3).to_bytes(3,'little')+b'\x01'+b'R'+struct.pack('<H',words[2])
    d=bytes(h)+body;return d+b'F'+struct.pack('<IHH',zlib.crc32(d),1,2)
class InnovationTests(unittest.TestCase):
    def test_fit_known_positive_negative_and_degenerate(self):
        for sign in (-1,1):self.assertEqual(fit([(x,sign*x*16384+7*65536) for x in range(-10,11)]),(sign*262144,7*65536,sign*1048576))
        self.assertIsNone(fit([(1,0)]*3));self.assertIsNone(fit([(0,0),(1,0)]));self.assertIsNone(fit([(0,0)],262144))
    def test_correction_saturation_and_bypass(self):
        self.assertEqual(apply(2047,0,1048576),(0,0));self.assertEqual(apply(0,0,67108864)[1],1)
        self.assertEqual(apply(4095,123,67108864,False),(-2048*65536,0))
    def test_fault_threshold_strict_and_polarity(self):
        b=dict(valid=1,gain=262144,offset=0,noise=0,compression=0,harmonic=0,otr=0)
        self.assertEqual(classify(b,b|{'offset':LIMITS['zero']},LIMITS),(0,0));self.assertEqual(classify(b,b|{'offset':LIMITS['zero']+1},LIMITS),(1,1))
        self.assertEqual(classify(b,b|{'gain':-262144},LIMITS),(32,6))
    def test_container_interleaving_moments_and_time_wrap(self):
        d=decode_result(example());self.assertEqual([r['timestamp'] for r in d['roi']],[(1<<64)-1,0]);self.assertEqual(d['buckets'][0]['min_index'],0)
        self.assertEqual(d['moments'],moments([2050,0x8800,2045,2043]))
    def test_container_corruption_and_truncation(self):
        d=bytearray(example());d[130]^=1
        with self.assertRaises(ValueError):decode_result(bytes(d))
        with self.assertRaises(ValueError):decode_result(example()[:-1])
    def test_uart_segment_sequence_wrap_and_crc(self):
        d=example();frames=[]
        for i,offset in enumerate(range(0,len(d),20)):
            part=d[offset:offset+20];flags=1|(FIRST if i==0 else 0)|(LAST if offset+len(part)==len(d) else MORE)
            frames.append(encode(Frame(0xb2,(65535+i)&65535,(1<<64)-2,25000000,2,flags,struct.pack('<I',offset)+part)))
        result,actual,count=assemble_uart(b''.join(frames));self.assertEqual(actual,d);self.assertEqual(result['result_id'],7);self.assertGreater(count,1)
        bad=bytearray(b''.join(frames));bad[-1]^=1
        with self.assertRaises(ValueError):assemble_uart(bad)
if __name__=='__main__':unittest.main()
