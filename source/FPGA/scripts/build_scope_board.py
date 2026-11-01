"""Stage a physical EGO1 baseline, simulate pin-level UART, and implement it."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, tempfile, zipfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FPGA=ROOT/'FPGA'
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as proto
from audit_board_multires import audit as audit_multires

def main():
    p=argparse.ArgumentParser();p.add_argument('--implement',action='store_true')
    p.add_argument('--simulation-baud',type=int,choices=(115200,921600,1152000),default=1152000)
    p.add_argument('--hardware-baud',type=int,choices=(115200,921600),default=115200)
    p.add_argument('--reuse-report',type=Path,
        help='Reuse only a passing simulation with unchanged production RTL and clock HDL')
    p.add_argument('--reaudit-multires',action='store_true',
        help='Re-audit completed pin traces when only the previous Python audit failed; preserve that report')
    p.add_argument('--stage-root',type=Path,help='ASCII scratch parent for Vivado/XSim')
    a=p.parse_args()
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    binary=Path(json.loads((FPGA/'scripts/vivado_toolchain.json').read_text())['bin'])
    rid=datetime.now().strftime('%Y%m%d_%H%M%S')
    report=FPGA/'reports/board'/rid;report.mkdir(parents=True,exist_ok=False)
    baseline=None
    if a.reuse_report:
        baseline=json.loads((a.reuse_report/'manifest.json').read_text(encoding='utf-8'))
        if (baseline.get('simulation')!='PASS' or
                baseline.get('boot_preset_simulation')!='PASS' or
                (baseline.get('multires_simulation')!='PASS' and not a.reaudit_multires) or
                baseline.get('analysis_simulation')!='PASS'):
            raise RuntimeError('Baseline must pass normal, boot-preset, multires and frozen-analysis simulations')
    stage_root=a.stage_root or Path(tempfile.gettempdir())
    if not baseline and not str(stage_root).isascii() and os.name=='nt':
        stage_root=Path(os.environ['LOCALAPPDATA'])/'Temp'
    if not baseline:
        if not str(stage_root).isascii():raise RuntimeError('Use --stage-root with an ASCII directory')
        stage_root.mkdir(parents=True,exist_ok=True)
    if baseline:
        stage=Path(baseline['stage'])
    else:
        # Use inherited workspace ACLs on Windows; Python 3.14 mkdtemp's
        # private-directory ACL can deny the vendor subprocess access.
        stage=stage_root/f'scope_board_{rid}_{os.urandom(4).hex()}'
        stage.mkdir()
    manifest=dict(verdict='RUNNING',part='xc7a35tcsg324-1',baud=a.hardware_baud,rate=25000000,
        depth=16384,stage=str(stage),source_sha256={},simulation='NOT_RUN',implementation='NOT_RUN')
    def save():(report/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    def run(args,label,marker=None):
        log=report/f'{label}.log'
        command=' '.join('"'+str(x)+'"' for x in args) if str(args[0]).endswith('.bat') else args
        tool_env=os.environ.copy()
        tool_env['SCOPE_UART_BAUD']=str(a.hardware_baud)
        tool_tmp=stage/'tool_tmp';tool_tmp.mkdir(exist_ok=True)
        # XSim's bundled GCC also needs a writable ASCII TEMP, independently
        # of the HDL working directory. Never change the user's global TEMP.
        if os.name=='nt':
            for key in ('TEMP','TMP','TMPDIR'):tool_env[key]=str(tool_tmp)
            # Tcl Store caches under APPDATA on Windows; isolate only the
            # tool subprocess cache when the host profile is not writable.
            tool_appdata=stage/'tool_appdata';tool_appdata.mkdir(exist_ok=True)
            tool_env['APPDATA']=str(tool_appdata)
            # Use the bundled Tcl app repository without profile catalog writes.
            # Xilinx documents these two variables for a local Tcl Store.
            tool_env['XILINX_TCLAPP_REPO']=str(binary.parent/'data/XilinxTclStore')
            tool_env['XILINX_LOCAL_USER_DATA']='NO'
        with log.open('wb') as f:
            result=subprocess.run(command,cwd=stage,env=tool_env,stdout=f,stderr=subprocess.STDOUT,shell=isinstance(command,str))
        text=log.read_text(encoding='utf-8',errors='replace')
        if result.returncode or re.search(r'(?m)^\s*(?:ERROR:|Fatal:|TEST_FAIL|BOARD_BUILD_FAIL)',text) or marker and marker not in text:
            raise RuntimeError(f'{label} failed: {text[-2500:]}')
        print(f'BOARD_STAGE_PASS {label}',flush=True)
        manifest[label]='PASS';save()
    print(f'BOARD_REPORT={report}\nBOARD_STAGE={stage}',flush=True);save()
    try:
        if baseline:
            for rel,digest in baseline['source_sha256'].items():
                if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=digest:
                    raise RuntimeError(f'Production source changed since simulation: {rel}')
            # Require staged production copies to match their current originals.
            for rel,digest in baseline['source_sha256'].items():
                copies=list((stage/'src').glob('*_'+Path(rel).name))
                if len(copies)!=1 or hashlib.sha256(copies[0].read_bytes()).hexdigest()!=digest:
                    raise RuntimeError(f'Staged production source mismatch: {rel}')
            for name in ('scope_clk_wiz.v','scope_clk_wiz_clk_wiz.v'):
                if (stage/'clock'/name).read_bytes()!=(FPGA/'ip/scope_clk_wiz'/name).read_bytes():
                    raise RuntimeError(f'Clock HDL changed since simulation: {name}')
            if (stage/'tb_scope_board.sv').read_bytes()!=(FPGA/'sim/tb/tb_scope_board.sv').read_bytes():
                raise RuntimeError('Board testbench changed since simulation')
            for key in ('simulation','simulation_baud','compared_samples','uart_compared_samples','simulation_scope','source_sha256',
                        'boot_preset_simulation','boot_preset_compared_samples','boot_preset_uart_compared_samples',
                        'analysis_simulation','analysis_frames','analysis_samples_compared','analysis_checks',
                        ):
                manifest[key]=baseline[key]
            transcript=(a.reuse_report/'multires.simulate.log').read_text(encoding='utf-8',errors='replace')
            if 'TEST_PASS tb_scope_board_multires' not in transcript or re.search(r'(?m)^\s*(?:ERROR:|Fatal:|TEST_FAIL)',transcript):
                raise RuntimeError('No completed passing multires pin-level simulation to re-audit')
            manifest.update(audit_multires(stage/'multires_vectors'))
            manifest['multires_trace_reaudit']=bool(a.reaudit_multires)
            shutil.copytree(stage/'multires_vectors',report/'multires_vectors_and_traces')
            manifest['simulation_report']=str(a.reuse_report)
            shutil.copyfile(FPGA/'constraints/scope_board_25m.xdc',stage/'scope_board_25m.xdc')
            shutil.copyfile(FPGA/'scripts/build_scope_board.tcl',stage/'build.tcl')
            shutil.copyfile(FPGA/'scripts/ensure_scope_fft_ip.tcl',stage/'ensure_scope_fft_ip.tcl')
        else:
            (stage/'src').mkdir();(stage/'clock').mkdir();(stage/'vectors').mkdir()
            # Only production RTL and generated clock HDL enter synthesis.
            pkg=[FPGA/'rtl/common/scope_pkg.sv',
                 FPGA/'rtl/common/multires_pkg.sv',FPGA/'rtl/common/protocol_pkg.sv',
                 FPGA/'rtl/common/fft_window_pkg.sv',FPGA/'rtl/common/spectrum_pkg.sv']
            selected=pkg+list((FPGA/'rtl/uart_proto').glob('*.sv'))+[
                *list((FPGA/'rtl/measure').glob('*.sv')),FPGA/'rtl/multires/multires_envelope.sv',
                FPGA/'rtl/dac_dds/dds_core.sv',FPGA/'rtl/dac_dds/dds_sine_lut.sv',FPGA/'rtl/dac_dds/scope_board_dds.sv',
                *list((FPGA/'rtl/clock_reset').glob('*.sv')),FPGA/'rtl/top/scope_core.sv',FPGA/'rtl/top/scope_board_top.sv',
                FPGA/'rtl/adc_if/adc_capture.sv',FPGA/'rtl/capture/bram_capture.sv',FPGA/'rtl/capture/capture_bram.sv',
                FPGA/'rtl/trigger/trigger_core.sv',FPGA/'rtl/trigger/trigger_edge.sv']
            for i,src in enumerate(selected):
                dest=stage/'src'/f'{i:03}_{src.name}';shutil.copyfile(src,dest)
                manifest['source_sha256'][str(src.relative_to(ROOT))]=hashlib.sha256(src.read_bytes()).hexdigest()
            for name in ('scope_clk_wiz.v','scope_clk_wiz_clk_wiz.v'):
                shutil.copyfile(FPGA/'ip/scope_clk_wiz'/name,stage/'clock'/name)
            save()
            shutil.copyfile(FPGA/'constraints/scope_board_25m.xdc',stage/'scope_board_25m.xdc')
            shutil.copyfile(FPGA/'scripts/build_scope_board.tcl',stage/'build.tcl')
            shutil.copyfile(FPGA/'scripts/ensure_scope_fft_ip.tcl',stage/'ensure_scope_fft_ip.tcl')
            models=['ad9767_model.sv','ad9226_model.sv','loopback_channel_model.sv']
            for name in models:shutil.copyfile(FPGA/'sim/models'/name,stage/name)
            shutil.copyfile(FPGA/'sim/tb/tb_scope_board.sv',stage/'tb_scope_board.sv')
            manifest['verification_tb_sha256']=hashlib.sha256((stage/'tb_scope_board.sv').read_bytes()).hexdigest()
            shutil.copyfile(FPGA/'sim/tb/tb_scope_board_dds.sv',stage/'tb_scope_board_dds.sv')
            v=stage/'vectors'
            requests=[(proto.PING,b'BOARD25'),(proto.GET_VERSION,b''),(proto.GET_STATUS,b''),
                (proto.SET_RECORD,struct.pack('<II',32768,500000)),
                (proto.SET_RECORD,struct.pack('<II',16384,500000)),
                (proto.SET_TRIGGER,struct.pack('<BBhHhhIIHI',0,0,0,8,-100,100,1,100,100,256)),
                (proto.SET_DDS,struct.pack('<BBIIHi',0,1,100000,0,819,0)),
                (proto.SINGLE,b''),(proto.GET_STATUS,b''),(proto.READ_WAVE,struct.pack('<II',0,64)),
                (proto.READ_WAVE,struct.pack('<II',16320,64)),(proto.STOP,b'')]
            lengths=[]
            for i,(kind,payload) in enumerate(requests):
                data=proto.encode(proto.Frame(kind,sequence=i,payload=payload));lengths.append(len(data))
                (v/f'cmd_{i}.hex').write_text(''.join(f'{x:02x}\n' for x in data),encoding='ascii')
            (v/'lengths.txt').write_text('\n'.join(map(str,lengths)),encoding='ascii')
            sources=[*sorted((stage/'src').glob('*.sv')),*sorted((stage/'clock').glob('*.v')),
                *[stage/n for n in models],stage/'tb_scope_board.sv',stage/'tb_scope_board_dds.sv']
            (stage/'scripts').mkdir(exist_ok=True)
            shutil.copyfile(FPGA/'scripts/ensure_scope_fft_ip.tcl',stage/'scripts/ensure_scope_fft_ip.tcl')
            shutil.copyfile(FPGA/'scripts/prepare_fft_development.tcl',stage/'prepare_fft.tcl')
            run([binary/'vivado.bat','-mode','batch','-notrace','-source','prepare_fft.tcl',
                 '-tclargs',stage,stage],'fft.prepare','FFT_PREPARE_PASS')
            shutil.copyfile(binary.parent/'data/xsim/xsim.ini',stage/'xsim.ini')
            run([binary/'xvhdl.bat','--relax','ip/scope_fft_1024/sim/scope_fft_1024.vhd'],'fft.vendor')
            exported=(stage/'export/scope_fft_1024/xsim/scope_fft_1024.sh').read_text()
            line=next(s for s in exported.splitlines() if s.startswith('  xelab '))
            fft_libs=[x for lib in re.findall(r'-L (\w+)',line) if lib!='xil_defaultlib' for x in ('-L',lib)]
            run([binary/'xvlog.bat','--sv' ,*sources,binary.parent/'data/verilog/src/glbl.v'],'compile')
            run([binary/'xelab.bat','work.tb_scope_board_dds','-s','tb_scope_board_dds','--timescale','1ns/1ps'],'dds.elaborate')
            run([binary/'xsim.bat','tb_scope_board_dds','--runall','--onfinish','quit','--onerror','quit'],
                'dds.simulate','TEST_PASS tb_scope_board_dds')
            run([binary/'xelab.bat','work.tb_scope_board','work.glbl','-s','tb_scope_board',
                 '--generic_top',f'TEST_BAUD={a.simulation_baud}',*fft_libs,'-L','unisims_ver','-L','secureip','--timescale','1ns/1ps'],'elaborate')
            run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
                 '--testplusarg',f'VECTOR_DIR={v.as_posix()}'],'simulate','TEST_PASS tb_scope_board')
            parser=proto.Parser();frames=parser.feed(bytes.fromhex((v/'uart.hex').read_text()))
            assert len(frames)==12 and parser.good_frames==12 and not any(parser.errors.values()),(len(frames),parser.errors)
            assert frames[0].payload==b'BOARD25'
            assert frames[3].flags&proto.ERROR and frames[3].payload==b'\x02'
            assert frames[4].payload==b'\0' and frames[8].payload[0]&2
            live={int(t):int(raw,16)|(int(otr)<<15) for t,raw,otr in
                  (line.strip().split(',') for line in (v/'live.csv').open())}
            wave_frames=[f for f in frames if f.kind==0xb0]
            assert len(wave_frames)==2
            first=wave_frames[0].timestamp
            frozen=[int(x,16) for x in (v/'frozen.hex').read_text().split()]
            expected=[live[(first+i)&((1<<64)-1)] for i in range(16384)]
            assert frozen==expected,'full frozen record differs from physical ADC capture'
            for f,offset in zip(wave_frames,(0,16320)):
                assembler=proto.WaveAssembler();wave=assembler.accept(f)
                assert wave is not None and len(wave)==64
                assert assembler.rate==25000000 and assembler.trigger==8192 and assembler.base==first
                assert wave==expected[offset:offset+64],'UART physical-pin boundary read differs'
            manifest['simulation']='PASS';manifest['compared_samples']=16384
            manifest['simulation_baud']=a.simulation_baud;manifest['uart_compared_samples']=128
            manifest['simulation_scope']='all 16384 frozen words observed; first/last 64 words read through UART pins'
            shutil.copytree(v,report/'vectors_and_traces')
            save()
            print('BOARD_PIN_SIM_PASS packets=12 memory_samples=16384 uart_samples=128',flush=True)
            # A second fresh simulation uses no SET_RECORD/TRIGGER/DDS commands:
            # verify power-up defaults can capture after the manual OFF->ON gate.
            boot=stage/'boot_vectors';boot.mkdir()
            for path in [*v.glob('cmd_*.hex'),v/'lengths.txt']:
                shutil.copyfile(path,boot/path.name)
            run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
                 '--testplusarg',f'VECTOR_DIR={boot.as_posix()}','--testplusarg','BOOT_PRESET_ONLY'],
                'boot.simulate','TEST_PASS tb_scope_board_boot')
            parser=proto.Parser();frames=parser.feed(bytes.fromhex((boot/'uart.hex').read_text()))
            assert len(frames)==8 and parser.good_frames==8 and not any(parser.errors.values())
            assert [f.sequence for f in frames]==[0,1,2,7,8,9,10,11]
            assert frames[0].payload==b'BOARD25'
            assert frames[1].payload==b'\x01\x00\x00\x00'+struct.pack('<I',0xA1261026)
            assert frames[2].payload[0]==4 and frames[4].payload[0]&2
            assert frames[3].payload==b'\0' and frames[7].payload==b'\0'
            live={int(t):int(raw,16)|(int(otr)<<15) for t,raw,otr in
                  (line.strip().split(',') for line in (boot/'live.csv').open())}
            wave_frames=[f for f in frames if f.kind==0xb0]
            assert len(wave_frames)==2
            first=wave_frames[0].timestamp
            expected=[live[(first+i)&((1<<64)-1)] for i in range(16384)]
            assert [int(x,16) for x in (boot/'frozen.hex').read_text().split()]==expected
            for f,offset in zip(wave_frames,(0,16320)):
                assembler=proto.WaveAssembler();wave=assembler.accept(f)
                assert wave==expected[offset:offset+64] and assembler.rate==25000000
                assert assembler.trigger==8192 and assembler.base==first
            manifest['boot_preset_simulation']='PASS'
            manifest['boot_preset_compared_samples']=16384
            manifest['boot_preset_uart_compared_samples']=128
            shutil.copytree(boot,report/'boot_vectors_and_traces')
            save()
            print('BOARD_BOOT_SIM_PASS packets=8 memory_samples=16384 uart_samples=128',flush=True)
            # Exercise the exact board/UART path, not a standalone reducer.
            multi=stage/'multires_vectors';multi.mkdir()
            extra=[(proto.GET_CAPABILITIES,b''),(proto.READ_ENVELOPE,struct.pack('<H',800)),
                (proto.READ_ENVELOPE,struct.pack('<H',400)),(proto.READ_WAVE,struct.pack('<II',7000,1024)),
                (proto.READ_ENVELOPE,struct.pack('<H',0)),(proto.READ_ENVELOPE,struct.pack('<H',801)),
                (proto.READ_ENVELOPE,b'\x01'),(proto.READ_WAVE,struct.pack('<II',16380,8)),
                (proto.READ_ENVELOPE,struct.pack('<H',800)),(proto.STOP,b''),
                (proto.PING,b'AFTER_CANCEL'),(proto.READ_ENVELOPE,struct.pack('<H',100)),
                (proto.GET_CONFIG,b''),(proto.SET_DDS,struct.pack('<BBIIHi',3,1,234567,0x23456789,300,-123)),
                (proto.GET_CONFIG,b''),(proto.SET_DDS,struct.pack('<BBIIHi',0,1,100000,0,819,0)),
                (proto.GET_CONFIG,b'\x00'),(proto.GET_CONFIG,b'')]
            multi_lengths=[]
            for i,(kind,payload) in enumerate(requests+extra):
                data=proto.encode(proto.Frame(kind,sequence=i,payload=payload));multi_lengths.append(len(data))
                (multi/f'cmd_{i}.hex').write_text(''.join(f'{x:02x}\n' for x in data),encoding='ascii')
            (multi/'lengths.txt').write_text('\n'.join(map(str,multi_lengths)),encoding='ascii')
            run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
                '--testplusarg',f'VECTOR_DIR={multi.as_posix()}','--testplusarg','MULTIRES_TEST'],
                'multires.simulate','TEST_PASS tb_scope_board_multires')
            shutil.copytree(multi,report/'multires_vectors_and_traces')
            manifest.update(audit_multires(report/'multires_vectors_and_traces'));save()
            print('BOARD_MULTIRES_SIM_PASS buckets=1300 roi=1024 cancel_recovery=PASS',flush=True)
        if not baseline:
            analysis=stage/'analysis_vectors';analysis.mkdir()
            requests_analysis=requests+[(proto.GET_CAPABILITIES,b''),(proto.READ_MEASURE,b''),
                (proto.READ_SPECTRUM,b''),(proto.READ_MEASURE,b''),(proto.READ_SPECTRUM,b''),
                (proto.SINGLE,b''),(proto.READ_WAVE,struct.pack('<II',0,1024)),
                (proto.READ_MEASURE,b''),(proto.READ_SPECTRUM,b'')]
            for i,(kind,payload) in enumerate(requests_analysis):
                data=proto.encode(proto.Frame(kind,sequence=i,payload=payload))
                (analysis/f'cmd_{i}.hex').write_text(''.join(f'{x:02x}\n' for x in data),encoding='ascii')
            (analysis/'lengths.txt').write_text('\n'.join(str(len(proto.encode(proto.Frame(k,payload=p)))) for k,p in requests_analysis))
            run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
                '--testplusarg',f'VECTOR_DIR={analysis.as_posix()}','--testplusarg','ANALYSIS_TEST'],
                'analysis.simulate','TEST_PASS tb_scope_board_analysis')
            from audit_board_analysis import audit as audit_analysis
            from fft_bitaccurate_reference import fft_integer
            model=stage/'exact_model';model.mkdir()
            with zipfile.ZipFile(stage/'ip/scope_fft_1024/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip') as archive:
                archive.extractall(model)
            shutil.copytree(analysis,report/'analysis_vectors_and_traces')
            manifest.update(audit_analysis(report/'analysis_vectors_and_traces',exact_fft=lambda samples:fft_integer(samples,model)))
            manifest['exact_fft_bins_compared']=2048;save()
        if not baseline:
            modes=stage/'capture_modes_vectors';modes.mkdir()
            edge=struct.pack('<BBhHhhIIHI',0,0,0,8,-100,100,1,100,100,256)
            impossible=struct.pack('<BBhHhhIIHI',0,0,4095,8,-100,100,1,100,100,256)
            commands=requests+[(proto.STOP,b''),(proto.SET_TRIGGER,impossible),
                (proto.SET_CAPTURE_MODE,proto.capture_mode_payload(0,25000)),
                (proto.GET_CAPTURE_CONFIG,b''),(proto.RUN,b''),(proto.RELEASE_FRAME,b''),
                (proto.STOP,b''),(proto.SET_CAPTURE_MODE,proto.capture_mode_payload(1,25000)),
                (proto.RUN,b''),(proto.STOP,b''),(proto.SET_TRIGGER,edge),(proto.RUN,b''),
                (proto.RELEASE_FRAME,b''),(proto.SINGLE,b''),(proto.GET_CAPTURE_CONFIG,b'')]
            for i,(kind,payload) in enumerate(commands):
                data=proto.encode(proto.Frame(kind,sequence=i,payload=payload))
                (modes/f'cmd_{i}.hex').write_text(''.join(f'{x:02x}\n' for x in data),encoding='ascii')
            (modes/'lengths.txt').write_text('\n'.join(str(len(proto.encode(proto.Frame(k,payload=p)))) for k,p in commands))
            run([binary/'xsim.bat','tb_scope_board','--runall','--onfinish','quit','--onerror','quit',
                '--testplusarg',f'VECTOR_DIR={modes.as_posix()}','--testplusarg','CAPTURE_MODES_TEST'],
                'capture_modes.simulate','TEST_PASS tb_scope_board_capture_modes')
            parser=proto.Parser();packets=parser.feed(bytes.fromhex((modes/'uart.hex').read_text()))
            assert len(packets)==20 and not parser.buffer and not any(parser.errors.values()),len(packets)
            assert not any(f.flags&proto.ERROR for f in packets)
            configs=[proto.decode_capture_configuration(f) for f in packets if f.kind==0x93]
            assert configs==[(0,25000),(1,25000)],configs
            manifest['capture_modes_simulation']='PASS';save()
            shutil.copytree(modes,report/'capture_modes_vectors_and_traces')
        if a.implement:
            run([binary/'vivado.bat','-mode','batch','-notrace','-source','build.tcl','-log','build.log','-journal','build.jou'],
                'implementation','BOARD_BITSTREAM_PASS')
            manifest['implementation']='PASS'
        for rel,digest in manifest['source_sha256'].items():
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=digest:
                raise RuntimeError(f'Production source changed during build: {rel}')
        manifest['verdict']='PASS'
    except Exception as exc:
        manifest['verdict']='FAIL';manifest['error']=str(exc);print(str(exc),flush=True)
    finally:
        for name in ('build.log','build.jou'):
            if (stage/name).is_file():shutil.copyfile(stage/name,report/name)
        if (stage/'artifacts').is_dir():shutil.copytree(stage/'artifacts',report/'artifacts')
        save()
    print(f'BOARD_BUILD_{manifest["verdict"]} report={report}',flush=True)
    return manifest['verdict']!='PASS'

if __name__=='__main__':raise SystemExit(main())
