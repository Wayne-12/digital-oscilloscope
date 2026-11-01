from pathlib import Path
import json,hashlib,re,struct,statistics
root=Path(__file__).resolve().parents[1];reports=root/'reports';hw=reports/'hardware'
def data(path):return json.loads(path.read_text(encoding='utf-8'))
throughput=data(hw/'throughput.json');analysis=data(hw/'analysis/verification.json')
modes=data(hw/'capture_modes/report.json');awg=data(hw/'awg/report.json')
gui=data(hw/'ui_multires/report.json');final=data(hw/'final.json')
timing=(reports/'implementation/timing.rpt').read_text()
match=re.search(r'^\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+\d+\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+\d+\s+([\d.-]+)',timing,re.M)
assert match,'Timing summary not found'
wns,tns,setup,whs,ths,hold,wpws=match.groups()
assert float(wns)>=0 and float(whs)>=0 and int(setup)==int(hold)==0
cdc=(reports/'implementation/cdc.rpt').read_text()
assert 'CDC-1   Critical    845' in cdc and 'CDC-13  Critical     10' in cdc
status=bytes.fromhex(final['before']['status']);counters=struct.unpack_from('<8I',status,12)
assert counters==(0,0,0,0,0,5,0,0),counters
checks={
 'physical_cpu_execution_and_echo':throughput['result']=='PASS',
 'routed_timing':float(wns)>=0 and float(whs)>=0,
 'dds_adc_measurement_fft':analysis['verdict']=='PASS' and analysis['restored'],
 'capture_modes':modes['verdict']=='PASS' and modes['restored'],
 'arbitrary_waveforms':awg['verdict']=='PASS' and awg['restored'],
 'frozen_frame_envelope_roi_ui':gui['result']=='PASS',
 'configuration_restored':final['result']=='PASS',
 'no_unexpected_communication_errors':counters==(0,0,0,0,0,5,0,0),
}
bit=root/'build/scope_cpu_runtime.bit'
wire=statistics.mean(r['wire_bytes_per_second'] for r in gui['transfers'])
result={'result':'PASS_WITH_RETAINED_METHODOLOGY_AND_CDC_FINDINGS' if all(checks.values()) else 'FAIL',
 'checks':checks,'build':'0xA4261028','uart_baud':921600,
 'runtime_bit_sha256':hashlib.sha256(bit.read_bytes()).hexdigest(),
 'firmware_elf_sha256':hashlib.sha256((root/'build/scope_cpu.elf').read_bytes()).hexdigest(),
 'timing_ns':{'setup_wns':float(wns),'hold_whs':float(whs),'pulse_width_wpws':float(wpws)},
 'frame_wire_bytes_per_second_mean':wire,'uart_utilization_mean':wire/92160,
 'echo_duplex_wire_bytes_per_second':throughput['trials'][-1]['wire_aggregate_bytes_per_second'],
 'real_capture_test_frames':len(analysis['frames'])+len(modes['frames'])+len(awg['frames'])+2,
 'cdc_retained':{'CDC-1':845,'CDC-13':10,'source_ports':{'module_switch':852,'reset_n':3}},
 'methodology_retained':{'LUTAR-1':2,'SYNTH-5':112,'SYNTH-6':11,'SYNTH-10':21,'TIMING-18':14,'XDCB-5':1},
 'unexpected_error_counters':[0]*8,'intentional_rejected_commands':5,
 'flash_programming_performed':False,'volatile_fpga_programming_performed':True,
 'current_state':'CPU test image running, acquisition stopped, original record/trigger/DDS/mode restored; unselected diagnostic AWG table remains volatile',
 'limitations':['No zero-CDC signoff','No long-duration soak or power-loss/glitch validation','Measured end-to-end transport throughput, not CPU instruction benchmark or maximum CPU throughput'],
 'initial_no_response_root_cause':'ELF source association was not retained when implementing from a DCP in a new Vivado session. Explicit UpdateMEM to the routed MMI and runtime bitstream restored CPU execution.'}
