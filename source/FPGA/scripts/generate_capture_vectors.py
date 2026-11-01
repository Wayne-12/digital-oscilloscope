"""Independent trigger search and chronological frame oracle (no DUT imports)."""
import argparse,json,random
from pathlib import Path
N=16384;MASK=(1<<64)-1

def descriptors(sid):
    out=[]
    def add(name,pre,t,mode=2,rising=1,timeout=None,flags=0,quiet=False,threshold=0,h=8,wrap_ts=False):
        out.append(dict(name=name,pre=pre,target=t,mode=mode,rising=rising,timeout=timeout or max(1,t-pre+100),flags=flags,quiet=quiet,threshold=threshold,hysteresis=h,wrap_ts=wrap_ts,frames=2 if flags&2 else 1))
    if sid==0:
        for j,pre in enumerate((0,4096,8192,12288,16383)):
            for k in range(3):
                t=max(pre,2) if k==0 else N+pre if k==1 else 3*N+pre+1
                add(f'ratio{j}_wrap{k}',pre,t,mode=(j+k)%3,rising=(j+k)%2,flags=16 if k==1 else 0)
        for t in (N-1,N,N+1):add(f'boundary_{t}',8192,t,mode=1,rising=t%2)
        for pre,timeout in ((0,1),(8192,37),(16383,1)):
            add(f'auto_quiet_{pre}',pre,pre+timeout-1,mode=0,timeout=timeout,quiet=True)
        add('edge_wins_timeout',4096,4128,mode=0,timeout=33)
        add('normal_release_rearm',8192,12000,mode=1,flags=2|16)
        add('single_explicit_rearm',12288,17001,mode=2,flags=2)
        add('timestamp_wrap',8192,2*N+1,mode=2,wrap_ts=True)
        add('zero_hyst_rise',0,67,mode=1,h=0)
        add('zero_hyst_fall',4096,4197,mode=2,rising=0,h=0)
        add('config_snapshot',4096,6201,mode=2,flags=4)
        add('early_cross_ignored',8192,8224,mode=1,flags=8)
        add('negative_threshold',4096,13017,mode=1,threshold=-1024,h=12)
        add('positive_threshold',12288,18001,mode=2,rising=0,threshold=1024,h=17)
    elif sid<4:
        for j,pre in enumerate((0,4096,8192,12288,16383)):
            add(f'ratio{j}_rate',pre,(j%3)*N+max(pre,2),mode=j%3,rising=j%2,flags=16)
        add('auto_quiet',8192,8255,mode=0,timeout=64,quiet=True)
        add('normal_release_rearm',4096,N+1,mode=1,flags=2)
        add('single_explicit_rearm',16383,2*N,mode=2,flags=2)
        add('boundary_last',8192,2*N-1,mode=1,rising=0)
    else:
        add('slow_reader_half',8192,N,mode=1)
        add('slow_reader_last',16383,2*N-1,mode=2)
        add('slow_auto_zero',0,31,mode=0,timeout=32,quiet=True)
        add('slow_single_rearm',4096,N+1,mode=2,flags=2|16)
    return out

