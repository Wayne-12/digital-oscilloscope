"""Independent integer oracle: event lists, complete pulses and block extrema.
No HDL function calls. All timestamp arithmetic is modulo 2**64.
"""
import argparse, json, math, random
from pathlib import Path
MASK=(1<<64)-1
def nearest(n,d):
    return (1 if n>=0 else -1)*((abs(n)+d//2)//d)
def cfg(kind,**kw):
    c=dict(kind=kind,threshold=0,hysteresis=8,window_low=-100,window_high=100,
           width_min=3,width_max=7,amplitude_limit=200,observation_samples=16)
    c.update(kw);return c
def config_ok(c):
    k=c['kind'];h=c['hysteresis']
    return k<=8 and (k not in (2,3) or c['window_low']+h<c['window_high']-h) and \
        (k not in (4,5) or 0<c['width_min']<=c['width_max']) and \
        (k not in (6,7) or 2<=c['observation_samples']<=16384)
def trigger_oracle(c, rows):
    # Represent only accepted uninterrupted histories; derive each event from
    # preceding evidence. Pulse bounds use completed transition pairs.
    history=[];arm=False;level=None;start=None;last_otr=0;block=[];err=0;prev=None;out=[]
    for x,ts,v,en,rst,otr in rows:
        hit=0;gap=prev is not None and ts!=((prev+1)&MASK)
        if rst or not en or not config_ok(c):
            history=[];arm=False;level=None;start=None;last_otr=0;block=[];err=0;prev=None
        elif v:
            prev=ts
            if gap:
                history=[];arm=False;level=None;start=None;last_otr=0;block=[];err=1
            else:
                k=c['kind'];h=c['hysteresis'];lo=c['threshold']-h;hi=c['threshold']+h
                r=level is False and x>hi;f=level is True and x<lo
                if k in (0,1):
                    hit=int(arm and (x>hi if k==0 else x<lo))
                    if hit:arm=False
                    elif x<=lo if k==0 else x>=hi:arm=True
                elif k in (2,3):
                    a=c['window_low'];b=c['window_high']
                    hit=int(arm and (a+h<x<b-h if k==2 else x<a-h or x>b+h))
                    if hit:arm=False
                    elif (x<=a-h or x>=b+h) if k==2 else a+h<=x<=b-h:arm=True
                elif k in (4,5):
                    if start is not None and (f if k==4 else r):
                        hit=int(c['width_min']<=((ts-start)&MASK)<=c['width_max'])
                    if r or f:start=ts if (r if k==4 else f) else None
                elif k in (6,7):
                    block.append(x)
                    if len(block)==c['observation_samples']:
                        span=max(block)-min(block);block=[]
                        hit=int(span<c['amplitude_limit'] if k==6 else span>c['amplitude_limit'])
                elif k==8:hit=int(otr and not last_otr)
                if level is None:
                    if x<=lo:level=False
                    elif x>=hi:level=True
                elif r or f:level=r
                last_otr=otr;history.append(x)
        out.append((hit,err))
    return out
def stats(values,timestamps,rate,th,h):
    n=len(values);s=sum(values);ss=sum(x*x for x in values);root=math.isqrt(ss//n)
    rms=root+int(4*ss>=n*(2*root+1)**2)
    # Schmitt-classify samples, then pair complete rise/fall/rise triples.
    level=None;edges=[]
    for x,t in zip(values,timestamps):
        if level is None:
            if x<=th-h:level=False
            elif x>=th+h:level=True
        elif not level and x>th+h:level=True;edges.append(('r',t))
        elif level and x<th-h:level=False;edges.append(('f',t))
    cycles=[]
    for a,b,c in zip(edges,edges[1:],edges[2:]):
        if (a[0],b[0],c[0])==('r','f','r'):
            cycles.append((((c[1]-a[1])&MASK),((b[1]-a[1])&MASK)))
    time_ok=all(timestamps[i]==((timestamps[i-1]+1)&MASK) for i in range(1,n))
    p=len(cycles) if time_ok else 0;elapsed=sum(x for x,y in cycles);high=sum(y for x,y in cycles)
    return [n,min(values),max(values),nearest(s,n),max(values)-min(values),rms,s,ss,p,
            nearest(elapsed*65536,p) if p else 0,nearest(rate*p,elapsed) if p else 0,
            nearest(high*1000000,elapsed) if p else 0,int(not time_ok),int(p>0)]
def generate(vdir,edir,seed):
    vdir.mkdir(parents=True,exist_ok=True);edir.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed);manifest={'seed':seed,'trigger':[],'measurement':[],'integration':[]}
    triggers=[]
    def tcase(name,c,values,**kw):
        rows=[];ts=kw.get('base',0)
        for i,x in enumerate(values):
            valid=int(not(kw.get('bubbles') and i%11==4));en=int(not(kw.get('disable') and i in (8,9,31)))
            reset=int(bool(kw.get('reset')) and i in (13,47))
            if kw.get('gap') and i==27:ts=(ts+3)&MASK
            otr=int(i%17 in (5,6,7))
            rows.append((x,ts,valid,en,reset,otr))
            if valid:ts=(ts+1)&MASK
        stage=1 if c['kind']<2 else 2 if c['kind']<4 else 3 if c['kind']<6 else 4
        if c['kind']>8:stage=4
        triggers.append((stage,name,c,rows,trigger_oracle(c,rows)))
    boundaries=[-4096,-2048,-109,-108,-100,-92,-91,-9,-8,-1,0,1,8,9,91,92,100,108,109,2047,4095]
    for k in range(9):
        tcase('boundaries',cfg(k),boundaries+boundaries[::-1]+boundaries*4)
        tcase('zero_hysteresis',cfg(k,hysteresis=0),[-100,0,0,0,100,0,-100]*30)
        tcase('random',cfg(k),[rng.randint(-300,300) for _ in range(3000)],bubbles=True)
        tcase('interruptions',cfg(k),[-200]*4+[200]*5+[-200]*3+[200,-200]*100,disable=True,reset=True,gap=True)
        tcase('timestamp_wrap',cfg(k),[-200]*3+[200]*5+[-200]*4+[200,-200]*25,base=MASK-5)
        tcase('constant',cfg(k),[0]*128)
        if k in (4,5):
            for width in (1,2,3,4,7,8,32):
                sign=1 if k==4 else -1
                tcase('width_'+str(width),cfg(k),[-200*sign]*3+[200*sign]*width+[-200*sign]*5)
            tcase('leading_partial',cfg(k),([200]*5+[-200]*5) if k==4 else ([-200]*5+[200]*5))
            sign=1 if k==4 else -1
            for width in (1,2,65535,65536,65537):
                tcase('exact_width_'+str(width),cfg(k,width_min=width,width_max=width),
                      [-200*sign]*3+[200*sign]*width+[-200*sign]*3)
            tcase('unsigned_width_max_reject',cfg(k,width_min=0xffffffff,width_max=0xffffffff),
                  [-200*sign]*3+[200*sign]*5+[-200*sign]*3)
        if k in (6,7):
            for span in (199,200,201,8191):
                vals=[-4096,4095]*8 if span==8191 else [0,span]*8
                tcase('span_'+str(span),cfg(k),vals*3)
            for window in (2,16384):
                for span in (199,200,201):
                    # Three consecutive blocks also prove block min/max restart.
                    tcase(f'block{window}_span{span}',cfg(k,observation_samples=window),
                          [0]*(window-1)+[span]+[100]*window+[-100]*(window-1)+[100])
            tcase('limit_zero',cfg(k,amplitude_limit=0),[0]*32)
            tcase('max_span_equal',cfg(k,amplitude_limit=8191),[-4096,4095]*16)
            tcase('limit_max',cfg(k,amplitude_limit=16383),[-4096,4095]*16)
        if k in (0,1):
            for th in (-4096,-1024,1024,4095):
                tcase('threshold_'+str(th),cfg(k,threshold=th),boundaries*3)
            tcase('max_hysteresis_no_hit',cfg(k,hysteresis=8191),[-4096,4095]*100)
    for c in (cfg(15),cfg(2,window_high=-120),cfg(3,hysteresis=100),cfg(4,width_min=0),
              cfg(5,width_max=2),cfg(6,observation_samples=1),cfg(7,observation_samples=16385)):
        tcase('invalid',c,[-200,200]*10)
    for stage in range(1,5):
        subset=[x for x in triggers if x[0]==stage];lines=[str(len(subset))]
        for cid,(_,name,c,rows,expected) in enumerate(subset):
            lines.append(' '.join(map(str,[cid,name,len(rows),*c.values(),int(not config_ok(c))])))
            for row,ex in zip(rows,expected):lines.append(' '.join(map(str,(*row,*ex))))
            manifest['trigger'].append(dict(stage=stage,id=cid,name=name,config=c,rows=len(rows),hits=sum(h for h,e in expected)))
        (vdir/f'trigger_stage{stage}.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    measurements=[]
    def mcase(stage,name,values,rate=25000000,th=0,h=8,base=100,ts_gap=False,bubbles=True):
        ts=[(base+i+(3 if ts_gap and i>=len(values)//2 else 0))&MASK for i in range(len(values))]
        measurements.append((stage,name,values,ts,rate,th,h,bubbles,stats(values,ts,rate,th,h)))
    for x in (0,1,-1,2047,-2048,4095,-4096):
        mcase(5,'constant_'+str(x),[x]*16384)
        mcase(6,'rms_constant_'+str(x),[x]*16384)
    for n in (1,2,3,16383,16384):
        mcase(5,'ramp_'+str(n),[((i*79)%8192)-4096 for i in range(n)])
        mcase(6,'rms_alternate_'+str(n),[4095 if i%2 else -4096 for i in range(n)])
    for a in ([0,1],[0,-1],[2,3],[0,0,1],[-4096,4095]):mcase(6,'rounding',a)
    for n in (31,257,1024,16384):
        mcase(5,'random_'+str(n),[rng.randint(-4096,4095) for _ in range(n)])
        mcase(6,'rms_random_'+str(n),[rng.randint(-4096,4095) for _ in range(n)])
    for duty in (1,5,9):
        for n in (10,11,20,23,1003):
            # Leading low sample makes even the first rising edge observable.
            vals=[900 if i%10<duty else -900 for i in range(-1,n-1)]
            mcase(7,f'duty{duty}0_n{n}',vals)
    for rate in (10000000,25000000,50000000,65000000):
        for period in (7,13,41):
            vals=[1000 if i%period<period//2 else -1000 for i in range(-1,1501)]
            mcase(7,f'rate{rate}_period{period}',vals,rate=rate)
    for x in (0,100,-100,4095,-4096):mcase(7,'no_period_'+str(x),[x]*1024)
    mcase(7,'insufficient_amplitude',[(-8 if i%10<5 else 8) for i in range(1024)])
    mcase(7,'exact_boundaries',[-9,-8,-1,0,1,8,9,8,0,-8,-9]*70)
    mcase(7,'zero_hysteresis',[0,0,0,-1,0,1,1,0,-1]*70,h=0)
    mcase(7,'only_partial',[-100]*10+[100]*10+[-100]*10)
    mcase(7,'exact_one_period',[-100]+[100]*5+[-100]*5+[100])
    mcase(7,'timestamp_wrap',[-100,100,100,-100]*100,base=MASK-13)
    mcase(7,'timestamp_gap',[-100,100,100,-100]*100,ts_gap=True)
    for clipped in (False,True):
        vals=[int(2500*math.sin(2*math.pi*i/37))+rng.randint(-5,5) for i in range(4096)]
        if clipped:vals=[max(-300,min(300,x)) for x in vals]
        mcase(7,'noisy_clipped' if clipped else 'noisy_sine',vals,h=20)
    vals=[]
    for p in (11,12,13,12,11,13)*12:vals.extend([-100]*(p//2)+[100]*(p-p//2))
    mcase(7,'noninteger_average',vals)
    mcase(7,'maximum_period_count',[-4096,4095]*8192,rate=65000000,bubbles=False)
    mcase(7,'maximum_hysteresis',[-4096,4095]*512,h=8191)
    for th in (-4096,-1024,1024,4095):
        mcase(7,'threshold_'+str(th),[-2000]*4+[2000]*4+([-2000]*4+[2000]*4)*20,th=th)
    for stage in (5,6,7):
        subset=[x for x in measurements if x[0]==stage];vs=[str(len(subset))];es=[]
        for cid,(_,name,values,ts,rate,th,h,bubbles,expected) in enumerate(subset):
            vs.append(' '.join(map(str,[cid,name,len(values),rate,th,h,int(bubbles)])))
            vs.extend(f'{x} {t}' for x,t in zip(values,ts));es.append(' '.join(map(str,[cid,*expected])))
            manifest['measurement'].append(dict(stage=stage,id=cid,name=name,expected=expected))
        (vdir/f'measure_stage{stage}.txt').write_text('\n'.join(vs)+'\n',encoding='utf-8')
        (edir/f'measure_stage{stage}.txt').write_text('\n'.join(es)+'\n',encoding='utf-8')
    # Actual trigger -> circular BRAM -> system readout -> measurement path.
    lines=['9'];el=[]
    for k in range(9):
        c=cfg(k);prefix=[-300]*20+[300]*5+[-300]*6+[0]*20+[300,-300]*20
        vals=(prefix+[(-300 if i%13<6 else 300) for i in range(16500)])[:16500]
        rows=[(x,i,1,1,0,int(k==8 and i in (24,25,26))) for i,x in enumerate(vals)]
        hits=trigger_oracle(c,rows);ti=next(i for i,(hit,_) in enumerate(hits) if hit and i>=16)
        frame=vals[ti-16:ti-16+16384];assert len(frame)==16384
        expected=stats(frame,list(range(ti-16,ti-16+16384)),25000000,0,8)
        lines.append(' '.join(map(str,[k,len(vals),ti,*c.values()])))
        lines.extend(f'{x} {r[5]}' for x,r in zip(vals,rows));el.append(' '.join(map(str,[k,*expected])))
        manifest['integration'].append(dict(kind=k,trigger_timestamp=ti,expected=expected))
    (vdir/'integration.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (edir/'integration.txt').write_text('\n'.join(el)+'\n',encoding='utf-8')
    (edir/'oracle_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f"ORACLE_PASS seed={seed} trigger_cases={len(triggers)} measurement_cases={len(measurements)} integration_frames=9")
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-output',type=Path,required=True);p.add_argument('--seed',type=int,default=20261020);a=p.parse_args();generate(a.output,a.expected_output,a.seed)
