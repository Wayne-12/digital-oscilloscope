"""Separate stimuli and Python integer-floor oracle for Step 10."""
import argparse,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC'/'protocol'))
from envelope_reference import boundaries,summarize

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--expected-output',type=Path,required=True)
    ap.add_argument('--seed',type=int,default=20261020);a=ap.parse_args();v=a.output;e=a.expected_output
    v.mkdir(parents=True,exist_ok=True);e.mkdir(parents=True,exist_ok=True);cases=[]
    def add(n,pattern,b=800,roi=1024,trigger=None,position=None):
        cases.append(dict(n=n,pattern=pattern,b=b,roi=roi,trigger=n//2 if trigger is None else trigger,position=position))
    for n in (1,2,7,511,512,799,800,801,1600,16000,16384,16383,16384):add(n,'random',roi=2048 if n>=16383 else 1024)
    for pattern in ('zero','constant_positive','constant_negative','increase','decrease','positive','negative','alternating'):
        add(16384,pattern)
    for n,b in ((17,1),(16003,3),(16384,17),(16384,127),(16384,400),(16384,200),(16384,100),(16000,800),(801,799)):
        add(n,'random',b=b,roi=512)
    for n in (16384,16384):
        for sign in ('positive','negative'):
            for pos in ('first','middle','last'):add(n,f'impulses_{sign}_{pos}',roi=2048,trigger=n//2)
    # One isolated global spike at either side of selected bucket boundaries.
    for n in (16003,16384):
        for k in (1,400,799):
            boundary=k*n//800
            for pos in (boundary-1,boundary):
                for sign in (1,-1):add(n,'single_positive' if sign>0 else 'single_negative',position=pos,roi=512)
    for t in (0,1,255,256,16383-256,16382,16383):
        add(16384,'random',trigger=t,roi=512 if t%2 else 2048)
    for r in (0,513,1023,2047):add(2400,'alternating',roi=r)
    for n in (511,512,2048):add(n,'random',trigger=n-1,roi=512 if n<2048 else 2048)
    data_meta=[];total_samples=total_buckets=total_roi=0
    with (v/'cases.txt').open('w',encoding='ascii') as desc:
        for cid,c in enumerate(cases):
            n=c['n'];pattern=c['pattern'];r=random.Random(a.seed^n^0xa510);xs=[0]*n
            if pattern=='random':xs=[r.randrange(-2048,2048) for _ in range(n)]
            elif pattern=='constant_positive':xs=[1011]*n
            elif pattern=='constant_negative':xs=[-1234]*n
            elif pattern=='increase':xs=[-2048+(i*4095//max(n-1,1)) for i in range(n)]
            elif pattern=='decrease':xs=[2047-(i*4095//max(n-1,1)) for i in range(n)]
            elif pattern=='positive':xs=[1+(i%2047) for i in range(n)]
            elif pattern=='negative':xs=[-1-(i%2048) for i in range(n)]
            elif pattern=='alternating':xs=[2047 if i%2 else -2048 for i in range(n)]
            elif pattern.startswith('single_'):xs[c['position']]=2047 if 'positive' in pattern else -2048
            elif pattern.startswith('impulses_'):
                for lo,hi in boundaries(n,c['b']):
                    pos=lo if pattern.endswith('first') else hi if pattern.endswith('last') else (lo+hi)//2
                    xs[pos]=2047 if 'positive' in pattern else -2048
            words=[2047-x|(0x8000 if i%257==0 or i==c['trigger'] else 0) for i,x in enumerate(xs)]
            env,roi=summarize(words,c['trigger'],c['b'],c['roi'])
            timestamp=0xfffffffffffffff0 if cid%2==0 else 0x123456789abc0000;rate=25000000
            desc.write(f"{cid} {n} {c['b']} {c['roi']} {c['trigger']} {timestamp:016x} {rate} {len(env)} {roi[0]} {roi[1]} {roi[2]}\n")
            (v/f'frame_{cid}.hex').write_text(''.join(f'{w:04x}\n' for w in words),encoding='ascii')
            (e/f'buckets_{cid}.txt').write_text(''.join(' '.join(map(str,row))+'\n' for row in env),encoding='ascii')
            start,count,_=roi
            (e/f'roi_{cid}.txt').write_text(''.join(f'{i-start} {i} {words[i]:04x} {xs[i]} {(timestamp+i)&((1<<64)-1):016x}\n' for i in range(start,start+count)),encoding='ascii')
            data_meta.append(dict(id=cid,**c,buckets=len(env),roi_start=start,roi_count=count,roi_trigger_index=roi[2],timestamp=timestamp,rate=rate))
            total_samples+=n;total_buckets+=len(env);total_roi+=count
    meta=dict(seed=a.seed,cases=data_meta,case_count=len(cases),sample_comparisons=total_samples,bucket_comparisons=total_buckets,roi_comparisons=total_roi)
    (e/'oracle.json').write_text(json.dumps(meta,indent=2),encoding='utf8');print('ORACLE_PASS',json.dumps({k:meta[k] for k in ('seed','case_count','sample_comparisons','bucket_comparisons','roi_comparisons')}))
if __name__=='__main__':main()
