"""Independent unit roots; no loopback, capture backend or system root is run."""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,sys,tempfile
from datetime import datetime
from pathlib import Path
from run_system_regression import RegressionFailure,run,verify_tool,first_time
from simulation_environment import configure

FPGA=Path(__file__).resolve().parents[1]
TESTS={
 'safe_seq':('tb_safe_seq','safe',None,'tb_safe'),
 'adc_capture':('tb_adc_capture','ad9226','ad9226','tb_ad9226'),
 'dds_dac':('tb_dds_dac','dds','dds','tb_dds'),
 'trigger':('tb_trigger','measure','measure','tb_trigger'),
 'capture_bram':('tb_capture_bram','capture','capture','tb_capture'),
 'measure':('tb_measure','measure','measure','tb_measure'),
 'uart_phy':('tb_uart_phy',None,None,'tb_uart_phy'),
 'protocol':('tb_protocol',None,'protocol_unit','tb_protocol'),
 'envelope':('tb_envelope','multires','multires','tb_multires'),
 'fft':('tb_fft','spectrum','spectrum','tb_spectrum'),
 'awg':('tb_awg',None,None,'tb_awg'),
}
PKGS=('scope_pkg','protocol_pkg','multires_pkg','fft_window_pkg','spectrum_pkg','innovation_pkg')

