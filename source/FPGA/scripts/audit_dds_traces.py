"""Read captured DUT traces, verify statistics and measured sample periods."""
import argparse,csv,json,math
from pathlib import Path

def audit(traces,oracle,output):
    gold=json.loads(oracle.read_text());results=[]
    for rate in gold['clock_rates']:
        groups=[[] for _ in gold['cases']];row_count=0
        with (traces/f'dds_r{rate}.csv').open() as f:
            for row in csv.DictReader(f):
                r={k:int(v) for k,v in row.items()}
                assert r['cycle']==row_count
                assert 0<=r['code']<=16383
                assert 0<=r['input_latch']<=16383 and 0<=r['dac_latch']<=16383
                groups[r['case_id']].append(r);row_count+=1
        assert row_count==gold['total_cycles']
        sample_period_ps=groups[0][1]['time_ps']-groups[0][0]['time_ps']
        actual_clock_hz=1e12/sample_period_ps
        assert all(b['time_ps']-a['time_ps']==sample_period_ps for rows in groups for a,b in zip(rows,rows[1:]))
        cases=[]
        for ref,rows in zip(gold['cases'],groups):
            assert len(rows)==ref['cycles']
            active=[x for x in rows if x['valid']];values=[x['code'] for x in active]
            stats=dict(name=ref['name'],cycles=len(rows),active=len(values))
            if ref['name']=='random_config_reset':
                boundary=[x['code'] for x in rows[4:15]]
                assert boundary==[8192,16382,16383,16383,16383,2,1,0,0,16383,0]
                stats['boundary_codes']=boundary
            if ref['active_samples']:
                assert len(values)==ref['active_samples']
                assert min(values)==ref['minimum'] and max(values)==ref['maximum'] and sum(values)==ref['sum']
                wraps=[i for i in range(1,len(active)) if active[i]['phase']<active[i-1]['phase']]
                assert wraps==ref['phase_wrap_indices']
                stats.update(minimum=min(values),maximum=max(values),mean=sum(values)/len(values),wraps=len(wraps))
                if ref['name'] in ('sine_coherent','square','triangle'):assert sum(values)==8192*len(values)
                if ref['name'].startswith('sine_') and ref['name']!='sine_coherent':
                    requested=int(ref['name'][5:])*rate/25_000_000
                    actual=rate*ref['ftw']/(1<<32)
                    error=actual-requested
                    assert abs(error)<=rate/(1<<33)+1e-9
                    crossings=[i for i in range(1,len(values)) if values[i-1]<=8192<values[i]]
                    periods=[b-a for a,b in zip(crossings,crossings[1:])]
                    theory=(1<<32)/ref['ftw']
                    assert len(periods)>=2 and all(abs(p-theory)<=1.01 for p in periods)
                    measured=actual_clock_hz*(len(crossings)-1)/(crossings[-1]-crossings[0])
                    stats.update(requested_hz=requested,ftw_frequency_hz=actual,ftw_error_hz=error,
                                 half_ftw_lsb_hz=rate/(1<<33),quantized_clock_ftw_frequency_hz=actual_clock_hz*ref['ftw']/(1<<32),measured_crossing_frequency_hz=measured,
                                 period_samples=periods,period_tolerance_samples=1.01)
            cases.append(stats)
        results.append(dict(rate_hz=rate,simulated_clock_hz=actual_clock_hz,sample_period_ps=sample_period_ps,verdict='PASS',rows=row_count,cases=cases))
    output.write_text(json.dumps(dict(verdict='PASS',results=results),indent=2))
    print(f'TRACE_AUDIT_PASS rates=4 rows={gold["total_cycles"]*4}')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--traces',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.traces,a.oracle,a.output)
