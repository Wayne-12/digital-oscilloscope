"""Generate independent direct-DFT results BEFORE configuring vendor FFT IP."""
import argparse,json,math,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC'/'protocol'))
from spectrum_reference import *

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--expected-output',type=Path,required=True);ap.add_argument('--seed',type=int,default=20261020)
    a=ap.parse_args();v=a.output;e=a.expected_output;v.mkdir(parents=True,exist_ok=True);e.mkdir(parents=True,exist_ok=True)
    cases=[];rng=random.Random(a.seed)
    sqrt_rng=random.Random(a.seed^0x53515254)
    sqrt_cases=[0,1,2,3,4,5,8,9,15,16,(1<<64)-1]
    for root in (2,255,65535,65536,0x7fffffff,0xfffffffe):
        sqrt_cases += [root*root-1,root*root,root*root+root,root*root+root+1]
    sqrt_cases += [sqrt_rng.getrandbits(64) for _ in range(256)]
    def sqrt_nearest(x):
        r=math.isqrt(x);return r+int(x-r*r>r)
    (v/'isqrt.txt').write_text(''.join(f'{i} {x:016x} {sqrt_nearest(x):09x}\n' for i,x in enumerate(sqrt_cases)),encoding='ascii')
    def add(name,x,window=0,rate=25000000,k=None,otr=False,source=0,integration=False):
        cases.append(dict(name=name,x=x,window=window,rate=rate,k=k,otr=otr,source=source,integration=integration))
    def sine(k,amp=1200,phase=0.17,dc=0):return [round_away(dc+amp*math.sin(2*math.pi*k*i/N+phase)) for i in range(N)]
    for window in (0,1):
        add('silence',[0]*N,window);add('dc_positive',[1000]*N,window);add('dc_negative',[-1700]*N,window)
        add('fullscale_dc_positive',[4095]*N,window,otr=True);add('fullscale_dc_negative',[-4096]*N,window,otr=True)
        add('nyquist_fullscale',[4095 if i%2 else -4096 for i in range(N)],window,otr=True)
        for rate in (25000000,50000000,65000000):add('coherent_rate',sine(37),window,rate,37)
        for k,amp in ((7,256),(113,1024),(311,1800),(499,2047),(37,4095)):add('coherent',sine(k,amp),window,k=k,otr=amp>2047)
        add('dc_plus_tone',sine(37,1200,dc=500),window,k=37)
        dual=[round_away(1000*math.sin(2*math.pi*37*i/N+0.17)+500*math.sin(2*math.pi*113*i/N+0.31)) for i in range(N)]
        add('dual',dual,window,k=37)
        add('square',[1000 if (i*8)%N<N//2 else -1000 for i in range(N)],window,k=8)
        add('noncoherent',sine(37.25,1000),window)
        add('noncoherent_noise',[max(-4096,min(4095,x+rng.randrange(-2,3))) for x in sine(113.3,1000)],window)
        add('random_fullrange',[rng.randrange(-4096,4096) for _ in range(N)],window,otr=True,source=65500)
        add('below_threshold',sine(37,1),window)
    # The exact 1024-point ROI emitted by Step 10 from the existing frozen BRAM.
    for window in (0,1):
        xs=[2047-(((i+7680)*37+123)&4095) for i in range(N)]
        add('bram_roi',xs,window,source=7680,integration=True,otr=True)
    metadata=[];sfd=(v/'spectrum_cases.txt').open('w',encoding='ascii');ifd=(v/'integration_cases.txt').open('w',encoding='ascii')
    for cid,c in enumerate(cases):
        x=c.pop('x');weighted=preprocess(x,c['window']);z=dft(weighted);s=summary(z,c['rate'],c['window'])
        if c['k'] is not None:assert s['valid'] and s['peak_bin']==c['k']
        if c['name'] in ('silence','dc_positive','dc_negative','fullscale_dc_positive','fullscale_dc_negative','nyquist_fullscale','below_threshold'):assert s['valid']==0,(c['name'],s)
        timestamp=(0xfffffffffffffff0+7680)&((1<<64)-1) if c['integration'] else (0xfffffffffffffff0 if cid%2==0 else 0x123456789abc0000)
        line=f"{cid} {c['window']} {c['rate']} {c['source']} {timestamp:016x} {int(c['otr'])} {s['valid']} {s['peak_bin']} {s['frequency']} {s['amplitude_q16']} {s['rms_q16']} {s['dc_q16']}\n"
        (ifd if c['integration'] else sfd).write(line)
        (v/f'samples_{cid}.txt').write_text(''.join(f'{i} {value} {int(((i+7680)%17==0 or i+7680==8192) if c["integration"] else (c["otr"] and i==17))} {(timestamp+i)&((1<<64)-1):016x}\n' for i,value in enumerate(x)),encoding='ascii')
        (e/f'fft_{cid}.txt').write_text(''.join(f'{i} {round_away(value.real)} {round_away(value.imag)}\n' for i,value in enumerate(z)),encoding='ascii')
        (e/f'weighted_{cid}.txt').write_text(''.join(f'{i} {value}\n' for i,value in enumerate(weighted)),encoding='ascii')
        metadata.append(dict(id=cid,**c,timestamp=timestamp,result=s,quantized_samples=x,weighted_samples=weighted))
    sfd.close();ifd.close()
    raw=[]
    raw.append(('complex_forward',False,[complex(round_away(12000*math.cos(2*math.pi*37*i/N)),round_away(12000*math.sin(2*math.pi*37*i/N))) for i in range(N)]))
    raw.append(('complex_inverse',True,raw[0][2]))
    raw.append(('complex_impulse',False,[complex(32767,-32768)]+[0j]*(N-1)))
    raw.append(('complex_fullscale_dc',False,[complex(-32768,-32768)]*N))
    raw.append(('complex_random',False,[complex(rng.randrange(-32768,32768),rng.randrange(-32768,32768)) for _ in range(N)]))
    with (v/'raw_cases.txt').open('w',encoding='ascii') as f:
        for cid,(name,inverse,x) in enumerate(raw):
            f.write(f'{cid} {int(inverse)}\n');z=dft(x,inverse)
            (v/f'raw_{cid}.txt').write_text(''.join(f'{i} {int(value.real)} {int(value.imag)}\n' for i,value in enumerate(x)),encoding='ascii')
            (e/f'raw_{cid}.txt').write_text(''.join(f'{i} {round_away(value.real)} {round_away(value.imag)}\n' for i,value in enumerate(z)),encoding='ascii')
    meta=dict(seed=a.seed,n=N,input_shift=3,component_tolerance=COMPONENT_TOLERANCE,amplitude_tolerance_q16=AMPLITUDE_TOLERANCE_Q16,
        hann_sum=sum(HANN),hann_square_sum=sum(w*w for w in HANN),spectrum_cases=sum(not c['integration'] for c in metadata),integration_cases=2,raw_cases=5,cases=metadata,raw_names=[r[0] for r in raw])
    (e/'oracle.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
    print('DFT_ORACLE_PASS',json.dumps({k:meta[k] for k in ('seed','spectrum_cases','integration_cases','raw_cases','component_tolerance','amplitude_tolerance_q16')}))
if __name__=='__main__':main()
