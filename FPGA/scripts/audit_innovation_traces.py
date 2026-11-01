"""Independent Step 12 scoreboard over actual raw capture, FFT, and UART bytes."""
import argparse,csv,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC/protocol'))
from innovation_reference import *
from spectrum_reference import dft,preprocess,round_away
from innovation_channel_oracle import channel_words
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
ap=argparse.ArgumentParser();ap.add_argument('--traces',type=Path,required=True);ap.add_argument('--vectors',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();td=a.traces;plan=json.loads((a.vectors/'plan.json').read_text())
raw=rows(td/'health_raw.csv');assert len(raw)==354304
groups={};timestamps={}
for r in raw:
    p,stage,item,i=map(int,(r['profile'],r['stage'],r['item'],r['index']));key=(p,stage,item);g=groups.setdefault(key,[]);t=timestamps.setdefault(key,[])
    assert i==len(g);word=(int(r['otr'])<<15)|int(r['raw']);assert word&0x7000==0
    g.append(word);ts=int(r['timestamp'],16)
    if t:assert ts==(t[-1]+1)&((1<<64)-1)
    t.append(ts)
fits={int(r['profile']):tuple(int(r[k]) for k in ('gain_q20','offset_q16','correction_q20')) for r in rows(td/'health_fits.csv')};assert len(fits)==8
features=rows(td/'health_features.csv');assert len(features)==8
fft=rows(td/'health_fft.csv');assert len(fft)==8192
computed=[];max_gain_error=0;max_offset_error=0;max_fft_error=0;max_harmonic_ppm_error=0
for p in range(8):
    zero=[2047-(w&4095) for item in range(4) for w in groups[p,0,item]];assert len(zero)==1024
    points=[]
    for item in range(9):
        xs=[2047-(w&4095) for w in groups[p,1,item]];assert len(xs)==2048
        points.append(((item-4)*512,rnd(sum(xs)*65536,2048)))
    gold=fit(points);assert gold==fits[p],(p,'fit',gold,fits[p]);gain,off,corr=gold
    true_gain=19661 if p==2 else 12288 if p==6 else 24576 if p==7 else 16384
    true_gain*=16*(-1 if p==6 else 1);true_off=(32 if p==1 else -37 if p==6 else 91 if p==7 else 0)<<16
    if p!=5:
        ge=abs(gain-true_gain);oe=abs(off-true_off);assert ge<=plan['gain_error_limit_q20'] and oe<=plan['offset_error_limit_q16'],(p,'injected calibration error',ge,oe)
        max_gain_error=max(max_gain_error,ge);max_offset_error=max(max_offset_error,oe)
    p2ps=[]
    for item in range(6):
        xs=[2047-(w&4095) for w in groups[p,2,item]];assert len(xs)==4096;p2ps.append(max(xs)-min(xs))
    assert p2ps==sorted(p2ps)
    if p==4:assert p2ps[-1]==p2ps[-2]==1400
    x=[2047-(w&4095) for w in groups[p,2,5][:1024]];zg=dft(preprocess(x));za=[]
    for k,r in enumerate(fft[p*1024:(p+1)*1024]):
        assert int(r['profile'])==p and int(r['bin'])==k
        re,im,power=map(int,(r['real'],r['imag'],r['power']));assert power==re*re+im*im
        error=max(abs(re-round_away(zg[k].real)),abs(im-round_away(zg[k].imag)));assert error<=128,(p,k,error);max_fft_error=max(max_fft_error,error);za.append(complex(re,im))
    powers=[int(za[k].real)**2+int(za[k].imag)**2 for k in (4,8,12)];harm=rnd((powers[1]+powers[2])*1000000,powers[0])
    harmonic_gold=round_away((abs(zg[8])**2+abs(zg[12])**2)*1000000/abs(zg[4])**2)
    he=abs(harm-harmonic_gold);assert he<=32;max_harmonic_ppm_error=max(max_harmonic_ppm_error,he)
    expected_p2p=abs(gain)*8192;loss=max(0,rnd((expected_p2p-p2ps[-1]*1048576)*1000000,expected_p2p))
    noise=rnd((len(zero)*sum(v*v for v in zero)-sum(zero)**2)*65536,len(zero)**2)
    cur=dict(valid=1,gain=gain,offset=off,noise=noise,compression=loss,harmonic=harm,otr=sum(w>>15 for w in groups[p,2,5]));computed.append(cur)
    actual=features[p];assert int(actual['profile'])==p
    assert {k:int(actual[k]) for k in ('gain','offset','noise','compression','harmonic','otr')}=={k:cur[k] for k in ('gain','offset','noise','compression','harmonic','otr')}
for p,cur in enumerate(computed):
    baseline=computed[7] if p==7 else computed[0];mask,kind=classify(baseline,cur,plan['limits'])
    assert (mask,kind)==(int(features[p]['alarms']),int(features[p]['classification']))
    assert kind==(0 if p==7 else p),(p,'fault classification',kind)
display=rows(td/'health_display.csv');assert len(display)==34816;displays={}
for r in display:
    p,k,i=map(int,(r['profile'],r['kind'],r['index']));source_key=(p,2,5) if k==0 else (p,3,0);word=groups[source_key][i];ts=timestamps[source_key][i]
    assert int(r['word'],16)==word and int(r['timestamp'],16)==ts
    g,b,c=fits[p];value,sat=apply(word,b,c);assert not sat and int(r['display_q16'])==value
    if k==1:assert word>>15==1
    else:displays[p,i]=value
normalization_error=0
for p in (1,2,6,7):
    for i in range(4096):normalization_error=max(normalization_error,abs(displays[p,i]-displays[0,i]))
assert normalization_error<=6*65536,('relative normalization',normalization_error)
jobs=[];spikes=0;roi_points=0;raw_reads=0;channel_profiles=[]
for backend,n in [('bram',16384)]:
    for profile in (-1,0,1,2,3):
        base=f'innovation_{backend}'+(f'_channel{profile}' if profile>=0 else '')
        if profile<0: words=source_words(n)
        else:
            words,channel_info=channel_words(td/f'{base}_source.csv',profile,n)
            channel_profiles.append(dict(backend=backend,**channel_info))
        stats=moments(words)
        for job,roi_count in enumerate(plan['roi_counts']):
            prefix=f'{base}_job{job}';wire=bytes.fromhex((td/f'{prefix}_uart.hex').read_text());container=bytes.fromhex((td/f'{prefix}_container.hex').read_text())
            decoded,reassembled,segments=assemble_uart(wire);assert reassembled==container
            assert len(container)==137+800*14+roi_count*3 and len(wire)==len(container)+segments*32
            assert decoded['count']==n and decoded['trigger']==n//2 and decoded['first']==0xfffffffffffffff0 and decoded['roi_start']==n//2-roi_count//2
            result_id=job|((profile+1)<<8)
            assert decoded['storage']==0 and decoded['result_id']==result_id and decoded['moments']==stats
            coverage=[0]*n
            for bucket in decoded['buckets']:
                lo,hi=bucket['first'],bucket['last'];xs=[2047-(w&4095) for w in words[lo:hi+1]];mn,mx=min(xs),max(xs)
                assert (bucket['min'],bucket['max'],bucket['min_index'],bucket['max_index'],bucket['otr'])==(mn,mx,lo+xs.index(mn),lo+xs.index(mx),int(any(w>>15 for w in words[lo:hi+1])))
                if profile<0: assert mn==-2048 and mx==2047
                for i in range(lo,hi+1):coverage[i]+=1
                spikes+=2
            assert min(coverage)==max(coverage)==1
            for r in decoded['roi']:assert r['word']==words[r['index']] and r['timestamp']==(decoded['first']+r['index'])&((1<<64)-1)
            assert decoded['roi'][roi_count//2]['index']==n//2
            reduction=1-len(wire)/(2*n);assert reduction>=plan['minimum_wire_reduction'][backend]
            jobs.append(dict(backend=backend,channel_profile=profile,job=job,count=n,roi_count=roi_count,container_bytes=len(container),wire_bytes=len(wire),uart_segments=segments,reduction=reduction,raw_crc32=stats['crc']))
            roi_points+=roi_count;raw_reads+=n
out=dict(verdict='PASS',seed=plan['seed'],profiles=8,raw_samples=len(raw),display_samples=len(display),fft_bins=len(fft),
 max_gain_error_q20=max_gain_error,max_offset_error_q16=max_offset_error,max_fft_component_error=max_fft_error,max_harmonic_ratio_error_ppm=max_harmonic_ppm_error,
 max_normalized_difference_q16=normalization_error,fingerprints=computed,capture_jobs=jobs,channel_capture_profiles=channel_profiles,raw_read_comparisons=raw_reads,spike_comparisons=spikes,roi_comparisons=roi_points)
a.output.write_text(json.dumps(out,indent=2),encoding='utf8');print('INNOVATION_TRACE_AUDIT_PASS',json.dumps({k:v for k,v in out.items() if k not in ('fingerprints','capture_jobs')}))
