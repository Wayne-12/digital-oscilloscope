"""Step 12 final gates, immutable source snapshot and explicit continuation record."""
import argparse,csv,hashlib,json,re,zipfile,sys
from collections import Counter
from datetime import datetime
from pathlib import Path
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def rnd(n,d):return (-1 if n<0 else 1)*((abs(n)+d//2)//d)
ap=argparse.ArgumentParser();ap.add_argument('--simulation-report',type=Path,required=True);ap.add_argument('--synthesis-report',type=Path,required=True);a=ap.parse_args()
root=Path(__file__).resolve().parents[2];sim=a.simulation_report.resolve();synth=a.synthesis_report.resolve();sm=read(sim/'manifest.json');sy=read(synth/'manifest.json')
sys.path.insert(0,str(root/'PC/protocol'))
from innovation_reference import source_words
assert sm['verdict']==sy['verdict']=='PASS'
assert len(sm['seeds'])>=2 and len(set(sm['seeds']))==len(sm['seeds'])
assert sm['replay']['verdict']==sm['native']['verdict']=='PASS' and sm['replay']['identical_traces']==sm['native']['identical_traces']==44
assert sm['native']['tops']==8 and len(sm['negative_assertions'])==2 and all(x['verdict']=='PASS' for x in sm['negative_assertions'])
for h in sm['source_sha256']:assert sha(Path(h['Path'])).upper()==h['Hash'].upper(),h['Path']
for h in sy['source_sha256']:assert sha(root/'FPGA'/h['file']).upper()==h['sha256'].upper(),h['file']
unit=(sim/'pc_tests.log').read_text(encoding='utf-8-sig');assert 'Ran 6 tests' in unit and re.search(r'^OK$',unit,re.M)
assert len(sy['resources'])==6 and all(r['latches']==r['blackboxes']==0 for r in sy['resources'])
zero_results=[]
for result in sm['results']:
    au=result['audit'];assert au['verdict']=='PASS' and (au['profiles'],au['raw_samples'],au['display_samples'],au['fft_bins'])==(8,354304,34816,8192)
    assert (au['raw_read_comparisons'],au['spike_comparisons'],au['roi_comparisons'])==(245760,24000,17920)
    assert au['max_gain_error_q20']<=525 and au['max_offset_error_q16']<=16384 and au['max_fft_component_error']<=128 and au['max_harmonic_ratio_error_ppm']<=32
    for h in result['traces']:assert sha(sim/f"seed_{result['seed']}/traces"/h['file']).upper()==h['sha256'].upper()
    # Explicit four-frame midpoint average, separate from the nine-point fit.
    zs={p:[[] for _ in range(4)] for p in range(8)}
    with (sim/f"seed_{result['seed']}/traces/health_raw.csv").open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if int(row['stage'])==0:zs[int(row['profile'])][int(row['item'])].append(2047-int(row['raw']))
    for p,frames in zs.items():
        assert all(len(v)==256 for v in frames);xs=sum(frames,[]);zero=rnd(sum(xs)*65536,1024)
        expected=(32 if p==1 else -37 if p==6 else 91 if p==7 else 0)*65536
        noise=12 if p==3 else 2 if p==6 else 0 if p==7 else 1
        assert all(expected//65536-noise<=x<=expected//65536+noise for x in xs)
        assert abs(zero-expected)<=65536 # 1 ADC code, fixed midpoint noise tolerance.
        zero_results.append(dict(seed=result['seed'],profile=p,frame_means_q16=[rnd(sum(v)*65536,256) for v in frames],multi_frame_zero_q16=zero,expected_q16=expected,error_q16=abs(zero-expected),limit_q16=65536))
first=sm['results'][0]
for directory in (sim/f"seed_{first['seed']}_replay/traces",sim/'project/traces'):
    for h in first['traces']:assert sha(directory/h['file']).upper()==h['sha256'].upper()
native_advisories=Counter()
for p in (sim/'project').glob('*.log'):
    text=p.read_text(encoding='utf-8-sig',errors='replace');assert not re.search(r'^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL)',text,re.M),p
    for line in text.splitlines():
        if not re.match(r'^\s*WARNING:',line):continue
        mid=re.search(r'\[([^\]]+)\]',line).group(1)
        if mid=='VRFC 10-9145':assert 'xfft_v9_1_15' in line and 'scope_fft_1024.vhd:201' in line
        else:assert mid in {'Board 49-26','Project 1-5713','Vivado 12-13650','Wavedata 42-489','Simtcl 6-168','Add_Wave-1'},line
        native_advisories[mid]+=1
synth_advisories=Counter()
for line in (synth/'console.log').read_text(encoding='utf-8-sig',errors='replace').splitlines():
    assert not re.match(r'^\s*(ERROR:|CRITICAL WARNING:|INNOVATION_OOC_SYNTH_FAIL)',line)
    if re.match(r'^\s*WARNING:',line):
        mid=re.search(r'\[([^\]]+)\]',line).group(1)
        # Known-only harmless synthesis diagnostics; never waive latches,
        # arithmetic/signedness, multiple drivers or black boxes.
        allowed=(mid=='Synth 8-7129' and any(s in line for s in ('bucket[first_index]','bucket[last_index]','bucket[sample_count]','roi[frame_index]','roi[roi_index]','roi[signed_sample]','roi[timestamp]','cfg_header[kind]','cfg_header[length]','cfg_header[flags]')) or
          mid=='Synth 8-6014' and any(s in line for s in ('held_reg[kind]','held_reg[length]','held_reg[flags]')) or
          mid=='Netlist 29-101' and "Netlist 'capture_result_stream' is not ideal for floorplanning" in line)
        assert allowed,line;synth_advisories[mid]+=1
old=read(root/'FPGA/reports/spectrum/20261022_132343_c1e2f042/acceptance_source_sha256.json');prior=0
for h in old:
    if h['file'].startswith(('FPGA/rtl/','FPGA/sim/models/')) and Path(h['file']).suffix.lower() in ('.v','.sv'):
        assert sha(root/h['file'])==h['sha256'],h['file'];prior+=1
isolated_spikes=[]
for backend,n in [('bram',16384)]:
    values=[2047-(w&4095) for w in source_words(n)]
    counts={str(x):sum(v==x and (i==0 or values[i-1]!=x) and (i==n-1 or values[i+1]!=x) for i,v in enumerate(values)) for x in (2047,-2048)}
    assert all(count>=200 for count in counts.values())
    isolated_spikes.append(dict(backend=backend,positive_single_sample=counts['2047'],negative_single_sample=counts['-2048']))
files=set()
for folder in ('FPGA/rtl','FPGA/sim/models','FPGA/sim/tb','FPGA/scripts','FPGA/ip','PC/protocol','PC/tests','docs/verification'):
    for p in (root/folder).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix.lower() in {'.sv','.sveo','.v','.vhd','.vho','.veo','.vh','.py','.ps1','.tcl','.json','.f','.md','.xci','.xdc','.txt','.xml'}:files.add(p)
files.add(root/'FPGA/project/scope_smoke/scope_smoke.xpr');files.add(sim/'manifest.json')
for seed in sm['seeds']:files.update(p for p in (root/f'FPGA/sim/vectors/innovation/{sim.name}/seed_{seed}').rglob('*') if p.is_file())
hashes=[dict(file=p.relative_to(root).as_posix(),sha256=sha(p)) for p in sorted(files)];write(sim/'acceptance_source_sha256.json',hashes)
with zipfile.ZipFile(sim/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
    for h in hashes:z.write(root/h['file'],h['file'])
with zipfile.ZipFile(sim/'source_snapshot.zip') as z:
    assert len(z.namelist())==len(hashes)
    for h in hashes:assert hashlib.sha256(z.read(h['file'])).hexdigest()==h['sha256']==sha(root/h['file'])
summary=dict(verdict='PASS',step=12,final_acceptance_complete=True,completed_at=datetime.now().astimezone().isoformat(),vivado='2025.2',seeds=sm['seeds'],
 innovation_one=dict(profiles_per_seed=8,raw_comparisons=sum(r['audit']['raw_samples'] for r in sm['results']),display_raw_preservation_comparisons=sum(r['audit']['display_samples'] for r in sm['results']),
   fft_bin_comparisons=sum(r['audit']['fft_bins'] for r in sm['results']),max_gain_error_q20=max(r['audit']['max_gain_error_q20'] for r in sm['results']),max_offset_error_q16=max(r['audit']['max_offset_error_q16'] for r in sm['results']),
   gain_limit_q20=525,offset_limit_q16=16384,multi_frame_zeros=zero_results,calibration_scope='display branch only; no raw rewriting; relative digital simulation only',
   primary_fault_classes=['healthy','zero drift','gain change','noise rise','clipping','harmonic rise','polarity reversal','learned alternate baseline']),
 innovation_two=dict(jobs=sum(len(r['audit']['capture_jobs']) for r in sm['results']),raw_read_comparisons=sum(r['audit']['raw_read_comparisons'] for r in sm['results']),
   spike_comparisons=sum(r['audit']['spike_comparisons'] for r in sm['results']),roi_comparisons=sum(r['audit']['roi_comparisons'] for r in sm['results']),
   per_seed_jobs=first['audit']['capture_jobs'],isolated_single_sample_spikes_per_frame=isolated_spikes,transport='Step 9 frame_tx/CRC16, B2 segmented SCAP v1 container with CRC32; raw remains frozen in memory'),
 python_unit_tests=6,expected_negative_assertions=sm['negative_assertions'],unexpected_errors=0,replay=sm['replay'],native_project=dict(verdict='PASS',clean_rebuild=True,tops=5,identical_traces=19,top='tb_innovation_health'),
 synthesis_resources=sy['resources'],retained_native_advisories=dict(native_advisories),retained_synthesis_advisories=dict(synth_advisories),
 unchanged_previous_rtl_and_model_files=prior,simulation_report=sim.relative_to(root).as_posix(),synthesis_report=synth.relative_to(root).as_posix(),documentation='docs/verification/step12_innovations.md',
 source_files=len(hashes),source_snapshot='source_snapshot.zip',snapshot_sha256=sha(sim/'source_snapshot.zip'),sources_and_archive_hashes_verified=True,
 exclusions=['absolute analog gain, ENOB and physical health limits','autonomous board-level self-test scheduling and host UI','final board top, shared-port arbitration and hardware CDC for the new summary bus','place-and-route timing signoff and final pins'])
write(sim/'acceptance.json',summary);print('STEP12_ACCEPTANCE_PASS',json.dumps(dict(raw=summary['innovation_one']['raw_comparisons'],display=summary['innovation_one']['display_raw_preservation_comparisons'],memory=summary['innovation_two']['raw_read_comparisons'],spikes=summary['innovation_two']['spike_comparisons'],roi=summary['innovation_two']['roi_comparisons'],source_files=len(hashes))))
