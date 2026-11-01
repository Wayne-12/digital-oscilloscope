"""Build and verify the full-record saturation extension using cached FFT IP.

The cached vendor IP and clock HDL come from the accepted previous build;
all production RTL and the board snapshot are compiled again from current files.
Implementation and bounded simulations run independently; both must pass.
"""
from pathlib import Path
from datetime import datetime
import hashlib,json,os,re,shutil,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'PC/protocol'))
import scope_protocol as p

def main(require_iob=False,require_awg=False):
    sys.stdout.reconfigure(encoding='utf-8')
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    report=ROOT/('FPGA/reports/awg' if require_awg else 'FPGA/reports/adc_iob' if require_iob else 'FPGA/reports/saturation')/stamp;report.mkdir(parents=True)
    stage=Path('R:/')/(('awg_' if require_awg else 'adc_iob_' if require_iob else 'saturation_')+stamp);stage.mkdir()
    cache=ROOT/'tmp/fpga_ascii/scope_board_20261026_232708_a50fa07f'
    for directory in ('ip','clock'):
        shutil.copytree(cache/directory,stage/directory)
    for name in ('xsim.ini','ensure_scope_fft_ip.tcl','build.tcl'):
        shutil.copyfile(cache/name,stage/name)
    # Use the current implementation script and constraints.
    shutil.copyfile(ROOT/'FPGA/scripts/build_scope_board.tcl',stage/'build.tcl')
    shutil.copyfile(ROOT/'FPGA/constraints/scope_board_25m.xdc',stage/'scope_board_25m.xdc')
    for directory in ('tool_tmp','tool_appdata','src','vectors'): (stage/directory).mkdir()
    for name in ('ad9767_model.sv','ad9226_model.sv','loopback_channel_model.sv'):
        shutil.copyfile(ROOT/'FPGA/sim/models'/name,stage/name)
    for name in ('tb_scope_board.sv','tb_scope_board_dds.sv','tb_frame_saturation.sv','tb_awg.sv'):
        shutil.copyfile(ROOT/'FPGA/sim/tb'/name,stage/name)
    f=ROOT/'FPGA'
    packages=[f/'rtl/common'/name for name in ('scope_pkg.sv','multires_pkg.sv','protocol_pkg.sv','fft_window_pkg.sv','spectrum_pkg.sv')]
    sources=packages+list((f/'rtl/uart_proto').glob('*.sv'))+list((f/'rtl/measure').glob('*.sv'))+[
        f/'rtl/multires/multires_envelope.sv',f/'rtl/dac_dds/dds_core.sv',f/'rtl/dac_dds/dds_sine_lut.sv',
        f/'rtl/dac_dds/scope_board_dds.sv',*list((f/'rtl/clock_reset').glob('*.sv')),
        f/'rtl/top/scope_core.sv',f/'rtl/top/scope_board_top.sv',f/'rtl/adc_if/adc_capture.sv',
        f/'rtl/capture/bram_capture.sv',f/'rtl/capture/capture_bram.sv',f/'rtl/trigger/trigger_core.sv',f/'rtl/trigger/trigger_edge.sv']
    firmware_build=int(re.search(r"FIRMWARE_BUILD=32'h([0-9a-fA-F]+)",(f/'rtl/top/scope_board_top.sv').read_text())[1],16)
    m={'verdict':'RUNNING','stage':str(stage),'source_sha256':{},'build':f'0x{firmware_build:08X}','iob_required':require_iob,
       'capabilities':63 if require_awg else 31,'baud':921600,'implementation':'NOT_RUN','saturation_simulation':'NOT_RUN'}
    for index,source in enumerate(sources):
        shutil.copyfile(source,stage/'src'/f'{index:03}_{source.name}')
        m['source_sha256'][str(source.relative_to(ROOT))]=hashlib.sha256(source.read_bytes()).hexdigest()
    def save():(report/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    save();print('SATURATION_REPORT='+str(report)+'\nSATURATION_STAGE='+str(stage),flush=True)
    binary=Path(json.loads((f/'scripts/vivado_toolchain.json').read_text())['bin'])
    env=os.environ.copy();env.update(TEMP=str(stage/'tool_tmp'),TMP=str(stage/'tool_tmp'),
        APPDATA=str(stage/'tool_appdata'),XILINX_LOCAL_USER_DATA='NO',SCOPE_UART_BAUD='921600',
        XILINX_TCLAPP_REPO=str(binary.parent/'data/XilinxTclStore'))
    env['SCOPE_REQUIRE_IOB']='1' if require_iob else '0'
    def start(args,label):
        stream=(report/(label+'.log')).open('wb')
        process=subprocess.Popen(' '.join('"'+str(x)+'"' for x in args),cwd=stage,env=env,stdout=stream,stderr=subprocess.STDOUT,shell=True)
        return process,stream,label
    def finish(job,marker=None):
        process,stream,label=job;code=process.wait();stream.close()
        text=(report/(label+'.log')).read_text(encoding='utf-8',errors='replace')
        assert code==0 and not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL|BOARD_BUILD_FAIL)',text),text[-2000:]
        if marker:assert marker in text,(label,marker)
        m[label]='PASS';save();print('SATURATION_STAGE_PASS '+label,flush=True)
    def run(args,label,marker=None):finish(start(args,label),marker)
    impl=start([binary/'vivado.bat','-mode','batch','-notrace','-source','build.tcl','-log','build.log','-journal','build.jou'],'implementation')
    try:
        run([binary/'xvhdl.bat','--relax','ip/scope_fft_1024/sim/scope_fft_1024.vhd'],'fft.vendor')
        compile_sources=[*sorted((stage/'src').glob('*.sv')),*sorted((stage/'clock').glob('*.v')),
            stage/'ad9767_model.sv',stage/'ad9226_model.sv',stage/'loopback_channel_model.sv',
            stage/'tb_scope_board.sv',stage/'tb_scope_board_dds.sv',stage/'tb_frame_saturation.sv',stage/'tb_awg.sv']
        run([binary/'xvlog.bat','--sv',*compile_sources,binary.parent/'data/verilog/src/glbl.v'],'compile')
        if require_awg:
            run([binary/'xelab.bat','work.tb_awg','-s','tb_awg','--timescale','1ns/1ps'],'awg.elaborate')
            run([binary/'xsim.bat','tb_awg','--runall','--onfinish','quit','--onerror','quit'],'awg.simulate','TEST_PASS tb_awg')
        run([binary/'xelab.bat','work.tb_frame_saturation','-s','tb_frame_saturation','--timescale','1ns/1ps'],'counter.elaborate')
        run([binary/'xsim.bat','tb_frame_saturation','--runall','--onfinish','quit','--onerror','quit'],'counter.simulate','TEST_PASS tb_frame_saturation')
        run([binary/'xelab.bat','work.tb_scope_board_dds','-s','tb_scope_board_dds','--timescale','1ns/1ps'],'dds.elaborate')
        run([binary/'xsim.bat','tb_scope_board_dds','--runall','--onfinish','quit','--onerror','quit'],'dds.simulate','TEST_PASS tb_scope_board_dds')
        # Vendor libraries are the same installed 2025.2 versions as the cached IP.
        text=(cache/'export/scope_fft_1024/xsim/scope_fft_1024.sh').read_text()
        line=next(s for s in text.splitlines() if s.startswith('  xelab '))
        libs=[x for lib in re.findall(r'-L (\w+)',line) if lib!='xil_defaultlib' for x in ('-L',lib)]
        run([binary/'xelab.bat','work.tb_scope_board','work.glbl','-s','tb_saturation_board',
            '--generic_top','TEST_BAUD=1152000','--generic_top',f'TEST_BUILD={firmware_build}',*libs,'-L','unisims_ver','-L','secureip','--timescale','1ns/1ps'],'board.elaborate')
        base=[(p.PING,b'BOARD25'),(p.GET_VERSION,b''),(p.GET_STATUS,b''),
            (p.SET_RECORD,struct.pack('<II',32768,500000)),(p.SET_RECORD,struct.pack('<II',16384,500000)),
            (p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',0,0,0,8,-100,100,1,100,100,256)),
            (p.SET_DDS,struct.pack('<BBIIHi',0,1,100000,0,819,0)),(p.SINGLE,b''),(p.GET_STATUS,b''),
            (p.READ_WAVE,struct.pack('<II',0,64)),(p.READ_WAVE,struct.pack('<II',16320,64)),(p.STOP,b'')]
        requests=base+[(p.STOP,b''),(p.GET_CAPABILITIES,b''),
            (p.SET_TRIGGER,struct.pack('<BBhHhhIIHI',6,0,0,8,-100,100,1,100,16383,2))]
        for mode in range(4):requests.extend([(p.SET_DIAGNOSTIC,bytes([mode])),(p.SINGLE,b''),
            (p.READ_SATURATION,b''),(p.READ_SATURATION,b''),(p.READ_MEASURE,b''),(p.READ_SPECTRUM,b''),
            (p.READ_WAVE,struct.pack('<II',8192,128)),(p.STOP,b'')])
        def vectors(folder,requests):
            folder.mkdir(exist_ok=True);lengths=[]
            for seq,(kind,payload) in enumerate(requests):
                wire=p.encode(p.Frame(kind,seq,payload=payload));lengths.append(len(wire))
                (folder/f'cmd_{seq}.hex').write_text(''.join(f'{x:02x}\n' for x in wire))
            (folder/'lengths.txt').write_text('\n'.join(map(str,lengths)))
        vectors(stage/'vectors',requests)
        run([binary/'xsim.bat','tb_saturation_board','--runall','--onfinish','quit','--onerror','quit',
            '--testplusarg',f'VECTOR_DIR={(stage/"vectors").as_posix()}','--testplusarg','SATURATION_TEST'],
            'board.simulate','TEST_PASS tb_scope_board_saturation')
        from audit_saturation import audit
        m.update(audit(stage/'vectors',stage/'ip/scope_fft_1024/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip',expected_build=firmware_build,expected_capabilities=m['capabilities']))
        # Reuse the previous mode-specific vectors with freshly compiled RTL.
        modes=stage/'mode_vectors';shutil.copytree(cache/'capture_modes_vectors',modes)
        run([binary/'xsim.bat','tb_saturation_board','--runall','--onfinish','quit','--onerror','quit',
            '--testplusarg',f'VECTOR_DIR={modes.as_posix()}','--testplusarg','CAPTURE_MODES_TEST'],
            'modes.simulate','TEST_PASS tb_scope_board_capture_modes')
        parser=p.Parser();packets=parser.feed(bytes.fromhex((modes/'uart.hex').read_text()))
        assert len(packets)==20 and not parser.buffer and not any(parser.errors.values())
        assert not any(f.flags&p.ERROR for f in packets)
        finish(impl,'BOARD_BITSTREAM_PASS')
        if require_iob:
            placement=(stage/'artifacts/adc_iob_placement.tsv').read_text()
            assert len(placement.splitlines())==14 and all('ILOGIC' in line for line in placement.splitlines()[1:])
            m['adc_iob_registers_verified']=13
        for rel,digest in m['source_sha256'].items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
        m['verdict']='PASS';save()
    except BaseException as exc:
        m['verdict']='FAIL';m['error']=repr(exc);save()
        if impl[0].poll() is None:
            # Allow implementation to finish and retain evidence independently.
            try:finish(impl,'BOARD_BITSTREAM_PASS')
            except BaseException as implementation_error:m['implementation_error']=repr(implementation_error)
        save();raise
    print('SATURATION_BUILD_PASS '+str(report),flush=True)

if __name__=='__main__':main()
