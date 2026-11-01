"""Audit actual CSV output, including independent index incidence counts."""
import argparse,csv,json,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'PC'/'protocol'))
from envelope_reference import summarize
ap=argparse.ArgumentParser();ap.add_argument('--vectors',type=Path,required=True);ap.add_argument('--expected',type=Path,required=True);ap.add_argument('--traces',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
def rows(name):
    with (a.traces/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def group(data):
    result={}
    for row in data:result.setdefault(int(row['case']),[]).append(row)
    return result
def env_tuple(r):return tuple(int(r[k]) for k in ('bucket','first','last','count','min','max','min_index','max_index','otr'))
def roi_tuple(r):return int(r['roi_index']),int(r['frame_index']),int(r['word'],16),int(r['signed']),int(r['timestamp'],16)
def check_coverage(n,actual):
    seen=bytearray(n)
    for row in actual:
        lo,hi=int(row['first']),int(row['last']);assert 0<=lo<=hi<n
        for i in range(lo,hi+1):seen[i]+=1
    assert all(v==1 for v in seen)
meta=json.loads((a.expected/'oracle.json').read_text());cases=rows('multires_cases.csv');bs=group(rows('multires_buckets.csv'));rs=group(rows('multires_roi.csv'))
assert len(cases)==meta['case_count'];spikes=0
for c,summary in zip(meta['cases'],cases):
    cid=c['id'];n=c['n'];assert int(summary['case'])==cid
    assert tuple(int(summary[k]) for k in ('samples','buckets','roi_samples','read_count','response_count','coverage_once'))==(n,c['buckets'],c['roi_count'],n,n,1)
    words=[int(x,16) for x in (a.vectors/f'frame_{cid}.hex').read_text().split()]
    oracle,roi=summarize(words,c['trigger'],c['b'],c['roi'])
    actual=bs[cid];assert [env_tuple(r) for r in actual]==oracle
    stored=[tuple(map(int,line.split())) for line in (a.expected/f'buckets_{cid}.txt').read_text().splitlines()]
    assert stored==oracle;check_coverage(n,actual)
    start,count,_=roi;expected_roi=[(i-start,i,words[i],2047-(words[i]&4095),(c['timestamp']+i)&((1<<64)-1)) for i in range(start,start+count)]
    assert [roi_tuple(r) for r in rs.get(cid,[])]==expected_roi
    if c['pattern'].startswith(('single_','impulses_')):
        positive='positive' in c['pattern'];peak=2047 if positive else -2048
        for i,w in enumerate(words):
            if 2047-(w&4095)==peak:
                found=[row for row in actual if int(row['first'])<=i<=int(row['last'])]
                assert len(found)==1 and int(found[0]['max' if positive else 'min'])==peak;spikes+=1
integration_samples=integration_buckets=integration_roi=0
for backend,n in [('bram',16384)]:
    ic=rows(f'multires_{backend}_cases.csv');ib=group(rows(f'multires_{backend}_buckets.csv'));ir=group(rows(f'multires_{backend}_roi.csv'))
    assert len(ic)==3
    words=[((i*37+123)&4095)|
        (0x8000 if (i%17==0 or i==n//2) else 0) for i in range(n)]
    for j,row in enumerate(ic):
        b=(800,400,100)[j];r=(512,1024,2048)[j]
        assert tuple(int(row[k]) for k in ('case','samples','buckets','roi_samples','read_count','response_count','coverage_once'))==(j,n,b,r,n,n,1)
        oracle,roi=summarize(words,n//2,b,r);assert [env_tuple(x) for x in ib[j]]==oracle;check_coverage(n,ib[j])
        start,count,_=roi;want=[(i-start,i,words[i],2047-(words[i]&4095),(0xfffffffffffffff0+i)&((1<<64)-1)) for i in range(start,start+count)]
        assert [roi_tuple(x) for x in ir[j]]==want
        integration_samples+=n;integration_buckets+=b;integration_roi+=r
result=dict(verdict='PASS',seed=meta['seed'],cases=meta['case_count'],sample_comparisons=meta['sample_comparisons'],bucket_comparisons=meta['bucket_comparisons'],roi_comparisons=meta['roi_comparisons'],
 spike_comparisons=spikes,integration_jobs=3,integration_samples=integration_samples,integration_buckets=integration_buckets,integration_roi=integration_roi)
a.output.write_text(json.dumps(result,indent=2),encoding='utf8');print('TRACE_AUDIT_PASS',json.dumps(result))
