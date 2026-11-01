"""Recover evidence after the report-only PowerShell integer-key serializer error.

Does not simulate, change RTL, waive a failing test, or discard any diagnostics.
Checks all completed runs, staged source bytes, original vectors and trace hashes.
"""
import argparse,hashlib,json,re,subprocess
from datetime import datetime
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def text(p):return p.read_text(encoding='utf-8-sig',errors='replace')
def read(p):return json.loads(text(p))
def check_log(p,native=False):
    for line in text(p).splitlines():
        assert not re.match(r'^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|FATAL_ERROR:)',line),(p,line)
        if re.match(r'^\s*WARNING:',line):
            mid=re.search(r'\[([^\]]+)\]',line).group(1)
            if mid=='VRFC 10-9145':assert 'xfft_v9_1_15' in line and 'scope_fft_1024.vhd:201' in line
            else:assert native and mid in {'Board 49-26','Project 1-5713','Vivado 12-13650','Wavedata 42-489','Simtcl 6-168','Add_Wave-1'},(p,line)
ap=argparse.ArgumentParser();ap.add_argument('--report',type=Path,required=True);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--python',required=True);a=ap.parse_args()
root=Path(__file__).resolve().parents[2];fpga=root/'FPGA';report=a.report.resolve();build=a.build.resolve();scripts=fpga/'scripts'
runner=scripts/'run_spectrum_tb.ps1';old=report/'runner_at_execution.ps1'
before=text(old);after=text(runner)
assert before.count('stages=$stages;')==1
replacement='stages=@(foreach($seed in $Seeds){[pscustomobject]@{seed=$seed;paths=$stages[$seed]}});'
assert before.replace('stages=$stages;',replacement)==after,'Only serialization may change'
relative=re.findall(r"'((?:rtl|sim)/[^']+\.sv)'",before)
assert len(relative)==24
inputs=[fpga/p for p in relative]
for p in inputs:assert sha(p)==sha(build/p.name),p
inputs += [scripts/p for p in ('run_spectrum_tb.ps1','generate_spectrum_vectors.py','generate_fft_tables.py','audit_spectrum_traces.py','ensure_scope_fft_ip.tcl','prepare_fft_development.tcl','check_spectrum_project.tcl','create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json')]
inputs += [root/'PC/protocol/spectrum_reference.py',root/'PC/tests/test_spectrum_reference.py']
started=datetime.strptime(report.name[:15],'%Y%m%d_%H%M%S').astimezone().timestamp()
for p in inputs:
    if p!=runner:assert p.stat().st_mtime<=started+2,('Source edited after launch',p)
assert 'Ran 5 tests' in text(report/'pc_tests.log') and re.search('^OK$',text(report/'pc_tests.log'),re.M)
for p in report.glob('*.console.log'):
    if p.name.startswith('fault_') and '.elaborate.' not in p.name:continue
    check_log(p,p.name in ('project.console.log','prepare.console.log'))
assert 'FFT_PREPARE_PASS' in text(report/'prepare.console.log')
traces=['fft_raw.csv','spectrum_bins.csv','spectrum_results.csv','spectrum_capture_bins.csv','spectrum_capture_results.csv','spectrum_capture_roi.csv']
tops=['tb_fft_wrapper','tb_spectrum','tb_spectrum_capture','tb_spectrum_control','tb_spectrum_isqrt']
def trace_hashes(directory):return [dict(file=n,sha256=sha(directory/n)) for n in sorted(traces)]
def pass_pattern(top,seed):
    return {
      'tb_fft_wrapper':f'^TEST_PASS tb_fft_wrapper seed={seed} cases=5 bins=5120 errors=0',
      'tb_spectrum':f'^TEST_PASS tb_spectrum seed={seed} cases=42 bins=43008 errors=0',
      'tb_spectrum_capture':f'^TEST_PASS tb_spectrum_capture seed={seed} jobs=2 errors=0',
      'tb_spectrum_control':'^TEST_PASS tb_spectrum_control controls=14 recoveries=14 invalid=2 errors=0',
      'tb_spectrum_isqrt':'^TEST_PASS tb_spectrum_isqrt cases=291 errors=0'}[top]