def sources(test):
    top,script,_,_=TESTS[test]
    if script:
        body=(FPGA/f'scripts/run_{script}_tb.ps1').read_text(encoding='utf-8-sig')
        paths=[FPGA/p for p in re.findall(r"'((?:rtl|sim)/[^']+\.sv)'",body)]
    elif test=='awg':
        paths=[FPGA/p for p in ('rtl/uart_proto/protocol_commands.sv',
               'rtl/measure/measure_udiv.sv',
               'rtl/dac_dds/dds_sine_lut.sv','rtl/dac_dds/scope_board_dds.sv')]
    else:
        names=('uart_tx','uart_rx') if test=='uart_phy' else ('frame_rx','frame_tx')
        paths=[FPGA/f'rtl/uart_proto/{n}.sv' for n in names]
    paths+=[FPGA/f'sim/tb/{top}.sv']
    packages=[FPGA/f'rtl/common/{n}.sv' for n in PKGS]
    return list(dict.fromkeys(packages+paths))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tests',nargs='+',choices=TESTS,default=list(TESTS))
    p.add_argument('--seeds',nargs='+',type=int,default=[20261020,42])
    p.add_argument('--vivado-bin',type=Path,default=Path(json.loads((FPGA/'scripts/vivado_toolchain.json').read_text())['bin']))
    p.add_argument('--inject-protocol-failure',action='store_true')
    a=p.parse_args()
    if len(set(a.seeds))!=len(a.seeds) or any(s<0 for s in a.seeds):p.error('seeds must be unique and nonnegative')
    if a.inject_protocol_failure and 'protocol' not in a.tests:p.error('select protocol for fault injection')
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    environment=configure(a.vivado_bin)
    rid=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    report=FPGA/'reports/unit'/rid;report.mkdir(parents=True)
    build=Path(tempfile.mkdtemp(prefix='scope_units_'))
    m=dict(verdict='FAIL',layer='unit',tests=a.tests,seeds=a.seeds,results=[],first_error=None,temporary_build=str(build),source_sha256={},environment=environment)
    def tool(name,args,work,label,pattern=None):
        code,text=run([str(a.vivado_bin/f'{name}.bat'),*args],work,report/f'{label}.log')
        # The exact release's vendor VHDL attribute warning is documented in
        # the existing FFT regression. No RTL warning is suppressed here.
        checked='\n'.join(s for s in text.splitlines() if not re.match(r'^WARNING: \[VRFC 10-9145\].*xfft_v9_1_15.*scope_fft_1024.vhd:201',s))
        verify_tool(code,checked,label,pattern)
        return text
    try:
        for test in a.tests:
            top,script,family,marker=TESTS[test]
            work=build/test;work.mkdir()
            paths=sources(test)
            staged=[]
            for i,src in enumerate(paths):
                if not src.is_file():raise RegressionFailure('SOURCE',str(src))
                m['source_sha256'][str(src.relative_to(FPGA))]=hashlib.sha256(src.read_bytes()).hexdigest()
                dest=work/f'{i:03}_{src.name}';shutil.copyfile(src,dest);staged.append(dest)
            libs=[]
            if test=='fft':
                args=[str(a.vivado_bin/'vivado.bat'),'-mode','batch','-notrace','-source',str(FPGA/'scripts/prepare_fft_development.tcl'),'-log','prepare.log','-journal','prepare.jou','-tclargs',str(work),str(FPGA)]
                code,text=run(args,work,report/'fft.prepare.log')
                if code or 'FFT_PREPARE_PASS' not in text or re.search(r'(?m)^(ERROR:|CRITICAL WARNING:)',text):raise RegressionFailure('FFT_PREPARE',text[-1200:])
                shutil.copyfile(a.vivado_bin/'../data/xsim/xsim.ini',work/'xsim.ini')
                tool('xvhdl',['--relax','ip/scope_fft_1024/sim/scope_fft_1024.vhd'],work,'fft.vendor')
                exported=(work/'export/scope_fft_1024/xsim/scope_fft_1024.sh').read_text()
                line=next(s for s in exported.splitlines() if s.startswith('  xelab '))
                libs=[x for lib in re.findall(r'-L (\w+)',line) if lib!='xil_defaultlib' for x in ('-L',lib)]
            tool('xvlog',['--sv',*map(str,staged)],work,f'{test}.compile')
            roots=[(top,marker)]
            if test=='fft':roots=[('tb_spectrum_isqrt','tb_spectrum_isqrt'),('tb_fft_wrapper','tb_fft_wrapper'),*roots]
            for root,_ in roots:tool('xelab',[f'work.{root}','--snapshot',root,'--timescale','1ns/1ps',*libs],work,f'{test}.{root}.elaborate')
            for seed in a.seeds:
                stage=work/f'seed_{seed}';v=stage/'vectors';e=stage/'expected';t=stage/'traces'
                t.mkdir(parents=True)
                if not family:
                    for d in (v,e):d.mkdir()
                if family:
                    generator=FPGA/f'scripts/generate_{family}_vectors.py'
                    args=[sys.executable,str(generator),'--output',str(v),'--seed',str(seed)]
                    if family!='protocol_unit':args+=['--expected-output',str(e)]
                    if family=='ad9226':args+=['--random-samples','10000']
                    code,text=run(args,work,report/f'{test}.seed{seed}.oracle.log')
                    if code or 'ORACLE_PASS' not in text:raise RegressionFailure('ORACLE_'+test,text[-1000:])
                for root,pass_name in roots:
                    label=f'{test}.{root}.seed{seed}'
                    args=[root,'--runall','--onfinish','quit','--onerror','quit','--sv_seed',str(seed)]
                    for item in (f'SEED={seed}',f'VECTOR_DIR={v.as_posix()}',f'EXPECTED_DIR={e.as_posix()}',f'TRACE_DIR={t.as_posix()}'):
                        args+=['--testplusarg',item]
                    if test=='protocol' and a.inject_protocol_failure:args+=['--testplusarg','INJECT_PROTOCOL_FAULT']
                    text=tool('xsim',args,work,label,rf'^TEST_PASS {pass_name}\b.*(?:errors=0|assertions_failed=0)')
                    markers=[s for s in text.splitlines() if s.startswith('TEST_PASS ')]
                    m['results'].append(dict(test=test,top=root,seed=seed,verdict='PASS',pass_markers=markers,log=f'{label}.log'))
                    print(f'UNIT_PASS test={test} top={root} seed={seed}',flush=True)
        for rel,digest in m['source_sha256'].items():
            if hashlib.sha256((FPGA/rel).read_bytes()).hexdigest()!=digest:raise RegressionFailure('SOURCE_CHANGED',rel)
        m['verdict']='PASS'
    except RegressionFailure as ex:
        m['first_error']=dict(code=ex.code,detail=str(ex),time_ns=ex.time_ns)
    except Exception as ex:
        m['first_error']=dict(code=type(ex).__name__,detail=str(ex),time_ns=None)
    finally:
        (report/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'UNIT_REGRESSION_{m["verdict"]} report={report}',flush=True)
    if m['first_error']:print('FIRST_FAILED_UNIT '+json.dumps(m['first_error'],ensure_ascii=False),flush=True)
    return int(m['verdict']!='PASS')

if __name__=='__main__':raise SystemExit(main())
