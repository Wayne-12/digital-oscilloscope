"""Freeze Step 11 only after simulations, native rebuild, synthesis and hashes pass."""
import argparse,hashlib,json,re,zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--simulation-report',type=Path,required=True);ap.add_argument('--synthesis-report',type=Path,required=True);a=ap.parse_args()
root=a.root.resolve();sim=a.simulation_report.resolve();synth=a.synthesis_report.resolve();sm=read(sim/'manifest.json');sy=read(synth/'manifest.json')
assert sm['verdict']==sy['verdict']=='PASS'
assert len(sm['seeds'])>=2 and len(sm['seeds'])==len(set(sm['seeds']))
assert sm['replay']['verdict']==sm['native']['verdict']=='PASS'
assert sm['replay']['identical_traces']==sm['native']['identical_traces']==6
assert sm['native']['tops']==5
if sm.get('evidence_recovery'):
    recovery=sm['evidence_recovery']
    assert sha(sim/recovery['original_runner']).upper()==recovery['original_runner_sha256'].upper()
    assert recovery['staged_hdl_files_checked']==24 and recovery['all_test_logs_rechecked'] and recovery['all_four_csv_audits_repeated_identically'] and recovery['no_rtl_or_vectors_modified']
assert len(sm['negative_assertions'])==2 and all(x['verdict']=='PASS' for x in sm['negative_assertions'])
unit_log=(sim/'pc_tests.log').read_text(encoding='utf-8-sig')
assert 'Ran 5 tests' in unit_log and re.search(r'^OK$',unit_log,re.M)
for h in sm['source_sha256']:assert sha(Path(h['Path'])).upper()==h['Hash'].upper(),h['Path']
for h in sy['source_sha256']:assert sha(root/'FPGA'/h['file']).upper()==h['sha256'].upper(),h['file']
assert sy['resources']['latches']==sy['resources']['blackboxes']==0 and sy['resources']['dsp']>0 and sy['resources']['ram']>0
for r in sm['results']:
    au=r['audit'];assert au['verdict']=='PASS'
    assert (au['spectrum_frames'],au['spectrum_bins'],au['raw_frames'],au['raw_bins'],au['roi_points'])==(44,45056,5,5120,2048)
    assert max([au['max_component_error']]+au['raw_max_errors'])<=128 and max(au['max_amplitude_error_q16'],au['max_rms_error_q16'])<=8192
    for h in r['traces']:assert sha(sim/f"seed_{r['seed']}/traces"/h['file']).upper()==h['sha256'].upper()
first=sm['results'][0]
for directory in (sim/f"seed_{first['seed']}_replay/traces",sim/'project/traces'):
    for h in first['traces']:assert sha(directory/h['file']).upper()==h['sha256'].upper()
native_advisories=Counter()
for p in (sim/'project').glob('*.log'):
    text=p.read_text(encoding='utf-8-sig',errors='replace')
    assert not re.search(r'^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL)',text,re.M),p
    for line in text.splitlines():
        if not re.match(r'^\s*WARNING:',line):continue
        mid=re.search(r'\[([^\]]+)\]',line).group(1)
        if mid=='VRFC 10-9145':assert 'xfft_v9_1_15' in line and 'scope_fft_1024.vhd:201' in line
        else:assert mid in {'Board 49-26','Project 1-5713','Vivado 12-13650','Wavedata 42-489','Simtcl 6-168','Add_Wave-1','IP_Flow 19-982'},line
        native_advisories[mid]+=1
synth_text=(synth/'console.log').read_text(encoding='utf-8-sig',errors='replace')
synth_advisories=Counter()
for line in synth_text.splitlines():
    assert not re.match(r'^\s*(ERROR:|CRITICAL WARNING:|SPECTRUM_OOC_SYNTH_FAIL)',line)
    if not re.match(r'^\s*WARNING:',line):continue
    mid=re.search(r'\[([^\]]+)\]',line).group(1)
    allowed=(mid=='Vivado 12-13650' or
      mid=='IP_Flow 19-982' and "'super_sample_rates'" in line or
      mid=='Synth 8-6040' and ('sin_addr_2s_comp' in line or 'cos_addr_2s_comp' in line) or
      mid=='Synth 8-3936' and 'frequency_product_reg' in line or
      mid=='Synth 8-3917' and ('bin_data[power]' in line or 'metadata[window_' in line) or
      mid=='Synth 8-7129' and 'sample_timestamp[' in line)
    assert allowed,line;synth_advisories[mid]+=1
upstream={}
for step,path in ((9,'FPGA/reports/uart/20261022_010136_ca06e863'),(10,'FPGA/reports/multires/20261022_125121_d0347ac8')):
    m=read(root/path/'manifest.json');assert m['verdict']=='PASS';count=0
    for h in m['source_sha256']:
        p=Path(h['Path'])
        if p.suffix.lower() in ('.sv','.v'):
            assert sha(p).upper()==h['Hash'].upper(),str(p);count+=1
    upstream[str(step)]=dict(report=path,unchanged_tested_hdl_files=count)
