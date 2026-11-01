"""Seal a passing saturation build for temporary hardware acceptance."""
from pathlib import Path
import argparse,hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main(require_iob=False,require_awg=False):
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('report',type=Path);cli.add_argument('--output',type=Path,required=True)
    a=cli.parse_args();report=a.report.resolve();m=json.loads((report/'manifest.json').read_text())
    assert m['verdict']=='PASS'
    for key in ('counter.simulate','dds.simulate','board.simulate','modes.simulate','implementation','saturation_simulation'):
        assert m[key]=='PASS',(key,m[key])
    if require_awg:assert m['awg.simulate']=='PASS' and m['capabilities']==63
    stage=Path(m['stage'])
    if not stage.exists() and stage.drive.upper()=='R:':
        stage=ROOT/'tmp/fpga_ascii'/stage.name
    for rel,digest in m['source_sha256'].items():assert sha(ROOT/rel)==digest,rel
    assert (stage/'scope_board_25m.xdc').read_bytes()==(ROOT/'FPGA/constraints/scope_board_25m.xdc').read_bytes()
    assert (stage/'build.tcl').read_bytes()==(ROOT/'FPGA/scripts/build_scope_board.tcl').read_bytes()
    if require_iob:
        assert m['adc_iob_registers_verified']==13
        lines=(stage/'artifacts/adc_iob_placement.tsv').read_text().splitlines()
        assert len(lines)==14
        import csv
        rows=list(csv.DictReader(lines,delimiter='\t'))
        assert all(row['site_type'].startswith('ILOGIC') and row['IOB'].lower() in ('1','true') for row in rows)
        data_indices={int(re.search(r'raw_iob_reg\[(\d+)\]',row['cell'])[1]) for row in rows if 'raw_iob_reg[' in row['cell']}
        assert data_indices==set(range(12)) and sum('otr_iob_reg' in row['cell'] for row in rows)==1
    timing=(stage/'artifacts/timing.rpt').read_text(encoding='utf-8')
    row=re.search(r'^\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)',timing,re.M)
    assert row and 'All user specified timing constraints are met.' in timing
    tests=(ROOT/('tmp/awg_pc_tests.log' if require_awg else 'tmp/saturation_pc_tests.log')).read_text(encoding='utf-8',errors='replace')
    match=re.search(r'Ran (\d+) tests',tests);assert match and tests.rstrip().endswith('OK')
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    bit=output/('scope_awg_25m.bit' if require_awg else 'scope_adc_iob_25m.bit' if require_iob else 'scope_saturation_25m.bit')
    if require_iob:
        assert 'FLASH_PREPARE_PASS' in (stage/'flash_prepare.log').read_text(encoding='utf-8',errors='replace')
        shutil.copyfile(stage/('flash/scope_awg_flash.bit' if require_awg else 'flash/scope_adc_iob_flash.bit'),bit)
        shutil.copytree(stage/'flash',output/'flash')
    else:
        shutil.copyfile(stage/'artifacts/scope_board_25m.bit',bit)
    shutil.copytree(stage/'artifacts',output/'implementation')
    shutil.copytree(report,output/'evidence/build')
    shutil.copytree(stage/'vectors',output/'evidence/frame_traces')
    shutil.copyfile(ROOT/('tmp/awg_pc_tests.log' if require_awg else 'tmp/saturation_pc_tests.log'),output/'evidence/pc_tests.log')
    sources=set(m['source_sha256'])
    for folder,glob in (('FPGA/scripts','*.py'),('FPGA/scripts','*.tcl'),('FPGA/scripts','*.json'),
            ('FPGA/sim/tb','*.sv'),('FPGA/sim/models','*.sv'),('PC/protocol','*.py'),('PC/ui','*.py'),('PC/tests','*.py')):
        sources.update(str(p.relative_to(ROOT)) for p in (ROOT/folder).glob(glob))
    sources.update(('示波器显示界面.py','PC/ui/requirements.txt','PC/protocol/protocol_spec.md','FPGA/constraints/scope_board_25m.xdc',
                    'docs/verification/实物测量清单_20261029.md'))
    copied={}
    for rel in sorted(sources):
        dest=output/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest);copied[rel]=sha(dest)
    for path in (stage/'clock').glob('*.v'):
        dest=output/'source/FPGA/ip/scope_clk_wiz'/path.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        assert path.read_bytes()==(ROOT/'FPGA/ip/scope_clk_wiz'/path.name).read_bytes()
        copied[str(dest.relative_to(output/'source'))]=sha(dest)
    release={'build':m['build'],'capabilities':m['capabilities'],'baud':921600,'rate':25000000,'depth':16384,
        'offline_verdict':'PASS','hardware_verdict':'PENDING','flash_programmed':False,
        'flash_programming_requires_user_instruction':True,'bitstream':bit.name,'bitstream_sha256':sha(bit),
        'setup_wns_ns':float(row[1]),'hold_whs_ns':float(row[2]),'pulse_width_slack_ns':float(row[3]),
        'pc_tests':int(match[1]),'build_report':str(report),'source_sha256':copied}
    if require_iob:release.update(adc_iob_actual_placement='PASS',adc_iob_registers=13,adc_iob_placement_report='implementation/adc_iob_placement.tsv')
    (output/'release_manifest.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SATURATION_CANDIDATE_PASS '+str(output));print(json.dumps({k:release[k] for k in ('build','bitstream_sha256','setup_wns_ns','hold_whs_ns')}))
if __name__=='__main__':main()
