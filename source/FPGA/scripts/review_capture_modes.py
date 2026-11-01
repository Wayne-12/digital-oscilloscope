"""Rerun board analysis with full FFT traces and the capture-mode contract.

Reuse only the completed baseline and multires runs with byte-identical RTL.
All new runs have distinct evidence; original failed audit is preserved.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as p
from audit_board_analysis import audit
from fft_bitaccurate_reference import fft_integer

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    base=Path(sys.argv[1]).resolve()
    reuse=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else None
    m=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    stage=Path(m['stage'])
    for key in ('simulation','boot_preset_simulation','multires_simulation'):
        assert m[key]=='PASS'
    for rel,digest in m['source_sha256'].items():
        assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest
        copies=list((stage/'src').glob('*_'+Path(rel).name))
        assert len(copies)==1 and hashlib.sha256(copies[0].read_bytes()).hexdigest()==digest
    report=ROOT/'FPGA/reports/capture_modes'/datetime.now().strftime('%Y%m%d_%H%M%S')
    report.mkdir(parents=True)
    model=stage/'exact_model';model.mkdir(exist_ok=True)
    archive=stage/'ip/scope_fft_1024/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip'
    with zipfile.ZipFile(archive) as z:z.extractall(model)
    manifest={'verdict':'RUNNING','stage':str(stage),'base_report':str(base),
        'source_sha256':m['source_sha256'],'verification_tb_sha256':hashlib.sha256((ROOT/'FPGA/sim/tb/tb_scope_board.sv').read_bytes()).hexdigest(),
        'cmodel_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    def save():(report/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    save();print('MODES_REVIEW_REPORT='+str(report),flush=True)
    binary=Path(json.loads((ROOT/'FPGA/scripts/vivado_toolchain.json').read_text())['bin'])
    env=os.environ.copy();env['TEMP']=env['TMP']=str(stage/'tool_tmp')
    def run(args,label,marker=None):
        with (report/(label+'.log')).open('wb') as stream:
            code=subprocess.run(' '.join('"'+str(x)+'"' for x in args),cwd=stage,env=env,stdout=stream,stderr=subprocess.STDOUT,shell=True).returncode
        body=(report/(label+'.log')).read_text(encoding='utf-8',errors='replace')
        assert code==0 and not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL)',body),body[-2000:]
        if marker:assert marker in body
        manifest[label]='PASS';save();print('MODES_REVIEW_PASS '+label,flush=True)
    try:
        if reuse:
            previous=json.loads((reuse/'manifest.json').read_text(encoding='utf-8'))
            assert previous['verification_tb_sha256']==manifest['verification_tb_sha256']
            assert previous['source_sha256']==manifest['source_sha256']
            assert previous['analysis.simulate']=='PASS'
            for label in ('compile','elaborate','analysis.simulate'):
                body=(reuse/(label+'.log')).read_text(encoding='utf-8',errors='replace')
                assert not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL)',body)
                if label=='analysis.simulate':assert 'TEST_PASS tb_scope_board_analysis' in body
                shutil.copyfile(reuse/(label+'.log'),report/(label+'.log'))
                manifest[label]='PASS'
            manifest['reused_completed_analysis']=str(reuse);save()
        else:
            shutil.copyfile(ROOT/'FPGA/sim/tb/tb_scope_board.sv',stage/'tb_scope_board.sv')
            run([binary/'xvlog.bat','--sv','tb_scope_board.sv'],'compile')
        exported=(stage/'export/scope_fft_1024/xsim/scope_fft_1024.sh').read_text()
        line=next(s for s in exported.splitlines() if s.startswith('  xelab '))
        libs=[x for lib in re.findall(r'-L (\w+)',line) if lib!='xil_defaultlib' for x in ('-L',lib)]
        analysis=stage/'exact_analysis_vectors'
        if not reuse:
            run([binary/'xelab.bat','work.tb_scope_board','work.glbl','-s','tb_scope_board_review',
                '--generic_top','TEST_BAUD=1152000',*libs,'-L','unisims_ver','-L','secureip','--timescale','1ns/1ps'],'elaborate')
            analysis.mkdir()
            for path in [*(stage/'analysis_vectors').glob('cmd_*.hex'),stage/'analysis_vectors/lengths.txt']:
                shutil.copyfile(path,analysis/path.name)
            run([binary/'xsim.bat','tb_scope_board_review','--runall','--onfinish','quit','--onerror','quit',
                '--testplusarg',f'VECTOR_DIR={analysis.as_posix()}','--testplusarg','ANALYSIS_TEST'],
                'analysis.simulate','TEST_PASS tb_scope_board_analysis')
        manifest.update(audit(analysis,exact_fft=lambda samples:fft_integer(samples,model)))
        manifest['exact_fft_bins_compared']=2048;save()
        shutil.copytree(analysis,report/'analysis_vectors_and_traces')
        modes=stage/'capture_modes_vectors';modes.mkdir()
        for path in (stage/'vectors').glob('cmd_*.hex'):shutil.copyfile(path,modes/path.name)
        lengths=[int(v) for v in (stage/'vectors/lengths.txt').read_text().split()]
        edge=struct.pack('<BBhHhhIIHI',0,0,0,8,-100,100,1,100,100,256)
        impossible=struct.pack('<BBhHhhIIHI',0,0,4095,8,-100,100,1,100,100,256)
        extra=[(p.STOP,b''),(p.SET_TRIGGER,impossible),(p.SET_CAPTURE_MODE,p.capture_mode_payload(0,25000)),
            (p.GET_CAPTURE_CONFIG,b''),(p.RUN,b''),(p.RELEASE_FRAME,b''),(p.STOP,b''),
            (p.SET_CAPTURE_MODE,p.capture_mode_payload(1,25000)),(p.RUN,b''),(p.STOP,b''),
            (p.SET_TRIGGER,edge),(p.RUN,b''),(p.RELEASE_FRAME,b''),(p.SINGLE,b''),(p.GET_CAPTURE_CONFIG,b'')]
        for index,(kind,payload) in enumerate(extra,12):
            wire=p.encode(p.Frame(kind,index,payload=payload));lengths.append(len(wire))
            (modes/f'cmd_{index}.hex').write_text(''.join(f'{x:02x}\n' for x in wire))
        (modes/'lengths.txt').write_text('\n'.join(map(str,lengths)))
        run([binary/'xsim.bat','tb_scope_board_review','--runall','--onfinish','quit','--onerror','quit',
            '--testplusarg',f'VECTOR_DIR={modes.as_posix()}','--testplusarg','CAPTURE_MODES_TEST'],
            'capture_modes.simulate','TEST_PASS tb_scope_board_capture_modes')
        parser=p.Parser();packets=parser.feed(bytes.fromhex((modes/'uart.hex').read_text()))
        assert len(packets)==20 and not parser.buffer and not any(parser.errors.values())
        assert not any(f.flags&p.ERROR for f in packets)
        assert [p.decode_capture_configuration(f) for f in packets if f.kind==0x93]==[(0,25000),(1,25000)]
        shutil.copytree(modes,report/'capture_modes_vectors_and_traces')
        manifest['capture_modes_simulation']='PASS';manifest['verdict']='PASS';save()
    except BaseException as exc:
        manifest['verdict']='FAIL';manifest['error']=repr(exc);save();raise
    print('CAPTURE_MODES_REVIEW_PASS '+str(report),flush=True)

if __name__=='__main__':main()
