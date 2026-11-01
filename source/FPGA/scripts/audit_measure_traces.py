"""Check completed trace coverage and re-evaluate the integer oracle from traces."""
import argparse,csv,json
from pathlib import Path
from generate_measure_vectors import trigger_oracle,stats
def records(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return [{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
def audit(td,ed,vd,out):
    manifest=json.loads((ed/'oracle_manifest.json').read_text(encoding='utf-8'))
    assert len(list(td.glob('*.csv')))==9,'Missing or extra traces'
    checks=0;trigger_samples=0;measurements=0;points=0
    for stage in range(1,5):
        rows=records(td/f'trigger_stage{stage}.csv')
        refs=[r for r in manifest['trigger'] if r['stage']==stage]
        assert len(rows)==sum(r['rows'] for r in refs)
        stimulus=(vd/f'trigger_stage{stage}.txt').read_text(encoding='utf-8').splitlines()
        assert int(stimulus[0])==len(refs)
        cursor=1
        for ref in refs:
            header=stimulus[cursor].split();cursor+=1
            assert int(header[0])==ref['id'] and int(header[2])==ref['rows']
            expected_rows=[list(map(int,l.split())) for l in stimulus[cursor:cursor+ref['rows']]];cursor+=ref['rows']
            data=[r for r in rows if r['case_id']==ref['id']]
            assert [r['index'] for r in data]==list(range(ref['rows']))
            for r,expected in zip(data,expected_rows):
                assert list(r.values())[2:]==[*expected,int(header[-1])]
            ex=trigger_oracle(ref['config'],[(r['value'],r['timestamp'],r['valid'],r['enable'],r['reset'],r['otr']) for r in data])
            assert [(r['hit'],r['timestamp_error']) for r in data]==ex
            assert sum(r['hit'] for r in data)==ref['hits']
            checks+=9*len(data);trigger_samples+=len(data)
        assert cursor==len(stimulus)
    for stage in (5,6,7):
        rows=records(td/f'measure_stage{stage}.csv');refs=[r for r in manifest['measurement'] if r['stage']==stage]
        assert len(rows)==len(refs)
        for r,ref in zip(rows,refs):
            assert list(r.values())==[ref['id'],*ref['expected']]
            measurements+=1;checks+=14
    lines=(vd/'integration.txt').read_text(encoding='utf-8').splitlines();cursor=1
    rows=records(td/'integration_points.csv');mr=records(td/'integration_measure.csv');assert len(mr)==9
    for ref in manifest['integration']:
        header=list(map(int,lines[cursor].split()));cursor+=1
        cid,n,ti=header[:3];stim=[tuple(map(int,l.split())) for l in lines[cursor:cursor+n]];cursor+=n
        data=[r for r in rows if r['case_id']==cid];assert len(data)==16384
        for i,r in enumerate(data):
            x,otr=stim[ti-16+i]
            assert [r['index'],r['word'],r['signed'],r['timestamp']]==[i,(otr<<15)|(2047-x),x,ti-16+i]
        expected=stats([r['signed'] for r in data],[r['timestamp'] for r in data],25000000,0,8)
        assert list(mr[cid].values())==[cid,*expected]==[cid,*ref['expected']]
        points+=len(data);checks+=4*len(data)+14
    assert len(rows)==points
    result=dict(verdict='PASS',seed=manifest['seed'],trigger_cases=len(manifest['trigger']),trigger_samples=trigger_samples,
                measurement_cases=measurements,integration_frames=9,integration_points=points,field_checks=checks)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8');print('TRACE_AUDIT_PASS',json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--traces',type=Path,required=True);p.add_argument('--expected',type=Path,required=True);p.add_argument('--vectors',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.traces,a.expected,a.vectors,a.output)
