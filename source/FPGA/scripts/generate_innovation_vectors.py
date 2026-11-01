import argparse,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC/protocol'))
from innovation_reference import *
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seed',type=int,default=20261020);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);rng=random.Random(a.seed)
cases=[]
for i in range(32):
    n=rng.randrange(2,33);gain=rng.choice([-393216,-262144,-196608,131072,196608,262144,393216]);off=rng.randrange(-50,51)<<16
    xs=sorted(rng.sample(range(-3072,3073),n));pts=[(x,rnd(gain*x,16)+off+rng.randrange(-128,129)) for x in xs];cases.append((pts,262144,n))
cases += [([(1,0)]*9,262144,9), ([(x,0) for x in range(9)],262144,9), ([(x,x*8*65536) for x in range(9)],262144,9), ([(0,0)],262144,1), ([(0,0)]*33,262144,33), ([(x,x*16384) for x in range(9)],0,9)]
with (a.output/'fit_cases.txt').open('w') as f:
    for i,(pts,nom,n) in enumerate(cases):
        r=fit(pts,nom);f.write(f'{i} {n} {nom} {int(r is not None)} '+(' '.join(map(str,r)) if r else '0 0 0')+'\n')
        (a.output/f'fit_{i}.txt').write_text(''.join(f'{x} {y}\n' for x,y in pts),encoding='ascii')
with (a.output/'apply.txt').open('w') as f:
    for i in range(1024):
        word=rng.randrange(4096)|(rng.randrange(2)<<15);off=rng.randrange(-2048*65536,2048*65536+1);corr=rng.choice([-67108864,-1398101,1048576,67108864]);valid=int(i%5!=0);ts=(0xfffffffffffffff0+i)&((1<<64)-1);value,sat=apply(word,off,corr,valid)
        f.write(f'{i} {word:04x} {ts:016x} {valid} {off} {corr} {value} {sat}\n')
base=dict(valid=1,gain=262144,offset=0,noise=65536,compression=0,harmonic=1,otr=0)
health=[(base.copy(),base.copy())]
for key,limit in [('offset',LIMITS['zero']),('gain',LIMITS['gain']),('noise',LIMITS['noise']),('compression',LIMITS['compression']),('harmonic',LIMITS['harmonic']),('otr',LIMITS['otr'])]:
    for delta in (limit,limit+1):c=base.copy();c[key]+=delta;health.append((base.copy(),c))
for change in ({'gain':-262144},{'valid':0},{'gain':0}):health.append((base.copy(),base|change))
with (a.output/'health.txt').open('w') as f:
    for i,(b,c) in enumerate(health):
        mask,kind=classify(b,c,LIMITS);f.write(f'{i} '+' '.join(str(v[k]) for v in (b,c) for k in ('valid','gain','offset','noise','compression','harmonic','otr'))+f' {mask} {kind}\n')
for name,n in [('bram',16384)]:
    words=source_words(n);(a.output/f'{name}_words.hex').write_text(''.join(f'{w:04x}\n' for w in words),encoding='ascii')
plan=dict(seed=a.seed,fit_cases=len(cases),apply_cases=1024,health_cases=len(health),profiles=8,zero_frames=4,zero_frame_samples=256,dc_points=9,dc_samples=2048,sine_amplitudes=[256,512,1024,2048,3072,4096],sine_samples=4096,fft_bins=1024,
 gain_error_limit_q20=GAIN_ERROR_LIMIT_Q20,offset_error_limit_q16=OFFSET_ERROR_LIMIT_Q16,limits=LIMITS,
 capture_jobs_per_backend=3,roi_counts=[512,1024,2048],minimum_wire_reduction=dict(bram=0.40))
(a.output/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf8');print('INNOVATION_ORACLE_PASS',json.dumps(plan))
