"""Audit the completed review, exact FFT results and preserve its candidate.

Never programs JTAG or Flash. The original floating-only audit failure is
preserved; the stronger exact review and strict 20-packet audit are required.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as p
from audit_board_multires import audit as audit_multires
from audit_board_analysis import audit as audit_analysis
from fft_bitaccurate_reference import fft_integer

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def checked(path,marker):
    body=path.read_text(encoding='utf-8',errors='replace')
    assert marker in body and not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL|BOARD_BUILD_FAIL)',body),path
    return body

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('report',type=Path)
    cli.add_argument('--output',type=Path,required=True)
    a=cli.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    review=a.report.resolve()
    reviewed=json.loads((review/'manifest.json').read_text(encoding='utf-8'))
    for key in ('verdict','analysis_simulation','capture_modes_simulation'):
        assert reviewed.get(key)=='PASS',(key,reviewed.get(key))
    assert reviewed['exact_fft_bins_compared']==2048
    assert sha(ROOT/'FPGA/sim/tb/tb_scope_board.sv')==reviewed['verification_tb_sha256']
    report=Path(reviewed.get('base_report',str(review)))
    m=json.loads((report/'manifest.json').read_text(encoding='utf-8'))
    stage=Path(m['stage'])
    assert (stage/'scope_board_25m.xdc').read_bytes()==(ROOT/'FPGA/constraints/scope_board_25m.xdc').read_bytes()
    for name in ('scope_clk_wiz.v','scope_clk_wiz_clk_wiz.v'):
        assert (stage/'clock'/name).read_bytes()==(ROOT/'FPGA/ip/scope_clk_wiz'/name).read_bytes()
    for key in ('simulation','boot_preset_simulation','multires_simulation'):
        assert m.get(key)=='PASS',(key,m.get(key))
    for rel,digest in m['source_sha256'].items():
        assert sha(ROOT/rel)==digest,rel
        copies=list((stage/'src').glob('*_'+Path(rel).name))
        assert len(copies)==1 and sha(copies[0])==digest,rel
    for label,marker in (
        ('simulate','TEST_PASS tb_scope_board '),('boot.simulate','TEST_PASS tb_scope_board_boot '),
        ('multires.simulate','TEST_PASS tb_scope_board_multires '),
        ('analysis.simulate','TEST_PASS tb_scope_board_analysis '),
        ('capture_modes.simulate','TEST_PASS tb_scope_board_capture_modes ')):
        origin=review if label in ('analysis.simulate','capture_modes.simulate') else report
        checked(origin/(label+'.log'),marker)
    audit_multires(report/'multires_vectors_and_traces')
    audit_analysis(review/'analysis_vectors_and_traces',exact_fft=lambda samples:fft_integer(samples,stage/'exact_model'))
    parser=p.Parser()
    frames=parser.feed(bytes.fromhex((stage/'capture_modes_vectors/uart.hex').read_text()))
    assert len(frames)==20 and not parser.buffer and not any(parser.errors.values())
    expected=[0,1,2,12,13,14,15,16,17,18,19,20,21,22,23,24,18,25,26,18]
    assert [f.sequence for f in frames]==expected
    assert frames[0].payload==b'BOARD25'
    assert frames[1].payload==b'\x01\0\0\0'+struct.pack('<I',0xA1261026)
    assert all(f.flags==p.RESPONSE for f in frames)
    assert all(f.payload==b'\0' for f in frames if f.kind not in (0x81,0x82,0x83,0x93))
    assert [p.decode_capture_configuration(f) for f in frames if f.kind==0x93]==[(0,25000),(1,25000)]
    implementation=stage/'capture_modes_implementation.log'
    if not implementation.exists():implementation=report/'implementation.log'
    checked(implementation,'BOARD_BITSTREAM_PASS')
    checked(stage/'flash_prepare.log','FLASH_PREPARE_PASS')
    timing=(stage/'artifacts/timing.rpt').read_text(encoding='utf-8')
    row=re.search(r'^\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)',timing,re.M)
    assert row and 'All user specified timing constraints are met.' in timing
    tests=(ROOT/'tmp/capture_modes_pc_tests.log').read_text(encoding='utf-8',errors='replace')
    assert re.search(r'Ran 109 tests',tests) and tests.rstrip().endswith('OK')
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(stage/'artifacts',output/'implementation')
    bit=output/'scope_capture_modes_25m.bit'
    shutil.copyfile(stage/'flash/scope_capture_modes_flash.bit',bit)
    shutil.copytree(stage/'flash',output/'flash')
    shutil.copytree(review,output/'evidence/exact_review')
    if report!=review:shutil.copytree(report,output/'evidence/initial_build')
    shutil.copyfile(ROOT/'tmp/capture_modes_pc_tests.log',output/'evidence/pc_tests.log')
    shutil.copyfile(implementation,output/'evidence/implementation.log')
    sources=set(m['source_sha256'])
    sources.update(str(path.relative_to(ROOT)) for folder,pattern in (
        ('PC/protocol','*.py'),('PC/tests','*.py'),('FPGA/scripts','*.py'),
        ('FPGA/scripts','*.tcl'),('FPGA/scripts','*.json'),('FPGA/sim/tb','*.sv'),
        ('FPGA/sim/models','*.sv')) for path in (ROOT/folder).glob(pattern))
    sources.update(('示波器显示界面.py','PC/ui/requirements.txt','PC/protocol/protocol_spec.md',
        'FPGA/constraints/scope_board_25m.xdc','docs/verification/capture_modes_implementation_20261026.md'))
    identity={}
    for rel in sorted(sources):
        dest=output/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/rel,dest);identity[rel]=sha(dest)
    for path in (ROOT/'FPGA/ip/scope_clk_wiz').glob('*.v'):
        rel=str(path.relative_to(ROOT));dest=output/'source'/rel
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest);identity[rel]=sha(dest)
    manifest={'build':'0xA1261026','capabilities':15,'baud':921600,'rate':25000000,'depth':16384,
        'offline_verdict':'PASS','hardware_verdict':'PENDING','flash_programmed':False,
        'build_report':str(report),'exact_review_report':str(review),'stage':str(stage),'bitstream_sha256':sha(bit),
        'setup_wns_ns':float(row[1]),'hold_whs_ns':float(row[2]),'pulse_width_slack_ns':float(row[3]),
        'source_sha256':identity,'original_orchestration_verdict':m['verdict'],
        'capture_modes_audited_packets':20,'pc_tests':109}
    (output/'release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CAPTURE_MODES_CANDIDATE_PASS '+str(output))
    print(json.dumps({k:manifest[k] for k in ('bitstream_sha256','setup_wns_ns','hold_whs_ns','pulse_width_slack_ns')}))

if __name__=='__main__':main()
