"""Independent integer DDS oracle. No RTL/LUT file is read by this generator."""
import argparse, json, math, random
from pathlib import Path

def rounded(n,d):
    return (-1 if n<0 else 1)*((abs(n)+d//2)//d)

def generate(out, expected, seed):
    out.mkdir(parents=True,exist_ok=True); expected.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed); records=[]; cases=[]
    def case(name,mode,n,ftw=0,amp=6000,offset=0,phase=0,randomize=False):
        cid=len(cases); values=[]; phases=[]; wraps=[]; acc=0; primed=False
        # Reset at a non-clock time is checked by TB before the next falling edge.
        entries=[(1,0,mode,amp,offset,ftw,phase)]*2+[(0,0,mode,amp,offset,ftw,phase)]*2
        for i in range(n):
            if randomize:
                reset=int(i%997==513); en=int(i%443 not in (31,32,33))
                item=(reset,en,rng.randrange(4),rng.randrange(65536),rng.randrange(-131072,131072),rng.getrandbits(32),rng.getrandbits(32))
                # Preserve the random schedule, with explicit full-scale-neighbour tests.
                if 1<=i<=8:
                    item=(0,1,1,(8190,8191,8192,8193)[(i-1)%4],0,0,0 if i<=4 else 0x80000000)
                elif i in (9,10): item=(0,1,3,0,131071 if i==9 else -131072,0,0)
                entries.append(item)
            else: entries.append((0,1,mode,amp,offset,ftw,phase))
        for rst,en,w,a,o,inc,po in entries:
            if rst or not en:
                acc=0; primed=False; code=8192; ph=0; valid=0
            elif not primed:
                primed=True; code=8192; ph=0; valid=0
            else:
                ph=(acc+po)%(1<<32); index=ph//(1<<22)
                if w==0:
                    x=math.sin(math.tau*index/1024)*32767
                    q=int(math.copysign(math.floor(abs(x)+0.5),x))
                elif w==1: q=32767 if ph < (1<<31) else -32767
                elif w==2:
                    t=index if index<256 else 512-index if index<768 else index-1024
                    q=rounded(t*32767,256)
                else: q=0
                code=max(0,min(16383,8192+o+rounded(q*a,32767)))
                valid=1; acc=(acc+inc)%(1<<32)
                if not randomize:
                    if phases and ph<phases[-1]: wraps.append(len(values))
                    values.append(code);phases.append(ph)
            records.append(((rst,en,w,a,o,inc,po),(code,ph,valid,cid)))
        stats=dict(id=cid,name=name,cycles=len(entries),active_samples=len(values))
        if values:
            stats.update(minimum=min(values),maximum=max(values),sum=sum(values),mean=sum(values)/len(values),phase_wrap_indices=wraps)
        if ftw:
            actual=25_000_000*ftw/(1<<32)
            stats.update(ftw=ftw,frequency_hz_25M=actual,period_samples=(1<<32)/ftw)
        cases.append(stats)
    def ftw(hz): return (hz*(1<<32)+12_500_000)//25_000_000
    case('dc_mid',3,65)
    case('dc_plus',3,65,offset=1234)
    case('dc_minus',3,65,offset=-2345)
    for hz in (1000,10000,100000,1000000):
        case(f'sine_{hz}',0,max(1001,4*25_000_000//hz+2),ftw(hz))
    for mode,name in ((0,'sine_coherent'),(1,'square'),(2,'triangle')):
        case(name,mode,4097,1<<22,8191)
    case('saturate_both',0,4097,1<<22,65535)
    case('saturate_high',1,2049,1<<22,65535,131071)
    case('saturate_low',2,2049,1<<22,65535,-131072)
    case('offset_phase',0,4097,1<<22,3210,765,0x32456789)
    case('amplitude_zero',0,1025,ftw(10000),0)
    case('nyquist_square',1,1025,0x80000000,8191)
    case('ftw_max_wrap',2,1025,0xffffffff,8191,phase=0x00000001)
    case('random_config_reset',0,12000,randomize=True)
    with (out/'stimulus.txt').open('w') as stim,(expected/'expected.txt').open('w') as exp:
        for (r,e,w,a,o,inc,po),(code,ph,v,cid) in records:
            stim.write(f'{r} {e} {w} {a} {o} {inc:08x} {po:08x}\n')
            exp.write(f'{code} {ph:08x} {v} {cid}\n')
    (out/'meta.txt').write_text(f'{len(records)} {len(cases)} {seed}\n')
    manifest=dict(seed=seed,total_cycles=len(records),cases=cases,rounding='nearest, ties away from zero',clock_rates=[10000000,25000000,50000000,65000000])
    (expected/'oracle_manifest.json').write_text(json.dumps(manifest,indent=2))
    assert cases[7]['mean']==8192 and cases[8]['mean']==8192 and cases[9]['mean']==8192
    assert cases[10]['minimum']==0 and cases[10]['maximum']==16383
    print(f'ORACLE_PASS cycles={len(records)} cases={len(cases)} seed={seed}')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-output',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    a=p.parse_args();generate(a.output,a.expected_output,a.seed)