seeds=[20261020,42];results=[];stages=[]
for seed in seeds:
    for role in ('vectors','expected'):
        original=fpga/f'sim/{role}/spectrum/{report.name}/seed_{seed}';stage=build/f'seed_{seed}/{role}'
        for p in original.iterdir():assert sha(p)==sha(stage/p.name),(role,p)
    stages.append(dict(seed=seed,paths=dict(vectors=str(build/f'seed_{seed}/vectors'),expected=str(build/f'seed_{seed}/expected'),original_vectors=str(fpga/f'sim/vectors/spectrum/{report.name}/seed_{seed}'),original_expected=str(fpga/f'sim/expected/spectrum/{report.name}/seed_{seed}'))))
for label,seed in [('seed_20261020',20261020),('seed_42',42),('seed_20261020_replay',20261020),('project',20261020)]:
    for top in tops:
        p=report/(f'project/{top}.simulate.log' if label=='project' else f'{label}.{top}.console.log')
        assert re.search(pass_pattern(top,seed),text(p),re.M),(label,top)
    td=report/label/'traces';out=report/label/'audit.json';previous=read(out)
    run=subprocess.run([a.python,str(scripts/'audit_spectrum_traces.py'),'--expected',str(build/f'seed_{seed}/expected'),'--traces',str(td),'--output',str(out)],capture_output=True,text=True,encoding='utf8')
    assert run.returncode==0 and 'SPECTRUM_TRACE_AUDIT_PASS' in run.stdout,(label,run.stdout,run.stderr)
    assert read(out)==previous,('Recovered audit changed',label)
    if label in ('seed_20261020','seed_42'):results.append(dict(seed=seed,verdict='PASS',audit=previous,traces=trace_hashes(td)))
    else:assert trace_hashes(td)==results[0]['traces'],label
for top in tops:
    for suffix in ('xvlog','elaborate','simulate'):check_log(report/f'project/{top}.{suffix}.log',True)
assert 'SPECTRUM_PROJECT_PASS tops=5 errors=0' in text(report/'project.console.log')
assert 'Deleted exact generated directory' in text(report/'project/clean_rebuild.txt')
negatives=[]
for bad,sig in [(1,'FFT_INPUT_TLAST'),(2,'SPECTRUM_TIMESTAMP')]:
    log=text(report/f'fault_{bad}.console.log');assert f'Fatal: {sig}' in log and 'NEGATIVE_TEST_DID_NOT_FIRE' not in log and 'TEST_PASS' not in log
    negatives.append(dict(case=bad,verdict='PASS',expected_fatal=sig))
manifest=dict(verdict='PASS',seeds=seeds,results=results,replay=dict(verdict='PASS',seed=20261020,identical_traces=6),
 native=dict(verdict='PASS',tops=5,identical_traces=6,audit=read(report/'project/audit.json')),negative_assertions=negatives,
 source_sha256=[dict(Path=str(p.resolve()),Hash=sha(p)) for p in inputs],stages=stages,temporary_build=str(build),failure=None,
 evidence_recovery=dict(reason='PowerShell JSON serialization rejected integer Hashtable stage keys AFTER all tests and audits completed',
   original_runner='runner_at_execution.ps1',original_runner_sha256=sha(old),corrected_runner_sha256=sha(runner),
   only_change='Serialize stages as an array of seed/path objects',staged_hdl_files_checked=len(relative),all_test_logs_rechecked=True,all_four_csv_audits_repeated_identically=True,
   original_invocation=f'run_spectrum_tb.ps1 -PythonExe {a.python} -Project',no_rtl_or_vectors_modified=True),
 commands=[dict(console_log=p.name,running_lines=re.findall(r'^(?:Running:|# xsim).*$',text(p),re.M)) for p in sorted(report.glob('*.console.log'))])
(report/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('SPECTRUM_MANIFEST_RECOVERY_PASS seeds=2 replay=PASS native_tops=5 staged_hdl=24 errors=0')
