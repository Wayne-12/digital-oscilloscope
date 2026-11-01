"""Independent byte/command oracle. CRC uses Python's C implementation, not RTL."""
import argparse,json,math,random,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC'/'protocol'))
from scope_protocol import Frame,Parser,encode

MASK=(1<<64)-1; BASE=MASK-15; RATE=25_000_000
def word(i,pre):return ((i*37+123)&4095) | (0x8000 if i%17==0 or i==pre else 0)
def measure():
    xs=[2047-((i*37+123)&4095) for i in range(16384)]
    s=sum(xs);ss=sum(x*x for x in xs);r=math.isqrt(ss//len(xs))
    if 4*ss>=len(xs)*(2*r+1)**2:r+=1
    b=bytearray(64);b[:4]=bytes([1,0,0,0]);struct.pack_into('<IhhhHH',b,4,len(xs),min(xs),max(xs),-1,max(xs)-min(xs),r)
    struct.pack_into('<qQ',b,20,s,ss);return bytes(b)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--expected-output',type=Path);ap.add_argument('--seed',type=int,default=20261020)
    ap.add_argument('--bulk-bytes',type=int,default=1048576);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    golden=a.expected_output or a.output;golden.mkdir(parents=True,exist_ok=True)
    rng=random.Random(a.seed);actions=[];gold=bytearray();accepted=bytearray();rxheaders=[];configs=[];parser=Parser()
    seq=10;unknown=errors=0;length=16384;pre=8192;backendpre=8192;wave=0;enabled=0;inc=phase=amp=dc=0
    def act(op,n=0):actions.append((op,n))
    def emit(f):gold.extend(encode(f))
    def response(req,payload,flags=1,kind=None,timestamp=BASE):emit(Frame(kind or req.kind|128,req.sequence,timestamp,RATE,backendpre,flags,payload))
    def sendwire(w):
        for v in w:act(0,v)
        got=parser.feed(w)
        for f in got:
            rxheaders.append(f'{f.kind:02x} {f.sequence:04x} {len(f.payload):04x} {f.timestamp:016x} {f.sample_rate:08x} {f.trigger_index:08x} {f.flags:04x}')
            accepted.extend(f.payload)
        return got
    def req(kind,payload=b'',flags=0,force_seq=None):
        nonlocal seq
        f=Frame(kind,seq if force_seq is None else force_seq,(0xfedcba9876543210+seq)&MASK,0x12345678,0x89abcdef,flags,payload);seq=(seq+1)&65535
        assert sendwire(encode(f))==[f];return f
    def wait():act(2,len(gold));act(1,15)
    def cfg():
        configs.append(f'{length} {pre} {wave} {enabled} {inc} {phase} {amp} {dc}')
        act(5,len(configs)-1)
    def ack(f,code=0):
        nonlocal errors
        if code:errors+=1
        response(f,bytes([code]),1|(2 if code else 0));wait()
    def status():
        f=req(3);p=bytearray(48);p[0]=2|(enabled<<2);p[2]=1
        struct.pack_into('<11I',p,4,length,pre,parser.errors['crc'],parser.errors['length'],parser.errors['version'],parser.errors['timeout'],unknown,errors,0,0,parser.good_frames)
        response(f,bytes(p));wait()
    act(4);f=req(1,b'\x55\xaa\x00\xff');response(f,f.payload);wait()
    f=req(1);response(f,b'');wait();f=req(2);response(f,bytes([1,0,0,0])+struct.pack('<I',0x20261022));wait()
    # Each malformed candidate is followed by a valid sentinel; no permanent loss of alignment.
    for mode in ('crc','version','length','delete','insert'):
        b=bytearray(encode(Frame(1,2,payload=b'abcdef')))
        if mode=='crc':b[-1]^=1
        elif mode=='version':b[2]=2
        elif mode=='length':b[6:8]=struct.pack('<H',1025)
        elif mode=='delete':del b[28]
        else:b.insert(28,0x33)
        sendwire(b);f=req(1,mode.encode());response(f,f.payload);wait()
    sendwire(b'\x00\x55');f=req(1,b'overlap');response(f,f.payload);wait()
    sendwire(encode(Frame(1,3,payload=b'timeout'))[:29]);act(1,400);parser.expire()
    f=req(1,b'after-timeout');response(f,f.payload);wait();status()
    # Full-width field validation and commit-only-on-success checks.
    f=req(0x77);unknown+=1;ack(f,5)
    f=req(2,b'x');ack(f,1);f=req(1,b'x',flags=1);ack(f,2)
    for ln,ratio,code in ((16384,1000000,0),(16384,250000,0),(32768,0,2),(16384,1000001,2)):
        f=req(0x10,struct.pack('<II',ln,ratio));ack(f,code)
        if not code:length=ln;pre=((ln-1)*ratio+500000)//1000000
        cfg()
    trigger=struct.pack('<BBhHhhIIHI',8,0,0,8,-100,100,1,10,4095,16)
    f=req(0x11,trigger);ack(f)
    bad=bytearray(trigger);bad[2:4]=struct.pack('<h',8192);f=req(0x11,bytes(bad));ack(f,2)
    for w,en,fr,ph,am,offset,code in ((3,1,0,0,0,-100,0),(0,1,10000,0x87654321,6000,0,0),(2,1,1000000,0,8000,100,0),(1,0,1000,0,4000,0,0),(0,1,12500001,0,1,0,2),(0,1,1000,0,16384,0,2),(0,1,1000,0,1,-131073,2)):
        f=req(0x40,struct.pack('<BBIIHi',w,en,fr,ph,am,offset));ack(f,code)
        if not code:wave=w;enabled=en;inc=((fr<<32)+12500000)//25000000;phase=ph;amp=am;dc=offset
        cfg()
    f=req(0x31);response(f,measure());wait()
    f=req(0x30,struct.pack('<II',16383,2));ack(f,2)
    def wave_response(f,offset,count,cancel=False):
        start=offset;nseg=0
        while count:
            n=min(508,count);payload=struct.pack('<II',offset,16384)+b''.join(struct.pack('<H',word(i,backendpre)) for i in range(offset,offset+n))
            emit(Frame(0xb0,(f.sequence+nseg)&65535,(BASE+offset)&MASK,RATE,backendpre,1|(8 if offset==start else 0)|(4 if count>n else 16),payload))
            offset+=n;count-=n;nseg+=1
            if cancel:break
    # Four segments, sequence FFFF -> 0000, timestamp carry across 64-bit boundary.
    f=req(0x30,struct.pack('<II',8,1600),force_seq=65535);wave_response(f,8,1600);wait()
    # Stop is accepted while the first wave packet is in flight; finish it, cancel the rest.
    before=len(gold);f=req(0x30,struct.pack('<II',32,1600));wave_response(f,32,1600,True)
    act(2,before+100);s=req(0x21);response(s,b'\0');wait()
    # Re-arm the actual previous-step capture backend, with configured 25% pre-trigger.
    f=req(0x20);ack(f);act(4);backendpre=pre
    f=req(0x30,struct.pack('<II',pre-2,5));wave_response(f,pre-2,5);wait()
    # Abort a fresh capture, then reject reading a frame that never completed.
    f=req(0x20);ack(f);f=req(0x21);ack(f);act(1,40)
    f=req(0x30,struct.pack('<II',0,1));ack(f,4)
    # Recover with a complete capture before the throughput test and final status.
    f=req(0x20);ack(f);act(4);status()
    # Saturate the retained queue while output is paused, then continuous seeded traffic.
    act(6,8000)
    left=a.bulk_bytes
    while left:
        n=min(1024,left);f=req(1,rng.randbytes(n));response(f,f.payload);left-=n
    wait();status();act(8)
    def puthex(name,data):
        destination=a.output if name=='bit_input.hex' else golden
        (destination/name).write_text(''.join(f'{v:02x}\n' for v in data),encoding='ascii')
    (a.output/'actions.txt').write_text(''.join(f'{op} {n}\n' for op,n in actions),encoding='ascii')
    puthex('expected.hex',gold);puthex('accepted_payload.hex',accepted)
    (golden/'headers.txt').write_text('\n'.join(rxheaders)+'\n',encoding='ascii')
    (golden/'configs.txt').write_text('\n'.join(configs)+'\n',encoding='ascii')
    # Pin-level smoke uses independent real bit timing and intentionally tiny FIFOs.
    bit=bytearray();bitgold=bytearray()
    for k,f in enumerate((Frame(1,65535,payload=b'\x00\x55\xaa\xff'),Frame(2,0),Frame(1,1))):
        w=encode(f);bit.extend(w);bitgold.extend(encode(Frame(f.kind|128,f.sequence,BASE,RATE,8192,1,f.payload if f.kind==1 else bytes([1,0,0,0])+struct.pack('<I',0x20261022))))
    puthex('bit_input.hex',bit);puthex('bit_expected.hex',bitgold)
    meta=dict(seed=a.seed,bulk_payload_bytes=a.bulk_bytes,output_bytes=len(gold),accepted_payload_bytes=len(accepted),accepted_frames=len(rxheaders),errors=parser.errors,unknown_commands=unknown,command_errors=errors,bit_input_bytes=len(bit),bit_output_bytes=len(bitgold),config_checks=len(configs))
    (golden/'counts.txt').write_text(' '.join(str(v) for v in (len(gold),len(accepted),len(rxheaders),parser.errors['crc'],parser.errors['length'],parser.errors['version'],parser.errors['timeout'],unknown,errors,a.bulk_bytes))+'\n',encoding='ascii')
    (golden/'bit_counts.txt').write_text(f'{len(bit)} {len(bitgold)}\n',encoding='ascii')
    (golden/'oracle.json').write_text(json.dumps(meta,indent=2),encoding='utf8');print('ORACLE_PASS',json.dumps(meta))
if __name__=='__main__':main()
