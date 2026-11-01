"""Audit actual vendor FFT CSV against the independent direct DFT and integer math."""
import argparse,csv,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC'/'protocol'))
from spectrum_reference import amplitude,one_sided_power,summary,N

def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def ints(p):return [[int(t) for t in line.split()] for line in p.read_text().splitlines()]
def nearest_sqrt(x):
    r=math.isqrt(x);return r+int(x-r*r>r)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--expected',type=Path,required=True);ap.add_argument('--traces',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();oracle=json.loads((a.expected/'oracle.json').read_text());cases={c['id']:c for c in oracle['cases']}
    max_component=0;max_amplitude=0;max_rms=0;bins_count=0;results_count=0;actual={};case_metrics=[]
    for prefix,selected in (('spectrum',list(range(42))),('spectrum_capture',[42,43])):
        br=rows(a.traces/f'{prefix}_bins.csv');rr=rows(a.traces/f'{prefix}_results.csv')
        assert len(br)==len(selected)*N and len(rr)==len(selected)
        assert [int(r['case_id']) for r in rr]==selected
        for ci,cid in enumerate(selected):
            c=cases[cid];gold=ints(a.expected/f'fft_{cid}.txt');z=[]
            for k,r in enumerate(br[ci*N:(ci+1)*N]):
                assert int(r['case_id'])==cid and int(r['bin'])==k
                re,im,p=map(int,(r['real'],r['imag'],r['power']));assert p==re*re+im*im
                err=max(abs(re-gold[k][1]),abs(im-gold[k][2]));assert err<=oracle['component_tolerance'],(cid,k,err)
                max_component=max(max_component,err);z.append(complex(re,im));bins_count+=1
            actual[cid]=z;r=rr[ci];s=c['result'];calc=summary(z,c['rate'],c['window'])
            for field,key in [('valid','valid'),('peak_bin','peak_bin'),('frequency_hz','frequency')]:assert int(r[field])==s[key]==calc[key],(cid,field,r,s,calc)
            k=s['peak_bin'];search=range(s['search_first'],s['search_last']+1)
            actual_peak=max(search,key=lambda i:(int(abs(z[i])**2),-i));power=int(r['peak_power']);assert power==int(z[actual_peak].real)**2+int(z[actual_peak].imag)**2
            amp=nearest_sqrt(power<<(10 if c['window'] else 8));rms=nearest_sqrt(power<<(9 if c['window'] else 7))
            if not s['valid']:amp=rms=0
            assert int(r['amplitude_q16'])==amp and int(r['rms_q16'])==rms
            ae=abs(amp-s['amplitude_q16']);re=abs(rms-s['rms_q16']);assert max(ae,re)<=oracle['amplitude_tolerance_q16']
            max_amplitude=max(max_amplitude,ae);max_rms=max(max_rms,re)
            assert int(r['dc_mean_q16'])==s['dc_q16'] and int(r['clipped'])==int(c['otr'])
            # Parseval, with a small absolute allowance for FFT integer rounding.
            spectral=sum(abs(v)**2 for v in z)/N/(8*8)
            temporal=sum(v*v for v in c['weighted_samples'])/(8*8)
            assert abs(spectral-temporal)<=max(5.0,temporal*0.001),(cid,'Parseval',spectral,temporal)
            results_count+=1;case_metrics.append(dict(id=cid,name=c['name'],window=c['window'],peak_bin=k,amplitude_error_q16=ae,rms_error_q16=re))
    raw=rows(a.traces/'fft_raw.csv');assert len(raw)==5*N
    raw_errors=[]
    for cid in range(5):
        gold=ints(a.expected/f'raw_{cid}.txt');err=0;z=[]
        for k,r in enumerate(raw[cid*N:(cid+1)*N]):
            assert int(r['case_id'])==cid and int(r['bin'])==k
            re,im=int(r['real']),int(r['imag']);err=max(err,abs(re-gold[k][1]),abs(im-gold[k][2]));z.append(complex(re,im))
        assert err<=oracle['component_tolerance'];raw_errors.append(err)
        if cid in (0,1):assert max(range(N),key=lambda k:abs(z[k]))==(37 if cid==0 else N-37)
    roi=rows(a.traces/'spectrum_capture_roi.csv');assert len(roi)==2*N
    for n,r in enumerate(roi):
        cid=42+n//N;i=n%N;c=cases[cid];original=7680+i
        assert int(r['case_id'])==cid and int(r['roi_index'])==i and int(r['frame_index'])==original
        assert int(r['signed'])==c['quantized_samples'][i] and int(r['otr'])==int(original%17==0 or original==8192)
        assert int(r['timestamp'],16)==(c['timestamp']+i)&((1<<64)-1)
    trends=[]
    for window in (0,1):
        dual=next(c for c in cases.values() if c['name']=='dual' and c['window']==window);z=actual[dual['id']]
        a1,a2=amplitude(z[37],window),amplitude(z[113],window)
        assert abs(a1-1000)<0.125 and abs(a2-500)<0.125
        sq=next(c for c in cases.values() if c['name']=='square' and c['window']==window);z=actual[sq['id']]
        harmonic=[amplitude(z[8*j],window) for j in (1,2,3,4,5)]
        assert harmonic[1]<1 and harmonic[3]<1 and abs(harmonic[2]/harmonic[0]-1/3)<0.01 and abs(harmonic[4]/harmonic[0]-1/5)<0.01
        trends.append(dict(window=window,dual_amplitudes=[a1,a2],square_harmonics=harmonic))
    leaks=[]
    for window in (0,1):
        c=next(c for c in cases.values() if c['name']=='noncoherent' and c['window']==window);p=one_sided_power(actual[c['id']],window)
        leaks.append(sum(v for k,v in enumerate(p) if abs(k-37)>2))
    assert leaks[1]<leaks[0]*0.05
    out=dict(verdict='PASS',seed=oracle['seed'],spectrum_frames=44,spectrum_bins=bins_count,raw_frames=5,raw_bins=5*N,roi_points=len(roi),
        max_component_error=max_component,raw_max_errors=raw_errors,max_amplitude_error_q16=max_amplitude,max_rms_error_q16=max_rms,
        hann_to_rect_far_leakage_ratio=leaks[1]/leaks[0],trends=trends,cases=case_metrics)
    a.output.write_text(json.dumps(out,indent=2),encoding='utf8');print('SPECTRUM_TRACE_AUDIT_PASS',json.dumps({k:v for k,v in out.items() if k not in ('cases','trends')}))
if __name__=='__main__':main()
