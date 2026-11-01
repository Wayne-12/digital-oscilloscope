"""Re-audit completed simulations after correcting the integer-window oracle.

Preserves the earlier FAIL report and all original transcripts. No RTL changes,
simulation skips, tolerance relaxation, bitstream rewrite, or hardware access.
"""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as p
from audit_board_analysis import audit
from audit_board_multires import audit as audit_multires
from resume_board_analysis import audit_capture

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('source_report',type=Path)
    a=cli.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    source=a.source_report.resolve()
    m=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    assert m['implementation']=='PASS' and m['analysis.simulate']=='PASS'
    for label,marker in [('simulate','TEST_PASS tb_scope_board '),
                         ('boot.simulate','TEST_PASS tb_scope_board_boot '),
                         ('multires.simulate','TEST_PASS tb_scope_board_multires '),
                         ('analysis.simulate','TEST_PASS tb_scope_board_analysis '),
                         ('implementation','BOARD_BITSTREAM_PASS')]:
        body=(source/(label+'.log')).read_text(encoding='utf-8',errors='replace')
        assert marker in body and not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL|BOARD_BUILD_FAIL)',body)
    for rel,digest in m['source_sha256'].items():assert sha(ROOT/rel)==digest,rel
    stage=Path(m['stage'])
    for rel,digest in m['source_sha256'].items():
        copies=list((stage/'src').glob('*_'+Path(rel).name))
        assert len(copies)==1 and sha(copies[0])==digest,rel
    assert sha(stage/'artifacts/scope_board_25m.bit')==sha(source/'artifacts/scope_board_25m.bit')
    audit_capture(source/'vectors_and_traces',False)
    audit_capture(source/'boot_vectors_and_traces',True)
    m.update(audit_multires(source/'multires_vectors_and_traces'))
    m.update(audit(stage/'analysis_vectors'))
    report=source.parent/datetime.now().strftime('%Y%m%d_%H%M%S_verified')
    shutil.copytree(source,report)
    shutil.copytree(stage/'analysis_vectors',report/'analysis_vectors_and_traces')
    previous=m.pop('error',None)
    m.update(verdict='PASS',source_report=str(source),capture_source_report=m['source_report'],
             oracle_reaudit_reason='Original oracle used ideal floating Hann instead of the established Q3/Q16 rounded front-end; exact harmonic bin checks now pass with the original tighter 0.125 ADC-code amplitude tolerance.',
             previous_failure=previous,hardware_verified=False,flash_programmed=False,
             bitstream_sha256=sha(source/'artifacts/scope_board_25m.bit'))
    m['oracle_sha256']={str(path.relative_to(ROOT)):sha(path) for path in (
        ROOT/'FPGA/scripts/audit_board_analysis.py',ROOT/'PC/protocol/spectrum_reference.py')}
    clocks={}
    for path in (stage/'clock').glob('*.v'):
        assert path.read_bytes()==(ROOT/'FPGA/ip/scope_clk_wiz'/path.name).read_bytes()
        clocks[path.name]=sha(path)
    m['clock_hdl_sha256']=clocks
    rows=[]
    packets=p.Parser().feed(bytes.fromhex((report/'analysis_vectors_and_traces/uart.hex').read_text()))
    for mi,si in ((13,14),(19,20)):
        measure=next(f for f in packets if f.sequence==mi and f.kind==0xb1)
        spectral=next(f for f in packets if f.sequence==si and f.kind==0xb3)
        rows.append({'timestamp':measure.timestamp,'measurement':p.decode_measurement(measure),
                     'spectrum':p.decode_spectrum(spectral)})
    (report/'summary_values.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (report/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    print('BOARD_FINAL_AUDIT_PASS report='+str(report))

if __name__=='__main__':main()
