"""Freeze checked Step 7 evidence and a verified, self-contained source snapshot."""
import argparse,hashlib,json,re,zipfile
from datetime import datetime
from pathlib import Path

def read_json(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_json(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def finalize(root,sim,synth,capture,package):
    root=root.resolve();sim=sim.resolve();synth=synth.resolve();capture=capture.resolve();package=package.resolve()
    sm=read_json(sim/'manifest.json');sy=read_json(synth/'manifest.json')
    cm=read_json(capture/'manifest.json');pm=read_json(package/'manifest.json')
    assert all(m['verdict']=='PASS' for m in (sm,sy,cm,pm)), 'An evidence gate did not pass'
    assert len(sm['seeds'])>=2 and len(sm['seeds'])==len(set(sm['seeds']))
    assert sm['replay']['verdict']=='PASS' and sm['project']['verdict']=='PASS' and sm['project']['clean_rebuild']
    assert sm['project']['top']=='tb_measure' and sm['replay']['identical_traces']==sm['project']['identical_traces']==9
    # A prior PASS is applicable only to exactly the functional/source bytes tested.
    for manifest in (sm,cm,pm):
        for h in manifest['source_sha256']:
            assert digest(Path(h['Path'])).upper()==h['Hash'].upper(),f"Source changed: {h['Path']}"
    for h in sy['source_sha256']:assert digest(root/'FPGA'/h['file']).upper()==h['sha256'].upper()
    for name in ('xvlog.log','elaborate.log','simulate.log'):
        log=(sim/'project'/name).read_text(encoding='utf-8-sig',errors='replace')
        assert not re.search(r'^\s*(WARNING:|CRITICAL WARNING:|ERROR:|Fatal:|TEST_FAIL)',log,re.M)
    transcript=(sim/'project/simulate.log').read_text(encoding='utf-8-sig',errors='replace')
    assert len(re.findall(r'^FEATURE_PASS ',transcript,re.M))==7
    assert len(re.findall(r'^MEASURE_RESET_PASS ',transcript,re.M))==13
    assert 'MEASURE_CAPTURE_CONFIG_PASS invalid_arms=4 errors=0' in transcript
    audits=[]
    for result in sm['results']:
        seed=result['seed'];td=sim/f'seed_{seed}/traces';audit=read_json(sim/f'seed_{seed}/trace_audit.json')
        assert audit['verdict']=='PASS' and audit['seed']==seed
        assert audit['trigger_cases']==result['trigger_cases'] and audit['measurement_cases']==result['measurement_cases']
        assert audit['integration_frames']==9 and audit['integration_points']==9*16384
        assert {h['file'] for h in result['trace_sha256']}=={p.name for p in td.glob('*.csv')}
        for h in result['trace_sha256']:assert digest(td/h['file']).upper()==h['hash'].upper()
        audits.append(audit)
    first=sm['results'][0]
    for other in (sim/f"seed_{first['seed']}_replay/traces",sim/'project/traces'):
        assert {p.name for p in other.glob('*.csv')}=={h['file'] for h in first['trace_sha256']}
        for h in first['trace_sha256']:assert digest(other/h['file']).upper()==h['hash'].upper()
    resources=sy['resources'];assert {r['top'] for r in resources}=={'measurement_core','trigger_core','bram_capture'}
    assert all(r['latches']==0 for r in resources)
    c=next(r for r in resources if r['top']=='bram_capture')
    assert 2*c['bram36']+c['bram18']==13 and c['lutram']==0
    files=set()
    for folder in ('FPGA/rtl','FPGA/sim/models','FPGA/sim/tb','FPGA/scripts','FPGA/ip','docs/verification'):
        for p in (root/folder).rglob('*'):
            if p.is_file() and p.suffix.lower() in {'.sv','.v','.vh','.py','.ps1','.tcl','.json','.f','.md','.xci','.xdc','.txt','.xml'}:
                files.add(p)
    files.add(root/'FPGA/project/scope_smoke/scope_smoke.xpr')
    for record in sm['data_paths']:
        for key in ('original_vectors','original_expected'):
            files.update(p for p in Path(record['paths'][key]).rglob('*') if p.is_file())
    hashes=[dict(file=p.relative_to(root).as_posix(),sha256=digest(p)) for p in sorted(files)]
    write_json(sim/'acceptance_source_sha256.json',hashes)
    with zipfile.ZipFile(sim/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
        for h in hashes:z.write(root/h['file'],h['file'])
    with zipfile.ZipFile(sim/'source_snapshot.zip') as z:
        assert len(z.namelist())==len(hashes)
        for h in hashes:
            assert hashlib.sha256(z.read(h['file'])).hexdigest()==h['sha256']==digest(root/h['file'])
    summary=dict(verdict='PASS',step=7,final_acceptance_complete=True,completed_at=datetime.now().astimezone().isoformat(),
      simulator=sm['backend'],seeds=sm['seeds'],trigger_types=9,independent_feature_stages=7,
      trigger_cases=sum(a['trigger_cases'] for a in audits),trigger_sample_comparisons=sum(a['trigger_samples'] for a in audits),
      standalone_measurement_frames=sum(a['measurement_cases'] for a in audits),
      integrated_bram_measurement_frames=sum(a['integration_frames'] for a in audits),
      integrated_point_comparisons=sum(a['integration_points'] for a in audits),
      audited_field_checks=sum(a['field_checks'] for a in audits),integer_oracle_error_lsb=0,
      accumulator_bits=dict(signed_sum=64,unsigned_square_sum=64),no_complete_period=dict(measurement_valid=0,frequency_hz=0,period_q16=0,duty_ppm=0),
      reset_state_operation_points_per_seed=13,invalid_measure_configs_per_seed=3,invalid_extended_arm_configs_per_seed=4,
      replay=sm['replay'],native_project=sm['project'],synthesis_resources=resources,
      synthesis_advisories=sy['retained_floorplanning_advisories'],
      simulation_report=sim.relative_to(root).as_posix(),synthesis_report=synth.relative_to(root).as_posix(),
      capture_compatibility_report=capture.relative_to(root).as_posix(),package_report=package.relative_to(root).as_posix(),
      source_snapshot='source_snapshot.zip',source_files=len(hashes),snapshot_sha256=digest(sim/'source_snapshot.zip'),
      sources_and_archive_hashes_verified=True,
      documentation='docs/verification/step7_trigger_measure.md',
      exclusions=['final board-level integration','place and route/timing signoff','physical ADC/DAC and final pin validation'])
    write_json(sim/'acceptance.json',summary)
    print('STEP7_ACCEPTANCE_PASS',json.dumps({k:summary[k] for k in ('trigger_cases','standalone_measurement_frames','integrated_point_comparisons','source_files')}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    for name in ('simulation-report','synthesis-report','capture-report','package-report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();finalize(a.root,a.simulation_report,a.synthesis_report,a.capture_report,a.package_report)
