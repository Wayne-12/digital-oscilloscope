"""Package a passing offline build. Never connects to or programs hardware."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'FPGA/scripts'))
from audit_board_analysis import audit

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('report',type=Path)
    cli.add_argument('--output',type=Path,required=True)
    a=cli.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    report=a.report.resolve()
    m=json.loads((report/'manifest.json').read_text(encoding='utf-8'))
    for key in ('verdict','simulation','boot_preset_simulation','multires_simulation',
                'analysis_simulation','implementation'):
        assert m.get(key)=='PASS',(key,m.get(key))
    # Re-audit from copied, completed UART evidence using the final independent
    # oracle, including exact period and duty as well as FFT/harmonic amplitude.
    analysis=audit(report/'analysis_vectors_and_traces')
    for rel,digest in m['source_sha256'].items():assert sha(ROOT/rel)==digest,rel
    for label,marker in [('simulate','TEST_PASS tb_scope_board '),
                         ('boot.simulate','TEST_PASS tb_scope_board_boot '),
                         ('multires.simulate','TEST_PASS tb_scope_board_multires '),
                         ('analysis.simulate','TEST_PASS tb_scope_board_analysis '),
                         ('implementation','BOARD_BITSTREAM_PASS')]:
        body=(report/(label+'.log')).read_text(encoding='utf-8',errors='replace')
        assert marker in body and not re.search(r'(?m)^\s*(ERROR:|Fatal:|TEST_FAIL|BOARD_BUILD_FAIL)',body)
    timing=(report/'artifacts/timing.rpt').read_text(encoding='utf-8')
    row=re.search(r'^\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)',timing,re.M)
    assert row and 'All user specified timing constraints are met.' in timing
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    bit=output/'scope_analysis_1024_25m.bit'
    shutil.copyfile(report/'artifacts/scope_board_25m.bit',bit)
    shutil.copytree(report/'artifacts',output/'implementation')
    extras=['FPGA/constraints/scope_board_25m.xdc','FPGA/scripts/build_scope_board.py',
            'FPGA/scripts/build_scope_board.tcl','FPGA/scripts/ensure_scope_fft_ip.tcl',
            'FPGA/scripts/prepare_fft_development.tcl','FPGA/scripts/resume_board_analysis.py',
            'FPGA/scripts/verify_board_analysis_hardware.py','FPGA/scripts/audit_board_analysis.py',
            'FPGA/scripts/audit_board_multires.py','FPGA/scripts/vivado_toolchain.json',
            'FPGA/scripts/generate_measure_vectors.py',
            'FPGA/scripts/finalize_board_analysis.py','FPGA/scripts/package_board_analysis.py',
            'FPGA/sim/models/ad9226_model.sv','FPGA/sim/models/ad9767_model.sv',
            'FPGA/sim/models/loopback_channel_model.sv','FPGA/sim/tb/tb_scope_board.sv',
            'FPGA/sim/tb/tb_scope_board_dds.sv','PC/ui/requirements.txt','PC/ui/launch_scope.py',
            'FPGA/scripts/program_scope_board.tcl','PC/protocol/scope_protocol.py',
            'PC/protocol/hardware_calibration.py','PC/protocol/spectrum_reference.py',
            'PC/protocol/protocol_spec.md','示波器显示界面.py']
    copied={}
    for rel in list(m['source_sha256'])+extras:
        source=ROOT/rel;dest=output/'source'/rel
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        copied[rel]=sha(source)
    stage=Path(m['stage'])
    for rel in ['clock/scope_clk_wiz.v','clock/scope_clk_wiz_clk_wiz.v',
                'ip/scope_fft_1024/scope_fft_1024.xci','ip/fft_contract_readback.txt']:
        source=stage/rel;dest=output/'build_inputs'/rel
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        copied['build_inputs/'+rel]=sha(source)
        if rel.startswith('clock/'):
            hdl=output/'source/FPGA/ip/scope_clk_wiz'/source.name
            hdl.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,hdl)
            copied['FPGA/ip/scope_clk_wiz/'+source.name]=sha(source)
    original_elaboration=Path(m.get('capture_source_report',m['source_report']))/'elaborate.log'
    original_baud=re.search(r'--generic_top TEST_BAUD=(\d+)',original_elaboration.read_text(encoding='utf-8',errors='replace'))
    release={'format':'scope-frozen-analysis-release-v1','offline_verdict':'PASS',
             'hardware_verified':False,'flash_programmed':False,'part':m['part'],
             'build_id':'0xA0261026','capabilities':7,'sample_rate':25000000,'record_length':16384,
             'fft_points':1024,'fpga_fft_window':'periodic Hann','harmonic_orders':[2,3,4,5],
             'uart_baud':m['baud'],'report':str(report),
             'multires_analysis_simulation_baud':m['simulation_baud'],
             'reused_capture_simulation_baud':int(original_baud[1]) if original_baud else None,
             'setup_wns_ns':float(row[1]),'hold_whs_ns':float(row[2]),'pulse_width_slack_ns':float(row[3]),
             'bitstream':bit.name,'bitstream_sha256':sha(bit),'source_sha256':copied,
             'analysis_reaudit':analysis,'analysis_oracle_sha256':sha(ROOT/'FPGA/scripts/audit_board_analysis.py')}
    (output/'release_manifest.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'README.md').write_text('''# FPGA 基础测量与 1024 点 FFT 固件

本发布包完成离线仿真、综合、布局布线和文件哈希核对。实物验收及 Flash 固化尚未执行。请使用工程中已更新的示波器界面；旧界面可能拒绝新增能力位。

固件参数为 25 MSPS、16384点BRAM、921600 bit/s，版本0xA0261026、能力flags=7。FPGA计算冻结整帧基础测量，并对前1024点计算周期Hann FFT，返回主峰和第2～5次谐波峰值幅度。PC曲线来自当前原始窗口，摘要与波形通过时间戳、采样率及触发索引绑定。

2048点FFT和复杂频谱指标已移出当前功能范围。原始ROI仍可读取最多2048点。FFT间隔约24.414kHz，低频精细测频使用时域整帧结果。主峰为幅度最大的交流谱峰，谐波幅度为整数倍主峰附近±1bin峰值，不等同于失真指标。

## 实物验收准备

用户连接实物后再进行JTAG加载。沿用已确认的DAC→ADC闭环接线与供电顺序；加载前SW0置OFF，加载成功后按提示完成OFF→ON。这里没有自动加载、改写Flash或自动恢复RUN。

实物验收入口为工程根目录下 `FPGA/scripts/verify_board_analysis_hardware.py --port 实际串口 --baud 921600`，使用现有Python环境运行。该脚本仅适用于新固件；会以不超过既定10% DDS幅度采集四种波形，保存原始帧并核对摘要，最后逐字节核对配置恢复。若端口被界面占用，先正常断开界面连接。

`implementation/` 保留本次时序、资源、CDC和方法学报告。约束时序通过不等于零CDC告警或实物电气验收；原有安全控制相关CDC关键项及方法学建议的解释见实现复核。原始Flash和先前固件未被修改。

`source/` 是本次代码快照，`build_inputs/` 保存实际时钟HDL和FFT配置；完整复现入口与校验值见 release_manifest.json 指向的验证目录。普通/上电捕获复用了逐字节源码匹配且重新核对ADC证据的既有通过记录；本次重新执行了多分辨率和摘要双帧测试。
''',encoding='utf-8')
    print('RELEASE_PACKAGE_PASS '+str(output))

if __name__=='__main__':main()
