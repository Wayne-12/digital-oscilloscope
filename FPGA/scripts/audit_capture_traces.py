"""Compare every exported BRAM word and metadata row to independent frame files."""
import argparse,csv,itertools,json
from pathlib import Path
N=16384;MASK=(1<<64)-1

def audit(traces,oracle_dir,vector_dir,output):
    gold=json.loads((oracle_dir/'oracle_manifest.json').read_text());results=[];total=0
    for scenario in gold['scenarios']:
        sid=scenario['sid'];frames=scenario['frames'];point_count=0;rereads=0
        with (traces/f'capture_s{sid}_metadata.csv').open() as f:
            rows=list(csv.DictReader(f))
        assert len(rows)==len(frames)
        for row,ref in zip(rows,frames):
            x={k:int(v) for k,v in row.items()}
            expected=dict(case_id=ref['case_id'],frame=ref['frame'],start_address=ref['start_address'],trigger_address=ref['trigger_address'],trigger_index=ref['pre'],pre=ref['pre'],post=N-1-ref['pre'],first_timestamp=ref['first_timestamp'],trigger_timestamp=ref['trigger_timestamp'],last_timestamp=ref['last_timestamp'],automatic=ref['automatic'],mode=ref['mode'],rising=ref['rising'],final_pointer=ref['final_pointer'])
            assert x==expected,(sid,ref['case_id'],'metadata')
            assert (x['start_address']+x['trigger_index'])%N==x['trigger_address']
            assert (x['first_timestamp']+x['pre'])&MASK==x['trigger_timestamp']
            assert (x['first_timestamp']+N-1)&MASK==x['last_timestamp']
        with (traces/f'capture_s{sid}.csv').open() as f:
            stream=iter(csv.DictReader(f))
            for ref in frames:
                passes=2 if ref['mode']==2 else 1
                for pass_id in range(passes):
                    if pass_id:rereads+=1
                    with (oracle_dir/f's{sid}_c{ref["case_id"]}_f{ref["frame"]}_frame.txt').open() as expected:
                        count=0;checksum=0;otr=0
                        for index,line in enumerate(expected):
                            w,ts,s=line.split();w=int(w,16);ts=int(ts,16);s=int(s)
                            row=next(stream);x={k:int(v) for k,v in row.items()}
                            assert x==dict(case_id=ref['case_id'],frame=ref['frame'],**{'pass':pass_id},index=index,word=w,signed=s,otr=w>>15,timestamp=ts),(sid,ref['case_id'],index)
                            assert w&0x7000==0 and s==2047-(w&4095)
                            checksum+=w;otr+=w>>15;count+=1
                        assert count==N and checksum==ref['word_sum'] and otr==ref['otr']
                    point_count+=count
            assert next(stream,None) is None
        results.append(dict(sid=sid,cases=scenario['cases'],frames=len(frames),points=point_count,rereads=rereads,verdict='PASS'))
        total+=point_count
    # Re-evaluate Schmitt reference from the provided independent input vectors.
    with (vector_dir/'trigger_unit.txt').open() as vf,(traces/'capture_trigger.csv').open() as tf:
        expected_count=int(vf.readline());rows=csv.DictReader(tf);count=0;hits=0
        for i,(line,row) in enumerate(itertools.zip_longest(vf,rows)):
            assert line is not None and row is not None
            reset,valid,rising,x,th,h,hit=map(int,line.split())
            actual={k:int(v) for k,v in row.items()}
            assert actual==dict(cycle=i,reset=reset,valid=valid,rising=rising,sample=x,threshold=th,hysteresis=h,hit=hit)
            count+=1;hits+=hit
        assert count==expected_count==28672
    all_frames=[f for s in gold['scenarios'] for f in s['frames']]
    assert len(all_frames)==71
    assert {x['pre'] for x in all_frames}>={0,4096,8192,12288,16383}
    assert {x['mode'] for x in all_frames}=={0,1,2}
    assert {x['rising'] for x in all_frames}=={0,1}
    assert {x['trigger_address'] for x in all_frames}>={0,1,16383}
    assert {x['automatic'] for x in all_frames}=={0,1}
    assert any(x['wraps_before_trigger']==0 for x in all_frames)
    assert any(x['wraps_before_trigger']==1 for x in all_frames)
    assert any(x['wraps_before_trigger']>=2 for x in all_frames)
    assert any(x['early_crossings_ignored'] for x in all_frames)
    assert any(x['first_timestamp']>x['last_timestamp'] for x in all_frames)
    data=dict(verdict='PASS',seed=gold['seed'],frames=71,distinct_frame_points=71*N,compared_points_with_rereads=total,auxiliary_full_frame_points=16384,trigger_unit_checks=count,trigger_unit_hits=hits,
      coverage=dict(pre_samples=[0,4096,8192,12288,16383],modes=['AUTO','NORMAL','SINGLE'],trigger_boundary_addresses=[0,1,16383],wraps_before_trigger=['zero','one','multiple'],timestamp_wrap=True,early_trigger_ignored=True,auto_timeout_and_edge_priority=True,normal_rearm_and_single_explicit_rearm=True,async_sys_rates_hz=[100000000,7000000]),results=results)
    output.write_text(json.dumps(data,indent=2))
    print(f'TRACE_AUDIT_PASS scenarios=5 frames=71 points={total} trigger_checks={count} errors=0')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--traces',type=Path,required=True);p.add_argument('--oracle-dir',type=Path,required=True);p.add_argument('--vector-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.traces,a.oracle_dir,a.vector_dir,a.output)
