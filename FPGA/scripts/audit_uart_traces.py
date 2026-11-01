import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC'/'protocol'))
from scope_protocol import Parser,WaveAssembler
ap=argparse.ArgumentParser();ap.add_argument('--vectors',type=Path,required=True);ap.add_argument('--traces',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
meta=json.loads((a.vectors/'oracle.json').read_text(encoding='utf8'));out={}
for name,reference in [('uart_bytes.hex','expected.hex'),('uart_bits.hex','bit_expected.hex')]:
    actual=bytes.fromhex((a.traces/name).read_text());expected=bytes.fromhex((a.vectors/reference).read_text());assert actual==expected,name
    p=Parser();frames=[]
    # Parse with deliberately unrelated chunks so a chunk boundary cannot hide framing bugs.
    for i in range(0,len(actual),137):frames+=p.feed(actual[i:i+137])
    assert not any(p.errors.values()) and not p.buffer,(name,p.errors)
    out[name]=dict(bytes=len(actual),frames=len(frames),sha256=hashlib.sha256(actual).hexdigest())
    if name=='uart_bytes.hex':
        waves=[f for f in frames if f.kind==0xb0 and not f.flags&2];assembler=WaveAssembler();first=None
        for f in waves[:4]:first=assembler.accept(f)
        assert first is not None and len(first)==1600 and waves[0].sequence==65535 and waves[1].sequence==0
        assert waves[0].timestamp>0xffffffffffff0000 and waves[1].timestamp<1000
        assert len(waves)==6 and waves[4].flags&4 and waves[5].flags&16
        out['wave_words_compared']=1600+508+5
out['oracle']=meta;out['verdict']='PASS';a.output.write_text(json.dumps(out,indent=2),encoding='utf8');print('TRACE_AUDIT_PASS',meta['bulk_payload_bytes'])
