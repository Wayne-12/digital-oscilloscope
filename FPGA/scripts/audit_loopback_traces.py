"""Independently audit stored traces and measure loopback behavior."""
import argparse,cmath,csv,json,math
from pathlib import Path

def fit_amplitude(values,start,w):
    # Three-parameter least squares (DC, sin, cos), independent of record coherence.
    a=[[0.0]*3 for _ in range(3)];b=[0.0]*3
    for n,y in enumerate(values,start):
        v=[1.0,math.sin(w*n),math.cos(w*n)]
        for i in range(3):
            b[i]+=v[i]*y
            for j in range(3):a[i][j]+=v[i]*v[j]
    for i in range(3):
        div=a[i][i]
        for j in range(i,3):a[i][j]/=div
        b[i]/=div
        for k in range(3):
            if k==i:continue
            factor=a[k][i]
            for j in range(i,3):a[k][j]-=factor*a[i][j]
            b[k]-=factor*b[i]
    return math.hypot(b[1],b[2])
def harmonic(values,k):
    v=values[-2048:];return 2*abs(sum(y*cmath.exp(-2j*math.pi*k*n/1024) for n,y in enumerate(v)))/len(v)

def audit(traces,oracle,output):
    g=json.loads(oracle.read_text());results=[];saved={};total=0;reported=0
    for p in g['profiles']:
        pid=p['id']
        for delay in (3500,7000):
            key=f'loop_p{pid}_d{delay}';cases=p['cases']
            words=[[] for _ in cases];values=[[] for _ in cases];full=[[] for _ in cases]
            clips=[[] for _ in cases];counts=[0]*len(cases);otr=[0]*len(cases);rawsum=[0]*len(cases)
            with (traces/f'{key}.csv').open() as f:
                for row in csv.DictReader(f):
                    x={k:int(v) for k,v in row.items()};c=x['case_id']
                    assert x['cycle']==counts[c];counts[c]+=1;clips[c].append(x['channel_clipped'])
                    if x['cap_valid']:
                        assert x['timestamp']==len(words[c]) and x['signed']==2047-x['raw']
                        assert 0<=x['raw']<=4095 and x['otr'] in (0,1)
                        words[c].append((x['otr']<<15)|x['raw']);full[c].append(x['signed'])
                        otr[c]+=x['otr'];rawsum[c]+=x['raw']
                        if x['timestamp']>=128:values[c].append(x['signed'])
            summaries=[]
            for c,ref in enumerate(cases):
                v=values[c]
                assert counts[c]==ref['cycles'] and len(words[c])==ref['captured'] and len(v)==ref['measured']
                assert min(v)==ref['minimum'] and max(v)==ref['maximum'] and sum(v)==ref['sum']
                assert sum(y*y for y in v)==ref['sum_squares']
                assert otr[c]==ref['otr'] and rawsum[c]==ref['raw_sum'] and sum(words[c])==ref['word_sum']
                assert sum(clips[c][:ref['captured']])==ref['clipped']
                summaries.append(dict(name=ref['name'],captured=len(words[c]),reported=len(words[c]),minimum=min(v),maximum=max(v),peak_to_peak=max(v)-min(v),mean=sum(v)/len(v),otr=otr[c],channel_clipped=ref['clipped']))
            read_counts=[0]*len(cases)
            with (traces/f'{key}_report.csv').open() as f:
                for row in csv.DictReader(f):
                    x={k:int(v) for k,v in row.items()};c=x['case_id'];i=read_counts[c]
                    assert x['address']==i and x['timestamp']==i and x['word']==words[c][i]
                    assert x['word']&0x7000==0 and x['otr']==x['word']>>15
                    assert x['signed']==2047-(x['word']&4095)
                    read_counts[c]+=1
            assert read_counts==[len(x) for x in words]
            total+=sum(counts);reported+=sum(read_counts)
            results.append(dict(key=key,verdict='PASS',cases=summaries))
            if delay==3500:saved[pid]=dict(values=values,full=full,summary=summaries)
    # Explicit behavioral verdicts, beyond exact per-cycle equality.
    b=saved[0];inv=saved[1]
    for cid in range(14):assert all(x==-y for x,y in zip(b['full'][cid],inv['full'][cid]))
    assert b['summary'][1]['mean']==512 and inv['summary'][1]['mean']==-512
    assert b['summary'][2]['mean']==-512 and inv['summary'][2]['mean']==512
    amps=[0,512,1024,2048,4096,6000,7500]
    p2p=[b['summary'][6+i]['peak_to_peak'] for i in range(7)]
    assert all(a<b for a,b in zip(p2p,p2p[1:]))
    for pid in (*range(9),10,12):assert all(c['otr']==0 for c in saved[pid]['summary'])
    assert sum(c['otr'] for c in saved[9]['summary'])>0
    assert sum(c['otr'] for c in saved[11]['summary'])>0
    noise=saved[4]['values'][6]
    assert min(noise)==-3 and max(noise)==3 and len(set(noise))==7 and abs(sum(noise)/len(noise))<0.25
    assert saved[5]['summary'][11]['minimum']==-1000 and saved[5]['summary'][11]['maximum']==1000
    responses=[]
    for cid,hz in ((3,10000),(4,100000),(5,1000000)):
        ftw=(hz*(1<<32)+12500000)//25000000;w=math.tau*ftw/(1<<32)
        baseline=fit_amplitude(b['values'][cid],128,w)
        lowpass=fit_amplitude(saved[6]['values'][cid],128,w)/baseline
        theory=abs(.125/(1-.875*cmath.exp(-1j*w)))
        fractional=fit_amplitude(saved[2]['values'][cid],128,w)/baseline
        interpolation=abs(.75+.25*cmath.exp(-1j*w))
        assert abs(lowpass-theory)<.01 and abs(fractional-interpolation)<.01
        responses.append(dict(frequency_hz=hz,lowpass_gain=lowpass,lowpass_theory=theory,fractional_gain=fractional,fractional_theory=interpolation))
    assert responses[0]['lowpass_gain']>responses[1]['lowpass_gain']>responses[2]['lowpass_gain']
    even_base=harmonic(b['values'][11],2);even=harmonic(saved[7]['values'][11],2)
    odd_base=harmonic(b['values'][11],3);odd=harmonic(saved[8]['values'][11],3)
    assert even>10 and even>even_base+10 and odd>5 and odd>odd_base+5
    long=b['summary'][-1];assert long['name']=='sine_1000_long' and len(b['values'][-1])>=100000
    data=dict(verdict='PASS',seed=g['seed'],cycles=total,records_reported=reported,
      amplitude_sweep=dict(dac_amplitudes=amps,adc_peak_to_peak=p2p,strictly_increasing=True),
      polarity=dict(baseline_dc_plus=512,inverted_dc_plus=-512,all_samples_exact_negatives=True),
      noise=dict(minimum=min(noise),maximum=max(noise),mean=sum(noise)/len(noise)),frequency_response=responses,
      harmonics=dict(baseline_second=even_base,distorted_second=even,baseline_third=odd_base,distorted_third=odd),
      long_record=dict(samples=long['captured'],measured_samples=len(b['values'][-1]),frequency_hz=1000,full_periods_at_least=4),results=results)
    output.write_text(json.dumps(data,indent=2))
    print(f'TRACE_AUDIT_PASS scenarios=26 cycles={total} reported={reported} monotonic=1 polarity=1 otr_path=1')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--traces',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.traces,a.oracle,a.output)