(reports/'hardware_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
text=f'''# 软核实物验证报告

日期：2026-10-28。结论：CPU 实物执行、当前 25 MHz 设计的布线后 STA、有限功能联调通过；保留方法学/CDC 发现，未作零 CDC 签核。

## 镜像与下载范围

器件 XC7A35T，JTAG 目标 `1234-tulA`，COM12 / 921600 / 8N1，版本 `0xA4261028`。用户明确授权临时下载，不固化。只调用 `program_hw_devices`，没有配置存储器创建、擦除或编程操作。QSPI 原镜像未写入；保持 QSPI 启动模式即可，断电重启将回到原固化镜像。

当前实际运行文件：`build/scope_cpu_runtime.bit`，SHA256 `{result['runtime_bit_sha256']}`。ELF SHA256 `{result['firmware_elf_sha256']}`。

最初从综合 DCP 在新会话生成的 `scope_cpu_test.bit` 未正确携带 C 程序，下载后无串口响应。显式使用 AMD UpdateMEM、真实布线后的 `cpu_memory.mmi`、处理器 `uart/cpu/inst/microblaze_I` 与 C ELF 生成 `scope_cpu_runtime.bit` 后，通信和后续所有物理测试通过。**不得直接下载未嵌入 ELF 的 `scope_cpu_test.bit`。** 原失败报告保留在 `hardware/throughput_before_explicit_elf.json`。

## 实测结果

| 项目 | 结果 |
|---|---|
| 布线后建立时间 WNS | +{float(wns):.3f} ns；TNS=0，0 失败端点 |
| 布线后保持时间 WHS | +{float(whs):.3f} ns；THS=0，0 失败端点 |
| 脉宽 WPWS | +{float(wpws):.3f} ns |
| 时钟与路径覆盖 | 100 MHz 输入 / 25 MHz 工作；check_timing 无缺失时钟、无未约束内部端点 |
| 路由 | 21500/21500 可路由网络完成，0 路由错误 |
| 完整冻结帧连续读取 | 六次逐字节一致，平均 {wire/1000:.2f} kB/s（含协议包头及 CRC），UART 字节上限利用率 {wire/92160*100:.2f}% |
| PING 双向回显 | 534 个随机/边界长度包，最大已测双向合计 {result['echo_duplex_wire_bytes_per_second']/1000:.2f} kB/s；窗口=2 |
| 标准 DDS / ADC / FPGA 测量与 FFT | 正弦、方波、三角、直流，4 帧独立算法核对通过 |
| AUTO / NORMAL / SINGLE | AUTO 不可能门限超时、NORMAL 等待与 STOP、双沿触发重臂、SINGLE 保持/重复、STOP 重启通过；{len(modes['frames'])} 帧 |
| 任意波形 | 1024 点逐字节读回、失败事务不破坏活动表、4 种真实波形形状验证通过；5 个预期非法命令正确拒绝 |
| 包络 / ROI | 100/200/400/800 桶逐桶对完整帧验证；1 点及 2048 点首/中/尾 ROI 与同帧原始码一致 |
| 原 Qt 界面 | Qt offscreen 自动化运行原窗口与实际 SerialWorker 线程，连接 CPU、能力=63、真实 16384 点、显示 100 kHz；已检查截图 |
| 通信错误 | 最终 CRC/长度/版本/超时/未知命令/停止位/RX 溢出均为 0；语义错误恰好等于 5 个刻意拒绝测试 |

吞吐数字为当前 USB-UART、主机、协议引擎和 CPU 的端到端实测，不是纯 CPU 指令性能或处理器最大吞吐。25 MSPS ADC 仍由 RTL 执行，不经 C 逐点采样。最小保持裕量只有 0.009 ns；这是本次实现的报告值，不应把它说成宽裕的保持余量。

## 保留的检查结果

未新增时序例外或 waiver，未修改原项目 RTL/XDC 来消除提示。

- `TIMING-18` 14 项：DAC 数据相对 `adc_external` 的关联时钟提示。真实 DAC 锁存由 `dac_external` 和 `wr_external` 分别使用 max=4 ns、min=-3.5 ns 约束；ADC 输入使用 max=9 ns、min=1.5 ns。`check_timing` 无缺失输入/输出 delay。没有虚构 DAC 对 ADC 时钟的外部负载时序来压掉警告。约束依赖原工程的短线/偏斜假设，未用外部仪器重测。
- `LUTAR-1` 两项及 CDC Critical：CDC-1=845、CDC-13=10；已逐行分组，852 项从 `module_switch` 出发，3 项从 `reset_n` 出发，全部标记 False Path。这些来自原有异步撤销/安全控制；新增 CPU 与 UART/邮箱同为 25 MHz 域，但复用原异步使能链，因此增加了扇出。不是无风险声明，未验证所有开关毛刺/上电跌落情况，不能签为零 CDC。
- RAMB 异步控制检查 `REQP-1839/1840`：异步断言、同步释放的复位影响 RAM 地址/使能。读取中断帧在复位后无效，后续需完整重写；仍保留警告。默认 DRC 报告这两类各显示 20 项并提示规则上限，不把显示数量当实际总数。没有 Error 或 Critical Warning 级 DRC 阻塞项。
- `SYNTH-5` 112 项、`SYNTH-6` 11 项、`SYNTH-10` 21 项与 DSP 流水建议属于映射/性能提示；当前 25 MHz STA 通过，不等于这些建议已修复。`XDCB-5` 1 项为约束查询效率提示。

根因核对引用的实际源：`integration/rtl/top/scope_board_top.sv`、`integration/rtl/top/scope_core.sv`、`integration/rtl/clock_reset/scope_reset_sync.sv`、`integration/scope_board_25m.xdc`。未修改这些原有安全结构。

## 恢复与边界

最终记录、触发、DDS、采集模式逐字节读回，与临时下载前基线一致；采集已 STOP，标准 DDS 仍按原配置运行。任意波形测试生成的表仍在易失 RAM 内，但未选作输出；原固件没有清表命令，复位/断电会清除。未执行长期稳定性试验。当前保留 CPU 临时镜像，未自动切回旧镜像，以便用户继续查看。

## 证据入口

- `hardware_validation.json`：汇总与哈希。
- `implementation/`：真实布线后时序、路由、DRC、CDC、方法学及 MMI。
- `hardware/throughput.json`、`hardware/analysis/verification.json`、`hardware/capture_modes/report.json`、`hardware/awg/report.json`、`hardware/ui_multires/report.json`：各项原始验收结果。
- `hardware/ui_multires/cpu_hardware_ui.png`：原界面真实采样截图。
- `hardware/final.json`：最终配置恢复核对。

复现顺序：离线固件/IP/综合 → `implement_system.tcl` → `embed_firmware.tcl` → 明确授权后 `program_test.tcl` → SW0 OFF→ON → 物理测试。后两项不是原离线验证默认动作。
'''
(reports/'实物验证报告.md').write_text(text,encoding='utf-8')
(root/'METHODOLOGY_RESOLUTION_REPORT.md').write_text('# 软核时序与方法学检查\n\n见 [实物验证报告](reports/实物验证报告.md) 的“保留的检查结果”。本次未更改约束、未创建 waiver；STA 通过，CDC 未完全签核。\n',encoding='utf-8')
(reports/'methodology_agent.log').write_text('TIMING-18: inspected real ADC/DAC XDC and routed check_timing. Confidence high: DAC has actual ACLK/WR1 requirements; no invented ADC-relative DAC delay added.\nCDC/LUTAR: inspected original safety RTL and all 855 critical rows; all from physical asynchronous controls; no automatic waiver. Confidence high for source classification, no claim of complete CDC safety.\nREQP: inspected RAM async-reset warnings and reset synchronizers. Confidence medium on complete reset transient behavior; retained without waiver.\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
assert all(checks.values()),checks
