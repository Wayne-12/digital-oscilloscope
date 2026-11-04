"""Bounded physical protocol client. No JTAG or Flash operations."""
from pathlib import Path
import sys,time,struct,json,argparse,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'pc/protocol'))
import scope_protocol as p
import serial

class Client:
 def __init__(self,port='COM12'):
  self.s=serial.Serial(port,921600,timeout=.01,write_timeout=2)
  self.s.reset_input_buffer();self.parser=p.Parser();self.seq=20000;self.pending=[]
 def receive(self,deadline):
  while time.monotonic()<deadline:
   if self.pending:return self.pending.pop(0)
   data=self.s.read(max(1,min(self.s.in_waiting,16384)))
   if data:self.pending+=self.parser.feed(data)
  raise TimeoutError('response deadline exceeded')
 def request(self,kind,payload=b'',timeout=4):
  seq=self.seq;self.seq=(seq+1)&65535
  wire=p.encode(p.Frame(kind,sequence=seq,payload=payload))
  if self.s.write(wire)!=len(wire):raise IOError('short serial write')
  deadline=time.monotonic()+timeout
  while True:
   f=self.receive(deadline)
   if f.kind==(kind|128) and f.sequence==seq:
    if f.flags&p.ERROR:raise RuntimeError(f'command {kind:02x} rejected {f.payload.hex()}')
    return f
 def identity(self):
  f=self.request(2);return struct.unpack_from('<I',f.payload,4)[0]
 def close(self):self.s.close()

def baseline(c):
 return {'build':hex(c.identity()),'config':c.request(5).payload.hex(),
         'capture_config':c.request(0x13).payload.hex(),
         'awg_status':c.request(0x19).payload.hex(),'status':c.request(3).payload.hex()}

def echo_throughput(c,length,count,window):
 pending={};sent=done=0;start=time.perf_counter();deadline=time.monotonic()+30
 while done<count:
  while sent<count and len(pending)<window:
   seq=c.seq;c.seq=(seq+1)&65535
   payload=hashlib.shake_256(struct.pack('<II',sent,length)).digest(length)
   wire=p.encode(p.Frame(1,sequence=seq,payload=payload))
   if c.s.write(wire)!=len(wire):raise IOError('short echo write')
   pending[seq]=payload;sent+=1
  f=c.receive(deadline)
  if f.kind!=0x81 or f.flags!=p.RESPONSE or f.sequence not in pending:
   raise AssertionError(f'unexpected echo {f}')
  if f.payload!=pending.pop(f.sequence):raise AssertionError('echo byte mismatch')
  done+=1
 elapsed=time.perf_counter()-start
 return {'payload':length,'packets':count,'window':window,'seconds':elapsed,
         'payload_bytes_per_second_each_direction':length*count/elapsed,
         'wire_bytes_per_second_each_direction':(length+28)*count/elapsed,
         'line_utilization_each_direction':(length+28)*count/elapsed/92160,
         'wire_aggregate_bytes_per_second':2*(length+28)*count/elapsed}

def main():
 a=argparse.ArgumentParser();a.add_argument('--mode',choices=['baseline','throughput','final'],required=True);a.add_argument('--port',default='COM12');args=a.parse_args()
 out=Path(os.environ.get('SCOPE_HARDWARE_REPORTS',str(ROOT/'reports/hardware')));out.mkdir(parents=True,exist_ok=True)
 c=None;result={'result':'FAIL','mode':args.mode}
 try:
  c=Client(args.port);result['before']=baseline(c)
  if args.mode=='final':
   original=json.loads((out/'baseline.json').read_text())['before']
   assert result['before']['build']=='0xa4261028'
   assert result['before']['config']==original['config'],'Record/trigger/DDS configuration differs from pre-test baseline'
   assert result['before']['capture_config']==original['capture_config'],'Capture mode differs from baseline'
   awg=bytes.fromhex(result['before']['awg_status'])
   assert not awg[1]&4,'Diagnostic AWG table must remain unselected'
   result['original_configuration_restored']=True
   result['expected_semantic_rejections']=5
   result['remaining_test_state']='Unselected volatile AWG diagnostic table; cleared by reset/power cycle'
  if args.mode=='throughput':
   assert c.identity()==0xa4261028,'CPU test image is not running'
   result['trials']=[echo_throughput(c,n,count,w) for n,count,w in [(0,50,1),(64,100,1),(1024,128,1),(1024,256,2)]]
   result['after']=baseline(c)
   assert not any(c.parser.errors.values()),c.parser.errors
   before=bytes.fromhex(result['before']['status']);after=bytes.fromhex(result['after']['status'])
   # Protocol semantic counters, framing, FIFO overflow must not increase.
   assert after[12:44]==before[12:44],(before.hex(),after.hex())
   result['parser_errors']=c.parser.errors
  result['result']='PASS'
 except Exception as error:result['error']=repr(error)
 finally:
  if c:c.close()
  (out/f'{args.mode}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result,indent=2))
 return result['result']!='PASS'
if __name__=='__main__':raise SystemExit(main())