def generate(vdir,edir,seed):
    vdir.mkdir(parents=True,exist_ok=True);edir.mkdir(parents=True,exist_ok=True)
    manifest=[];frames=0;source_samples=0
    for sid,rate in enumerate((25000000,10000000,50000000,65000000,65000000)):
        ds=descriptors(sid);entries=[]
        with (vdir/f'cases_s{sid}.txt').open('w') as cases,(edir/f'frames_s{sid}.txt').open('w') as headers:
            for cid,c in enumerate(ds):
                cases.write(f'{cid} {c["name"]} {c["mode"]} {c["pre"]} {c["rising"]} {c["threshold"]} {c["hysteresis"]} {c["timeout"]} {c["flags"]} {c["frames"]}\n')
                for f in range(c['frames']):
                    rng=random.Random(seed+sid*104729+cid*7919+f*65537)
                    t=c['target'];post=N-1-c['pre'];length=t+post+1
                    base=((seed<<40)+(sid<<32)+(cid<<20)+(f<<18))&MASK
                    if c['wrap_ts']:base=(MASK+1-c['target']-5+f*5)&MASK
                    samples=[];q=False;found=None;eligible_wait=0;early=0;automatic=False
                    for i in range(length):
                        th=c['threshold'];h=c['hysteresis'];rise=bool(c['rising'])
                        if i>t:val=rng.randrange(-2048,2048)
                        elif i==0:val=th-h-1 if rise else th+h+1
                        elif c['flags']&8 and i==1:val=th+h+1 if rise else th-h-1
                        elif c['flags']&8 and 2<=i<=c['pre']:val=th+h+4 if rise else th-h-4
                        elif c['flags']&8 and i==c['pre']+1:val=th-h-1 if rise else th+h+1
                        elif i==t and not c['quiet']:val=th+h+1 if rise else th-h-1
                        else:val=th+rng.randrange(-max(0,h-1),max(0,h-1)+1)
                        val=max(-2048,min(2047,val));raw=2047-val
                        otr=int(rng.getrandbits(1))
                        ts=(base+i)&MASK;samples.append((raw,otr,ts,val))
                        if found is None:
                            hit=q and (val>th+h if rise else val<th-h)
                            if hit:q=False
                            elif val<=th-h if rise else val>=th+h:q=True
                            eligible=i>=c['pre'];due=c['mode']==0 and eligible and eligible_wait==c['timeout']-1
                            if eligible and (hit or due):found=i;automatic=bool(due and not hit)
                            elif eligible and c['mode']==0:eligible_wait+=1
                            elif hit:early+=1
                    assert found==t,(sid,cid,c,found)
                    begin=found-c['pre'];frame=samples[begin:found+post+1];assert len(frame)==N
                    stem=f's{sid}_c{cid}_f{f}'
                    with (vdir/f'{stem}_stim.txt').open('w') as inp:
                        for raw,otr,ts,val in samples:inp.write(f'{raw:03x} {otr} {ts:016x}\n')
                    with (edir/f'{stem}_frame.txt').open('w') as out:
                        for raw,otr,ts,val in frame:out.write(f'{((otr<<15)|raw):04x} {ts:016x} {val}\n')
                    start=begin%N;addr=t%N;endptr=length%N
                    headers.write(f'{length} {t} {start} {addr} {endptr} {frame[0][2]:016x} {samples[t][2]:016x} {frame[-1][2]:016x} {int(automatic)}\n')
                    entries.append(dict(case_id=cid,frame=f,**c,source_samples=length,trigger_ordinal=t,start_address=start,trigger_address=addr,final_pointer=endptr,first_timestamp=frame[0][2],trigger_timestamp=samples[t][2],last_timestamp=frame[-1][2],automatic=int(automatic),early_crossings_ignored=early,first_word=(frame[0][1]<<15)|frame[0][0],trigger_word=(frame[c['pre']][1]<<15)|frame[c['pre']][0],last_word=(frame[-1][1]<<15)|frame[-1][0],word_sum=sum((x[1]<<15)|x[0] for x in frame),otr=sum(x[1] for x in frame),wraps_before_trigger=t//N))
                    frames+=1;source_samples+=length
        (vdir/f'meta_s{sid}.txt').write_text(f'{len(ds)} {sum(x["frames"] for x in ds)} {seed} {rate} {7000000 if sid==4 else 100000000}\n')
        manifest.append(dict(sid=sid,adc_rate_hz=rate,sys_rate_hz=7000000 if sid==4 else 100000000,cases=len(ds),frames=entries))
    # Standalone hysteresis: random dither, exact boundaries, h=0, signed limits.
    rng=random.Random(seed^0x6841);unit=[];q=False;last_cfg=None
    for direction in (0,1):
        for threshold,h in ((0,8),(0,0),(-2048,1),(2047,1),(-1024,17),(1024,4095),(0,8191)):
            for k in range(2048):
                clear=int(k==0 or k==1024);valid=int(rng.randrange(7)!=0)
                if k%128 in (0,1):x=threshold+(-h if direction else h)
                elif k%128==2:x=threshold+(h if direction else -h)
                elif k%128==3:x=threshold+(h+1 if direction else -h-1)
                else:x=threshold+rng.randrange(-max(h-1,0),max(h-1,0)+1)
                x=max(-2048,min(2047,x))
                if clear:q=False
                hit=int(not clear and valid and q and (x>threshold+h if direction else x<threshold-h))
                unit.append((clear,valid,direction,x,threshold,h,hit))
                if not clear and valid:
                    if hit:q=False
                    elif x<=threshold-h if direction else x>=threshold+h:q=True
    with (vdir/'trigger_unit.txt').open('w') as f:
        f.write(f'{len(unit)}\n')
        for row in unit:f.write(' '.join(map(str,row))+'\n')
    data=dict(seed=seed,frame_length=N,scenarios=manifest,frames=frames,source_samples=source_samples,frame_samples=frames*N,trigger_unit_checks=len(unit))
    (edir/'oracle_manifest.json').write_text(json.dumps(data,indent=2))
    print(f'ORACLE_PASS seed={seed} scenarios=5 frames={frames} frame_samples={frames*N} trigger_checks={len(unit)}')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-output',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    a=p.parse_args();generate(a.output,a.expected_output,a.seed)
