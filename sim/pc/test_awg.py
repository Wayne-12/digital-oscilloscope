import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'protocol'))
import awg
import scope_protocol as p

class MemoryLink:
    def __init__(self):self.data=b'';self.active=b'';self.crc=0;self.selected=False
    def exchange(self,kind,payload=b''):
        answer=b'\0'
        if kind==awg.BEGIN:
            assert payload==struct.pack('<I',1024);self.data=b''
        elif kind==awg.CHUNK:
            assert struct.unpack_from('<H',payload)[0]*2==len(self.data)
            self.data+=payload[2:]
        elif kind==awg.COMMIT:
            assert len(self.data)==2048 and struct.unpack('<H',payload)[0]==p.crc16(self.data)
            self.active=self.data;self.crc=p.crc16(self.active)
        elif kind==awg.READ:
            start,count=struct.unpack('<HH',payload);answer=payload+self.active[start*2:(start+count)*2]
        elif kind==awg.STATUS:
            answer=struct.pack('<BBHHHHHI',1,int(bool(self.active)),0,1024,1024 if self.active else 0,self.crc,self.crc,0)
        else:raise AssertionError(kind)
        return p.Frame(kind|128,0,payload=answer,flags=p.RESPONSE)

class AwgTests(unittest.TestCase):
    def test_one_pass_values_and_mutation_during_transfer(self):
        expected=[(i*73)%65535-32767 for i in range(1024)]
        link=MemoryLink()
        self.assertTrue(awg.upload(link,iter(expected))['valid'])
        self.assertEqual(awg.read_table(link),expected)
        mutable=expected.copy()
        self.assertTrue(awg.upload(link,mutable,lambda _:mutable.__setitem__(0,123))['valid'])
        self.assertEqual(awg.read_table(link),expected)

    def test_transaction_complete_readback(self):
        values=[(i*73)%65535-32767 for i in range(1024)]
        progress=[];link=MemoryLink();result=awg.upload(link,values,progress.append)
        self.assertEqual(awg.read_table(link),values)
        self.assertTrue(result['valid']);self.assertEqual(progress,[20,40,60,80,100])

    def test_wrong_readback_refused(self):
        class Corrupt(MemoryLink):
            def exchange(self,kind,payload=b''):
                f=super().exchange(kind,payload)
                if kind==awg.READ:f=replace(f,payload=f.payload[:-1]+bytes([f.payload[-1]^1]))
                return f
        with self.assertRaises(ValueError):awg.upload(Corrupt(),[0]*1024)

    def test_file_contract_and_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'table.csv'
            path.write_text('value\n'+'\n'.join(['-1','1']+['0']*1022),encoding='utf-8-sig')
            self.assertEqual(awg.load_table(path),[-32767,32767]+[0]*1022)
            for bad in ('nan','inf','1.0001','-1.0001','0,1','arbitrary text'):
                path.write_text('\n'.join([bad]+['0']*1023))
                with self.subTest(bad=bad),self.assertRaises(ValueError):awg.load_table(path)
            path.write_text('0\n'*1023)
            with self.assertRaises(ValueError):awg.load_table(path)

    def test_no_silent_clipping(self):
        for value in (-32768,32768,1.5,True):
            with self.subTest(value=value),self.assertRaises(ValueError):awg.encode_table([value]*1024)

if __name__=='__main__':unittest.main()