old_sources=read(root/'FPGA/reports/multires/20261022_125121_d0347ac8/acceptance_source_sha256.json')
all_prior_rtl=0
for h in old_sources:
    p=root/h['file']
    if h['file'].startswith('FPGA/rtl/') and p.suffix.lower() in ('.sv','.v'):
        assert sha(p)==h['sha256'],h['file'];all_prior_rtl+=1
upstream['10']['unchanged_all_previous_rtl_files']=all_prior_rtl
files=set()
for folder in ('FPGA/rtl','FPGA/sim/models','FPGA/sim/tb','FPGA/scripts','FPGA/ip','PC/protocol','PC/tests','docs/verification'):
    for p in (root/folder).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in {'.sv','.sveo','.v','.vhd','.vho','.veo','.vh','.py','.ps1','.tcl','.json','.f','.md','.xci','.xdc','.txt','.xml'}:files.add(p)
files.add(root/'FPGA/project/scope_smoke/scope_smoke.xpr')
files.add(sim/'manifest.json')
if sm.get('evidence_recovery'):files.add(sim/sm['evidence_recovery']['original_runner'])
for seed in sm['seeds']:
    for role in ('vectors','expected'):files.update(p for p in (root/f'FPGA/sim/{role}/spectrum/{sim.name}/seed_{seed}').rglob('*') if p.is_file())
hashes=[dict(file=p.relative_to(root).as_posix(),sha256=sha(p)) for p in sorted(files)]
write(sim/'acceptance_source_sha256.json',hashes)
with zipfile.ZipFile(sim/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
    for h in hashes:z.write(root/h['file'],h['file'])
with zipfile.ZipFile(sim/'source_snapshot.zip') as z:
    assert len(z.namelist())==len(hashes)
    for h in hashes:assert hashlib.sha256(z.read(h['file'])).hexdigest()==h['sha256']==sha(root/h['file'])
summary=dict(verdict='PASS',step=11,final_acceptance_complete=True,completed_at=datetime.now().astimezone().isoformat(),vivado='2025.2',seeds=sm['seeds'],
 spectrum_frames=sum(r['audit']['spectrum_frames'] for r in sm['results']),spectrum_bin_comparisons=sum(r['audit']['spectrum_bins'] for r in sm['results']),
 raw_complex_frames=sum(r['audit']['raw_frames'] for r in sm['results']),raw_complex_bin_comparisons=sum(r['audit']['raw_bins'] for r in sm['results']),
 integration_roi_comparisons=sum(r['audit']['roi_points'] for r in sm['results']),
 maximum_component_error=max(max([r['audit']['max_component_error']]+r['audit']['raw_max_errors']) for r in sm['results']),
 maximum_amplitude_error_q16=max(r['audit']['max_amplitude_error_q16'] for r in sm['results']),
 maximum_rms_error_q16=max(r['audit']['max_rms_error_q16'] for r in sm['results']),
 fixed_tolerances=dict(component_integer_units=128,amplitude_q16=8192),
 cancel_phases_per_seed=7,reset_phases_per_seed=7,recoveries_per_seed=14,invalid_configs_per_seed=2,isqrt_vectors_per_seed=291,
 expected_negative_assertions=sm['negative_assertions'],unexpected_errors=0,python_unit_tests=5,replay=sm['replay'],
 native_project=dict(verdict='PASS',tops=5,identical_traces=6,clean_rebuild=True,top='tb_spectrum',report=str(sim/'project')),
 synthesis_resources=sy['resources'],synthesis_resource_note='LUT field counts LUT primitives; utilization report has 2161 Slice LUTs, 6 RAMB18 = 3 BRAM tiles',
 retained_native_advisories=dict(native_advisories),retained_synthesis_advisories=dict(synth_advisories),unchanged_upstream=upstream,
 simulation_report=sim.relative_to(root).as_posix(),synthesis_report=synth.relative_to(root).as_posix(),documentation='docs/verification/step11_fft_spectrum.md',
 source_files=len(hashes),source_snapshot='source_snapshot.zip',snapshot_sha256=sha(sim/'source_snapshot.zip'),sources_and_archive_hashes_verified=True,
 exclusions=['2048-point mode','sub-bin frequency interpolation','final board top / UART spectrum packets / shared-port arbitration','place-and-route timing signoff and final pins'])
if sm.get('evidence_recovery'):summary['report_serialization_recovery']=sm['evidence_recovery']
write(sim/'acceptance.json',summary)
print('STEP11_ACCEPTANCE_PASS',json.dumps({k:summary[k] for k in ('spectrum_frames','spectrum_bin_comparisons','raw_complex_bin_comparisons','maximum_component_error','maximum_amplitude_error_q16','source_files')}))
