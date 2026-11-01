"""Independent Python integer/timeline oracle for DDS -> DAC -> channel -> ADC.
Does not import RTL helpers or read the RTL sine ROM. All files use ADC LSB units.
"""
import argparse,cmath,json,math,random
from pathlib import Path

def rnd(n,d): return (-1 if n<0 else 1)*((abs(n)+d//2)//d)
def noise_step(s):
    s^=(s<<13)&0xffffffff;s^=s>>17;s^=(s<<5)&0xffffffff
    return s&0xffffffff
PROFILES=[{},dict(invert=True),dict(delay=3,fraction=16384),dict(gain=8192,offset=123),
 dict(noise=3),dict(clip=(-1000,1000)),dict(alpha=8192),dict(even=4096),dict(odd=4096),
 dict(gain=32768),dict(delay=2,fraction=32768,gain=12288,invert=True,offset=-37,noise=2,clip=(-1750,1750),alpha=32768,even=2048,odd=-1024),
 dict(delay=1,fraction=49152,force=True),dict(delay=4,fraction=65535)]
def profile(i):
    return dict(delay=0,fraction=0,gain=16384,invert=False,offset=0,noise=0,clip=None,alpha=65536,even=0,odd=0,force=False)|PROFILES[i]
def cases(i):
    result=[dict(name='dc_mid',n=256,mode=3,offset=0),dict(name='dc_plus',n=256,mode=3,offset=2048),dict(name='dc_minus',n=256,mode=3,offset=-2048)]
    for hz,n in ((10000,8192),(100000,4096),(1000000,4096)):
        result.append(dict(name=f'sine_{hz}',n=n,mode=0,ftw=(hz*(1<<32)+12500000)//25000000,amplitude=6000))
    for a in (0,512,1024,2048,4096,6000,7500):
        result.append(dict(name=f'amp_{a}',n=3072,mode=0,ftw=1<<22,amplitude=a))
    result.append(dict(name='random_config',n=2048,random=True))
    if i==0:result.append(dict(name='sine_1000_long',n=100256,mode=0,ftw=(1000*(1<<32)+12500000)//25000000,amplitude=6000))
    return result

def wave(phase,mode):
    idx=phase>>22
    if mode==0:
        x=32767*math.sin(math.tau*idx/1024)
        return int(math.copysign(math.floor(abs(x)+0.5),x))
    if mode==1:return 32767 if phase<0x80000000 else -32767
    if mode==2:return rnd((idx if idx<256 else 512-idx if idx<768 else idx-1024)*32767,256)
    return 0

def generate(vdir,edir,seed):
    vdir.mkdir(parents=True,exist_ok=True);edir.mkdir(parents=True,exist_ok=True)
    manifests=[]
    for pid in range(13):
        cfg=profile(pid); summaries=[]
        with (vdir/f'cases_p{pid}.txt').open('w') as headers,(vdir/f'stim_p{pid}.txt').open('w') as stim,(edir/f'expected_p{pid}.txt').open('w') as exp:
            for cid,c in enumerate(cases(pid)):
                ns=(seed^(pid<<16)^(cid*0x9e3779b9))&0xffffffff
                headers.write(f'{cid} {c["name"]} {c["n"]} {ns:08x}\n')
                rng=random.Random(seed+cid*7919); acc=0;primed=False;dcin=8192;dcout=8192;div=False;dov=False
                history=[];filt=0;noise=ns or 1;adc_inputs=[];rows=[];chan_rows=[];force_rows=[];clip_rows=[]
                for n in range(c['n']):
                    if c.get('random'):
                        mode=rng.randrange(4);amplitude=rng.randrange(7501);offset=rng.randrange(-64,65);ftw=rng.getrandbits(32);po=rng.getrandbits(32)
                    else:mode=c.get('mode',0);amplitude=c.get('amplitude',0);offset=c.get('offset',0);ftw=c.get('ftw',0);po=0
                    fe=int(cfg['force'] and (n%257==17 or n%509==23 or 300<=n<309));fv=int(fe and not n%509==23)
                    stim.write(f'{mode} {amplitude} {offset} {ftw:08x} {po:08x} {fe} {fv}\n')
                    if not primed:code=8192;ph=0;valid=0;primed=True
                    else:
                        ph=(acc+po)&0xffffffff;code=max(0,min(16383,8192+offset+rnd(wave(ph,mode)*amplitude,32767)));valid=1;acc=(acc+ftw)&0xffffffff
                    if not dov:
                        history=[];filt=0;noise=ns or 1;ch=0;cv=0;clipped=0;cfe=0;cfv=0
                    else:
                        history.insert(0,dcout-8192)
                        needed=cfg['delay']+1+bool(cfg['fraction'])
                        if len(history)>=needed:
                            d=cfg['delay'];x=history[d];old=history[d+1] if cfg['fraction'] else 0
                            x=rnd((65536-cfg['fraction'])*x+cfg['fraction']*old,65536)
                            y=x+rnd(cfg['even']*x*x,65536*8192)+rnd(cfg['odd']*x*x*x,65536*8192**2)
                            y=rnd(y*cfg['gain'],65536)*(-1 if cfg['invert'] else 1)
                            noise=noise_step(noise);y+=cfg['offset']+(noise%(2*cfg['noise']+1)-cfg['noise'])
                            filt+=rnd((y*65536-filt)*cfg['alpha'],65536)
                            ch=rnd(filt,65536);clipped=0
                            if cfg['clip']:
                                lo,hi=cfg['clip'];clipped=int(ch<lo or ch>hi);ch=max(lo,min(hi,ch))
                            cv=1;cfe=fe;cfv=fv
                        else:ch=0;cv=0;clipped=0;cfe=0;cfv=0
                        # Keep only the causal history needed by the model.
                        history=history[:cfg['delay']+2]
                    auto=int(ch< -2048 or ch>2047);aotr=cfv if cfe else auto
                    araw=2047-max(-2048,min(2047,ch));adc_inputs.append((araw,aotr,ch,cfe,cfv,auto,clipped))
                    old_in=dcin;old_iv=div;dcin=code;div=True;dcout=old_in;dov=old_iv
                    ar,ao=(adc_inputs[n-7][:2] if n>=7 else (2047,0));av=int(n>=7)
                    if n>=8:
                        cr,co=adc_inputs[n-8][:2];cs=2047-cr;ct=n-8;cvout=1
                        rows.append((ct,cr,cs,co));chan_rows.append(adc_inputs[n-8][2]);force_rows.append(adc_inputs[n-8][3:6]);clip_rows.append(adc_inputs[n-8][6])
                    else:cvout=0;cr=2047;cs=0;co=0;ct=0
                    exp.write(f'{code} {ph:08x} {valid} {dcin} {dcout} {int(dov)} {ch} {cv} {clipped} {cfe} {cfv} {ar} {ao} {av} {cvout} {cr} {cs} {co} {ct:016x}\n')
                measure=[x for x in rows if x[0]>=128]; vals=[x[2] for x in measure]
                summaries.append(dict(id=cid,name=c['name'],cycles=c['n'],captured=len(rows),measured=len(vals),minimum=min(vals),maximum=max(vals),sum=sum(vals),sum_squares=sum(x*x for x in vals),otr=sum(x[3] for x in rows),raw_sum=sum(x[1] for x in rows),clipped=sum(clip_rows),forced_high=sum(en and val for en,val,au in force_rows),forced_low=sum(en and not val for en,val,au in force_rows),auto_overrange=sum(au for en,val,au in force_rows),word_sum=sum((x[3]<<15)|x[1] for x in rows)))
        (vdir/f'meta_p{pid}.txt').write_text(f'{len(summaries)} {seed}\n')
        manifests.append(dict(id=pid,config=cfg,cases=summaries))
    (edir/'oracle_manifest.json').write_text(json.dumps(dict(seed=seed,sample_rate_hz=25000000,profiles=manifests,rounding='nearest, ties away from zero',measurement_start_timestamp=128),indent=2))
    print(f'ORACLE_PASS seed={seed} profiles=13 delay_endpoints=2 compared_per_seed=1258816')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-output',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    a=p.parse_args();generate(a.output,a.expected_output,a.seed)
