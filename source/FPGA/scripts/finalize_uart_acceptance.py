"""Freeze Step 9 only after all simulation, replay, native and synthesis gates."""
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
assert sm['bulk_bytes_per_seed']>=1048576 and sm['replay']['verdict']==sm['project']['verdict']=='PASS'
assert sm['project']['clean_rebuild'] and sm['project']['identical_traces']==sm['replay']['identical_traces']==2
for h in sm['source_sha256']:assert sha(Path(h['Path'])).upper()==h['Hash'].upper(),h['Path']
for h in sy['source_sha256']:assert sha(root/'FPGA'/h['file']).upper()==h['sha256'].upper(),h['file']
bad=r'^\s*(WARNING:|CRITICAL WARNING:|ERROR:|Fatal:|TEST_FAIL)'
for top in ('bits','bytes'):
    for log in ('xvlog','elaborate','simulate'):
        assert not re.search(bad,(sim/f'project/tb_uart_{top}.{log}.log').read_text(encoding='utf-8-sig',errors='replace'),re.M)
assert not re.search(bad,(synth/'console.log').read_text(encoding='utf-8-sig'),re.M)
for r in sm['results']:
    au=r['audit'];assert au['verdict']=='PASS' and au['oracle']['bulk_payload_bytes']>=1048576
    assert au['oracle']['errors']==dict(crc=3,length=1,version=1,timeout=1)
    assert au['oracle']['unknown_commands']==1 and au['oracle']['command_errors']==11
    assert au['wave_words_compared']==2113 and au['uart_bytes.hex']['frames']==1067
    for h in r['traces']:assert sha(sim/f"seed_{r['seed']}/traces"/h['file']).upper()==h['sha256'].upper()
    for kind in ('bits','bytes'):
        log=(sim/f"seed_{r['seed']}.{kind}.console.log").read_text(encoding='utf-8-sig')
        assert re.search(f'^TEST_PASS tb_uart_{kind} .*errors=0',log,re.M)
        if kind=='bits':assert 'timing_checks=960 sample_checks=776' in log
first=sm['results'][0]
for td in (sim/f"seed_{first['seed']}_replay/traces",sim/'project/traces'):
    for h in first['traces']:assert sha(td/h['file']).upper()==h['sha256'].upper()
assert {r['top'] for r in sy['resources']}=={'uart_transport','scope_uart_endpoint'} and all(r['latches']==0 for r in sy['resources'])
# Previous stages are reused only if their tested HDL bytes are still unchanged.
upstream={}
for step,path in ((7,'FPGA/reports/measure/20261021_233853_998a2694'),):
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
    for role in ('vectors','expected'):files.update(p for p in (root/f"FPGA/sim/{role}/uart/{sim.name}/seed_{seed}").rglob('*') if p.is_file())
hashes=[dict(file=p.relative_to(root).as_posix(),sha256=sha(p)) for p in sorted(files)]
write(sim/'acceptance_source_sha256.json',hashes)
with zipfile.ZipFile(sim/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
    for h in hashes:z.write(root/h['file'],h['file'])
with zipfile.ZipFile(sim/'source_snapshot.zip') as z:
    assert len(z.namelist())==len(hashes)
    for h in hashes:assert hashlib.sha256(z.read(h['file'])).hexdigest()==h['sha256']==sha(root/h['file'])
summary=dict(verdict='PASS',step=9,final_acceptance_complete=True,completed_at=datetime.now().astimezone().isoformat(),simulator=sm['backend'],seeds=sm['seeds'],
 bulk_payload_bytes=sum(r['audit']['oracle']['bulk_payload_bytes'] for r in sm['results']),
 encoded_output_bytes_compared=sum(r['audit']['uart_bytes.hex']['bytes'] for r in sm['results']),
 bit_level=dict(input_protocol_bytes_per_seed=88,output_protocol_bytes_per_seed=96,tx_timing_assertions_per_seed=960,rx_sample_assertions_per_seed=776,rx_overruns_per_seed=4,framing_errors_per_seed=1,false_starts_per_seed=1),
 expected_parser_errors_per_seed=dict(crc=3,length=1,version=1,timeout=1),unexpected_errors=0,
 wave_samples_compared=sum(r['audit']['wave_words_compared'] for r in sm['results']),crc='CRC-16/CCITT-FALSE',crc_known_vectors=3,
 replay=sm['replay'],native_project=sm['project'],synthesis_resources=sy['resources'],unchanged_upstream=upstream,
 simulation_report=sim.relative_to(root).as_posix(),synthesis_report=synth.relative_to(root).as_posix(),
 documentation='docs/verification/step9_uart_protocol.md',protocol_specification='PC/protocol/protocol_spec.md',source_files=len(hashes),source_snapshot='source_snapshot.zip',snapshot_sha256=sha(sim/'source_snapshot.zip'),sources_and_archive_hashes_verified=True,
 exclusions=['final scope_hw_top system integration and CDC control wrapper','physical UART board testing','place-and-route/timing signoff and final pins'])
console=(sim/'project/console.log').read_text(encoding='utf-8-sig',errors='replace')
summary['retained_native_environment_advisories']={}
for message_id in re.findall(r'^WARNING: \[([^\]]+)\]',console,re.M):
    summary['retained_native_environment_advisories'][message_id]=summary['retained_native_environment_advisories'].get(message_id,0)+1
write(sim/'acceptance.json',summary);print('STEP9_ACCEPTANCE_PASS',json.dumps({k:summary[k] for k in ('bulk_payload_bytes','encoded_output_bytes_compared','wave_samples_compared','source_files')}))
