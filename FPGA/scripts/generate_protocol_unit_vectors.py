"""Independent PC codec oracle for the isolated RTL frame codec."""
import argparse,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC/protocol'))
from scope_protocol import Frame,Parser,encode

def generate(out,seed):
    out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed);parser=Parser();frames=[];actions=[]
    def feed(data):
        frames.extend(parser.feed(data));actions.extend(f'0 {b}' for b in data)
    # Known malformed candidates with no accidental magic in their bodies.
    f=encode(Frame(1,payload=b'1111'))
    bad=bytearray(f);bad[-1]^=1;feed(bad)
    bad=bytearray(f);bad[6:8]=(1025).to_bytes(2,'little');feed(bad)
    bad=bytearray(f);bad[2]=2;feed(bad)
    feed(f[:-1]);feed(f)
    feed(f[:27]+b'3'+f[27:]);feed(f)
    actions.append(f'2 {sum(len(encode(x)) for x in frames)}')
    feed(b'\x55\xaa\x01');actions.append('1 150');frames.extend(parser.expire())
    # Empty, one-byte and maximum frames; sequence and timestamp wrap.
    feed(encode(Frame(1,65535,(1<<64)-1,payload=b'')))
    feed(encode(Frame(2,0,0,payload=b'\x55')))
    bulk=1048576
    for i in range(bulk//1024):
        payload=rng.randbytes(1024)
        feed(encode(Frame(0x80,i&65535,((1<<64)-16+i)&((1<<64)-1),25000000,i,1,payload)))
    actions.extend((f'2 {sum(len(encode(x)) for x in frames)}','8 0'))
    expected=b''.join(map(encode,frames));accepted=b''.join(f.payload for f in frames)
    (out/'actions.txt').write_text('\n'.join(actions)+'\n',encoding='ascii')
    (out/'expected.hex').write_text(expected.hex(' ').replace(' ','\n')+'\n',encoding='ascii')
    (out/'accepted.hex').write_text(accepted.hex(' ').replace(' ','\n')+'\n',encoding='ascii')
    (out/'headers.txt').write_text(''.join(f'{f.kind:x} {f.sequence:x} {len(f.payload):x} {f.timestamp:x} {f.sample_rate:x} {f.trigger_index:x} {f.flags:x}\n' for f in frames),encoding='ascii')
    e=parser.errors
    (out/'counts.txt').write_text(f'{len(expected)} {len(accepted)} {len(frames)} {e["crc"]} {e["length"]} {e["version"]} {e["timeout"]} {bulk}\n',encoding='ascii')
    (out/'oracle.json').write_text(json.dumps(dict(seed=seed,frames=len(frames),bulk=bulk,errors=e),indent=2),encoding='utf-8')
    print('PROTOCOL_UNIT_ORACLE_PASS',len(frames),e)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args();generate(a.output,a.seed)
