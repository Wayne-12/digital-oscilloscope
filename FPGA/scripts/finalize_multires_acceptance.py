"""Freeze Step 10 source and evidence only after every required gate passed."""
import argparse,hashlib,json,re,zipfile
from datetime import datetime
from pathlib import Path
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--simulation-report',type=Path,required=True);ap.add_argument('--synthesis-report',type=Path,required=True);a=ap.parse_args()
root=a.root.resolve();sim=a.simulation_report.resolve();synth=a.synthesis_report.resolve();sm=read(sim/'manifest.json');sy=read(synth/'manifest.json')
assert sm['verdict']==sy['verdict']=='PASS'
assert len(sm['seeds'])>=2 and len(sm['seeds'])==len(set(sm['seeds']))
assert sm['replay']['verdict']==sm['project']['verdict']=='PASS' and sm['project']['clean_rebuild']
assert sm['replay']['identical_traces']==sm['project']['identical_traces']==6
assert len(sm['negative_tests'])==3 and all(x['verdict']=='PASS' for x in sm['negative_tests'])
for h in sm['source_sha256']:assert sha(Path(h['Path'])).upper()==h['Hash'].upper(),h['Path']
for h in sy['source_sha256']:assert sha(root/'FPGA'/h['file']).upper()==h['sha256'].upper(),h['file']
bad=r'^\s*(WARNING:|CRITICAL WARNING:|ERROR:|Fatal:|TEST_FAIL)'
for top in ('tb_multires','tb_multires_bram'):
    for log in ('xvlog','elaborate','simulate'):
        assert not re.search(bad,(sim/f'project/{top}.{log}.log').read_text(encoding='utf-8-sig',errors='replace'),re.M)
assert not re.search(bad,(synth/'console.log').read_text(encoding='utf-8-sig'),re.M)
for r in sm['results']:
    au=r['audit'];assert au['verdict']=='PASS' and au['cases']==80
    assert (au['sample_comparisons'],au['bucket_comparisons'],au['roi_comparisons'],au['spike_comparisons'])==(1028608, 55702, 75640, 9624)
    assert (au['integration_jobs'],au['integration_samples'],au['integration_buckets'],au['integration_roi'])==(3, 49152, 1300, 3584)
    for h in r['traces']:assert sha(sim/f"seed_{r['seed']}/traces"/h['file']).upper()==h['sha256'].upper()
    log=(sim/f"seed_{r['seed']}.multires.console.log").read_text(encoding='utf-8-sig')
    assert len(re.findall('^MULTIRES_CASE_PASS ',log,re.M))==80 and len(re.findall('^MULTIRES_CONTROL_POINT_PASS ',log,re.M))==14
first=sm['results'][0]
for td in (sim/f"seed_{first['seed']}_replay/traces",sim/'project/traces'):
    for h in first['traces']:assert sha(td/h['file']).upper()==h['sha256'].upper()
synthesis_resources=sy['resources'] if isinstance(sy['resources'],list) else [sy['resources']]
assert len(synthesis_resources)==1
resources=synthesis_resources[0];assert resources['latches']==resources['dsp']==resources['ram']==0 and resources['index_bits']==18
upstream={}
for step,path in ((9,'FPGA/reports/uart/20261022_010136_ca06e863'),):
    m=read(root/path/'manifest.json');assert m['verdict']=='PASS';count=0
    for h in m['source_sha256']:
        p=Path(h['Path'])
        if p.suffix.lower() in ('.sv','.v'):
            assert sha(p).upper()==h['Hash'].upper(),str(p);count+=1
    upstream[str(step)]=dict(report=path,unchanged_tested_hdl_files=count)
files=set()
for folder in ('FPGA/rtl','FPGA/sim/models','FPGA/sim/tb','FPGA/scripts','FPGA/ip','PC/protocol','PC/tests','docs/verification'):
    for p in (root/folder).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in {'.sv','.v','.vh','.py','.ps1','.tcl','.json','.f','.md','.xci','.xdc','.txt','.xml'}:files.add(p)
files.add(root/'FPGA/project/scope_smoke/scope_smoke.xpr')
for seed in sm['seeds']:
    for role in ('vectors','expected'):files.update(p for p in (root/f"FPGA/sim/{role}/multires/{sim.name}/seed_{seed}").rglob('*') if p.is_file())
hashes=[dict(file=p.relative_to(root).as_posix(),sha256=sha(p)) for p in sorted(files)]
write(sim/'acceptance_source_sha256.json',hashes)
with zipfile.ZipFile(sim/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
    for h in hashes:z.write(root/h['file'],h['file'])
with zipfile.ZipFile(sim/'source_snapshot.zip') as z:
    assert len(z.namelist())==len(hashes)
    for h in hashes:assert hashlib.sha256(z.read(h['file'])).hexdigest()==h['sha256']==sha(root/h['file'])
summary=dict(verdict='PASS',step=10,final_acceptance_complete=True,completed_at=datetime.now().astimezone().isoformat(),simulator=sm['backend'],seeds=sm['seeds'],
 core_cases=sum(r['audit']['cases'] for r in sm['results']),
 input_sample_comparisons=sum(r['audit']['sample_comparisons']+r['audit']['integration_samples'] for r in sm['results']),
 bucket_comparisons=sum(r['audit']['bucket_comparisons']+r['audit']['integration_buckets'] for r in sm['results']),
 roi_comparisons=sum(r['audit']['roi_comparisons']+r['audit']['integration_roi'] for r in sm['results']),
 spike_comparisons=sum(r['audit']['spike_comparisons'] for r in sm['results']),integration_jobs=sum(r['audit']['integration_jobs'] for r in sm['results']),
 bucket_rule='[floor(i*N/B),floor((i+1)*N/B)-1], B=min(N,requested)',short_frames='reduce effective bucket count',
 roi_rule='min(max(trigger-floor(R/2),0),N-R), R=min(N,requested_roi)',
 invalid_configs_per_seed=8,cancel_phases_per_seed=7,reset_phases_per_seed=7,expected_negative_tests=sm['negative_tests'],unexpected_errors=0,
 replay=sm['replay'],native_project=sm['project'],synthesis_resources=synthesis_resources,unchanged_upstream=upstream,
 simulation_report=sim.relative_to(root).as_posix(),synthesis_report=synth.relative_to(root).as_posix(),documentation='docs/verification/step10_multires_envelope.md',
 source_files=len(hashes),source_snapshot='source_snapshot.zip',snapshot_sha256=sha(sim/'source_snapshot.zip'),sources_and_archive_hashes_verified=True,
 exclusions=['final board-level top and bus arbitration','UART envelope/ROI packet integration','place-and-route/timing signoff and final pins'])
console=(sim/'project/console.log').read_text(encoding='utf-8-sig',errors='replace');summary['retained_native_environment_advisories']={}
for message_id in re.findall(r'^WARNING: \[([^\]]+)\]',console,re.M):
    summary['retained_native_environment_advisories'][message_id]=summary['retained_native_environment_advisories'].get(message_id,0)+1
write(sim/'acceptance.json',summary);print('STEP10_ACCEPTANCE_PASS',json.dumps({k:summary[k] for k in ('input_sample_comparisons','bucket_comparisons','roi_comparisons','spike_comparisons','source_files')}))
