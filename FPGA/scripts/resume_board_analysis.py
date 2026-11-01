"""Resume interrupted board verification without accepting incomplete traces.

Rebuilds the simulator from byte-checked production copies, re-audits completed
normal/boot runs, and reruns any interrupted multiresolution/analysis run.
Implementation may run independently of simulation; release requires both PASS.
"""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as p
from audit_board_multires import audit as audit_multires
from audit_board_analysis import audit as audit_analysis

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit_capture(folder,boot):
    parser=p.Parser()
    frames=parser.feed(bytes.fromhex((folder/'uart.hex').read_text()))
    assert len(frames)==(8 if boot else 12) and not parser.buffer and not any(parser.errors.values())
    assert frames[0].payload==b'BOARD25'
    assert frames[1].payload==b'\x01\0\0\0'+struct.pack('<I',0xA0261026)
    assert [f.sequence for f in frames]==([0,1,2,7,8,9,10,11] if boot else list(range(12)))
    live={int(t):int(raw,16)|(int(otr)<<15) for t,raw,otr in
          (line.split(',') for line in (folder/'live.csv').read_text().splitlines())}
    waves=[f for f in frames if f.kind==0xb0]
    assert len(waves)==2
    base=waves[0].timestamp
    words=[int(x,16) for x in (folder/'frozen.hex').read_text().split()]
    assert len(words)==16384 and words==[live[(base+i)%2**64] for i in range(16384)]
    for f,offset in zip(waves,(0,16320)):
        assembly=p.WaveAssembler()
        assert assembly.accept(f)==words[offset:offset+64]
        assert (assembly.rate,assembly.trigger,assembly.base)==(25000000,8192,base)
    assert frames[-1].payload==b'\0'

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('source_report',type=Path)
    cli.add_argument('--implement',action='store_true')
    cli.add_argument('--hardware-baud',type=int,choices=(115200,921600),default=921600)
    cli.add_argument('--simulation-baud',type=int,choices=(921600,1152000,1562500),default=1562500)
    a=cli.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    previous=json.loads((a.source_report/'manifest.json').read_text(encoding='utf-8'))
    stage=Path(previous['stage'])
    assert stage.is_dir() and str(stage).isascii()
    report=ROOT/'FPGA/reports/board'/datetime.now().strftime('%Y%m%d_%H%M%S')
    report.mkdir()
    binary=Path(json.loads((ROOT/'FPGA/scripts/vivado_toolchain.json').read_text())['bin'])
    manifest={'verdict':'RUNNING','part':'xc7a35tcsg324-1','baud':a.hardware_baud,
              'rate':25000000,'depth':16384,'stage':str(stage),'source_report':str(a.source_report.resolve()),
              'simulation_baud':a.simulation_baud,'source_sha256':{},'implementation':'NOT_RUN'}
    def save():
        (report/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    def checked_log(path,marker=None):
        text=path.read_text(encoding='utf-8',errors='replace')
        assert not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL|BOARD_BUILD_FAIL)',text),text[-2000:]
        if marker:assert marker in text,(path,marker)
    env=os.environ.copy()
    for key in ('TEMP','TMP','TMPDIR'):env[key]=str(stage/'tool_tmp')
    env.update(APPDATA=str(stage/'tool_appdata'),XILINX_LOCAL_USER_DATA='NO',
               XILINX_TCLAPP_REPO=str(binary.parent/'data/XilinxTclStore'),SCOPE_UART_BAUD=str(a.hardware_baud))
    def start(args,label):
        output=report/(label+'.log')
        stream=output.open('wb')
        command=' '.join('"'+str(x)+'"' for x in args)
        process=subprocess.Popen(command,cwd=stage,env=env,stdout=stream,stderr=subprocess.STDOUT,shell=True)
        return process,stream,output
    def finish(job,marker=None):
        process,stream,output=job
        status=process.wait();stream.close()
        assert status==0,(output,status)
        checked_log(output,marker)
        print('BOARD_RESUME_PASS '+output.stem,flush=True)
        manifest[output.stem]='PASS';save()
    def run(args,label,marker=None):finish(start(args,label),marker)
    implementation=None
    print('BOARD_RESUME_REPORT='+str(report),flush=True)
    try:
        sources={path.name:path for path in (ROOT/'FPGA/rtl').rglob('*.sv')}
        for copy in sorted((stage/'src').glob('*.sv')):
            source=sources[copy.name[4:]]
            assert source.read_bytes()==copy.read_bytes(),str(source)
            manifest['source_sha256'][str(source.relative_to(ROOT))]=digest(source)
        for path in (stage/'clock').glob('*.v'):
            assert path.read_bytes()==(ROOT/'FPGA/ip/scope_clk_wiz'/path.name).read_bytes()
        for path in [stage/'tb_scope_board.sv',stage/'tb_scope_board_dds.sv']:
            assert path.read_bytes()==(ROOT/'FPGA/sim/tb'/path.name).read_bytes()
        for name in ('ad9767_model.sv','ad9226_model.sv','loopback_channel_model.sv'):
            assert (stage/name).read_bytes()==(ROOT/'FPGA/sim/models'/name).read_bytes()
        assert (stage/'ensure_scope_fft_ip.tcl').read_bytes()==(ROOT/'FPGA/scripts/ensure_scope_fft_ip.tcl').read_bytes()
        manifest['fft_xci_sha256']=digest(stage/'ip/scope_fft_1024/scope_fft_1024.xci')
        save()
        # A finished transcript AND independently valid ADC/UART traces are
        # necessary for reuse. An interrupted run can never satisfy this gate.
        for label,folder,marker,boot in (
            ('simulate','vectors','TEST_PASS tb_scope_board ',False),
            ('boot.simulate','boot_vectors','TEST_PASS tb_scope_board_boot ',True)):
            checked_log(a.source_report/(label+'.log'),marker)
            audit_capture(stage/folder,boot)
            shutil.copyfile(a.source_report/(label+'.log'),report/(label+'.log'))
            shutil.copytree(stage/folder,report/(folder+'_and_traces'))
        manifest.update(simulation='PASS',compared_samples=16384,uart_compared_samples=128,
                        boot_preset_simulation='PASS',boot_preset_compared_samples=16384,
                        boot_preset_uart_compared_samples=128,
                        simulation_scope='full ADC record identity and first/last 64 UART samples; independently re-audited')
        save()
        hdl=[*sorted((stage/'src').glob('*.sv')),*sorted((stage/'clock').glob('*.v')),
             *[stage/n for n in ('ad9767_model.sv','ad9226_model.sv','loopback_channel_model.sv')],
             stage/'tb_scope_board.sv',stage/'tb_scope_board_dds.sv',binary.parent/'data/verilog/src/glbl.v']
        run([binary/'xvlog.bat','--sv',*hdl],'resume.compile')
        script=(stage/'export/scope_fft_1024/xsim/scope_fft_1024.sh').read_text()
        line=next(s for s in script.splitlines() if s.startswith('  xelab '))
        libs=[x for name in re.findall(r'-L (\w+)',line) if name!='xil_defaultlib' for x in ('-L',name)]
        run([binary/'xelab.bat','work.tb_scope_board','work.glbl','-s','tb_scope_board',
             '--generic_top',f'TEST_BAUD={a.simulation_baud}',*libs,'-L','unisims_ver',
             '-L','secureip','--timescale','1ns/1ps'],'resume.elaborate')
        if a.implement:
            shutil.copyfile(ROOT/'FPGA/scripts/build_scope_board.tcl',stage/'build.tcl')
            implementation=start([binary/'vivado.bat','-mode','batch','-notrace','-source','build.tcl',
                                  '-log','build.log','-journal','build.jou'],'implementation')
        multi=stage/'multires_vectors'
        run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
             '--testplusarg',f'VECTOR_DIR={multi.as_posix()}','--testplusarg','MULTIRES_TEST'],
            'multires.simulate','TEST_PASS tb_scope_board_multires')
        shutil.copytree(multi,report/'multires_vectors_and_traces')
        manifest.update(audit_multires(report/'multires_vectors_and_traces'));save()
        analysis=stage/'analysis_vectors';analysis.mkdir(exist_ok=True)
        lengths=[]
        base=[p.Parser().feed(bytes.fromhex((stage/'vectors'/f'cmd_{i}.hex').read_text()))[0] for i in range(12)]
        extra=[(p.GET_CAPABILITIES,b''),(p.READ_MEASURE,b''),(p.READ_SPECTRUM,b''),
               (p.READ_MEASURE,b''),(p.READ_SPECTRUM,b''),(p.SINGLE,b''),
               (p.READ_WAVE,struct.pack('<II',0,1024)),(p.READ_MEASURE,b''),(p.READ_SPECTRUM,b'')]
        for i,(kind,payload) in enumerate([(f.kind,f.payload) for f in base]+extra):
            data=p.encode(p.Frame(kind,sequence=i,payload=payload));lengths.append(len(data))
            (analysis/f'cmd_{i}.hex').write_text(''.join(f'{x:02x}\n' for x in data),encoding='ascii')
        (analysis/'lengths.txt').write_text('\n'.join(map(str,lengths)),encoding='ascii')
        run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
             '--testplusarg',f'VECTOR_DIR={analysis.as_posix()}','--testplusarg','ANALYSIS_TEST'],
            'analysis.simulate','TEST_PASS tb_scope_board_analysis')
        shutil.copytree(analysis,report/'analysis_vectors_and_traces')
        manifest.update(audit_analysis(report/'analysis_vectors_and_traces'));save()
        if implementation:finish(implementation,'BOARD_BITSTREAM_PASS');implementation=None
        for rel,value in manifest['source_sha256'].items():assert digest(ROOT/rel)==value,rel
        manifest['verdict']='PASS'
    except Exception as error:
        manifest.update(verdict='FAIL',error=repr(error))
        print('BOARD_RESUME_ERROR '+repr(error),flush=True)
    finally:
        if implementation:
            try:finish(implementation,'BOARD_BITSTREAM_PASS')
            except Exception as error:manifest['implementation_error']=repr(error)
        if (stage/'artifacts').is_dir():shutil.copytree(stage/'artifacts',report/'artifacts')
        save()
    print('BOARD_RESUME_'+manifest['verdict']+' report='+str(report),flush=True)
    return manifest['verdict']!='PASS'

if __name__=='__main__':raise SystemExit(main())
