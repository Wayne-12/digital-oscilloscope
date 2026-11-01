from pathlib import Path
import hashlib,json,re,struct,statistics
r=Path(__file__).resolve().parents[1];out=r/'reports/cdc_repair';hw=out/'hardware'
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def cdc_counts(path):
 t=path.read_text();return {name:{'severity':severity,'count':int(count)} for name,severity,count in
 re.findall(r'^\s*(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+',t,re.M)}
before=cdc_counts(out/'before/implementation/cdc.rpt');after=cdc_counts(r/'reports/implementation/cdc.rpt')
critical=lambda counts:sum(v['count'] for v in counts.values() if v['severity']=='Critical')
assert critical(before)==855 and critical(after)==0
sim=(out/'safety_simulation_pass.txt').read_text()
assert 'CDC_SAFETY_TEST_PASS cases=23' in sim
t=(r/'reports/implementation/timing.rpt').read_text()
m=re.search(r'^\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+\d+\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+\d+\s+([\d.-]+)',t,re.M)
assert m
wns,tns,setup,whs,ths,hold,wpws=m.groups()
assert float(wns)>=0 and float(whs)>=0 and int(setup)==int(hold)==0
echo=load(hw/'throughput.json');analysis=load(hw/'analysis/verification.json')
modes=load(hw/'capture_modes/report.json');awg=load(hw/'awg/report.json')
ui=load(hw/'ui_multires/report.json');final=load(hw/'final.json')
checks={'cdc_critical_removed':critical(after)==0,'asynchronous_safety_simulation':True,
 'routed_timing':True,'physical_cpu_execution_and_echo':echo['result']=='PASS',
 'dds_adc_measurement_fft':analysis['verdict']=='PASS' and analysis['restored'],
 'capture_modes':modes['verdict']=='PASS' and modes['restored'],
 'arbitrary_waveforms':awg['verdict']=='PASS' and awg['restored'],
 'frozen_frame_envelope_roi_ui':ui['result']=='PASS',
 'configuration_restored':final['result']=='PASS'}
counters=struct.unpack_from('<8I',bytes.fromhex(final['before']['status']),12)
checks['no_unexpected_communication_errors']=counters==(0,0,0,0,0,5,0,0)
wire=statistics.mean(row['wire_bytes_per_second'] for row in ui['transfers'])
result={'result':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
 'build':'0xA4261028','revision':'cdc_repair_1','cdc_before':before,'cdc_after':after,
 'timing_ns':{'setup_wns':float(wns),'hold_whs':float(whs),'pulse_width_wpws':float(wpws)},
 'frame_wire_bytes_per_second_mean':wire,'uart_utilization_mean':wire/92160,
 'echo_duplex_wire_bytes_per_second':echo['trials'][-1]['wire_aggregate_bytes_per_second'],
 'runtime_bit_sha256':sha(r/'build/scope_cpu_runtime.bit'),
 'firmware_elf_sha256':sha(r/'build/scope_cpu.elf'),
 'rtl_overlay_hashes':{str(p.relative_to(r)):sha(p) for p in [r/'rtl/scope_core.sv',r/'rtl/scope_cpu_board_top.sv']},
 'volatile_fpga_programming_performed':True,'flash_programming_performed':False,
 'new_timing_exceptions_or_waivers':False,
 'limitations':['No long-duration soak or external power-loss/glitch validation',
  'Digital simulation does not measure analog metastability or establish product safety certification',
  'Other LUTAR, RAM async-control and performance methodology warnings remain'],
 'report':'reports/cdc_repair/修复报告.md'}
assert all(checks.values()),checks
(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(r/'reports/hardware_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
md=f'''# 复位/使能 CDC 修复报告

结论：本次目标 CDC Critical 路径从 **855 条降为 0 条**。修复版通过异步切换专项仿真、完整布局布线与真实 CPU/ADC/DAC/原 UI 回归。仅临时 JTAG 下载，**未固化 QSPI**。

## 修改方法

修复使用 `rtl/scope_core.sv` 与 `rtl/scope_cpu_board_top.sv` 覆盖层，构建脚本显式选用它们。原 FPGA 项目、50 个原始 RTL 和原约束均未修改。

- 保留捕获短 OFF 脉冲的异步安全资格器，其输出再通过两级本地上升沿采样，供内部状态机使用；采集使能改为上升沿寄存器输出。原始 SW0 不再直接组合控制大量内部寄存器的 D/CE。
- 保留异步断言、两级同步释放的安全复位以及引脚紧急高阻关断，去掉 raw reset/MMCM 状态重复绕过同步结构进入 OE/ODDR R 的旁路。
- 停机顺序仍为停止采集→关闭 ADC 时钟→关闭 DAC 时钟→释放数据；启动仍完整执行 DAC 16 拍中码和 ADC 256 拍预热。内部增加有界同步延迟，不再承诺原始 SW0 直接零周期截断所有内部 CE。
- 没有新增 false path、降低检查严重度或创建 waiver。

## 证据

| 检查 | 修复前 | 修复后 |
|---|---|---|
| CDC-1 Critical | 845 | 0 |
| CDC-13 Critical | 10 | 0 |
| CDC-3 / CDC-9 | 同步结构 Info | 2 / 3 条 Info，全部识别为同步结构 |
| 异步切换自检 | 首个 3 ns OFF 脉冲在 11421 ns 触发 `ASYNC_INTERNAL_CAPTURE_ENABLE`；此前完成短脉冲用例 0 个 | 23 个场景全部通过 |
| 布线后建立 WNS | +10.111 ns | +{float(wns):.3f} ns |
| 布线后保持 WHS | +0.009 ns | +{float(whs):.3f} ns |
| 未约束内部端点 / 负裕量端点 | 0 / 0 | 0 / 0 |
| DRC Error/Critical Warning | 无阻塞项 | 无阻塞项 |

23 个场景包含 20 个相位上的亚周期 OFF 脉冲、长 OFF、失锁并停止时钟、短复位，以及每次恢复后的完整预热；使用 AMD ODDR/OBUFT/glbl 模型，失锁且时钟完全停止时仍检查输出为高阻。数字仿真证明的是事件与顺序，不是模拟亚稳态概率的直接测量。

实物回归：534 个 PING 包、四类标准 DDS 的 ADC 测量/FFT、AUTO/NORMAL/SINGLE/STOP、1024 点 AWG 下载/全表读回/错误拒绝及四类闭环波形、四档包络与首中尾 ROI、原 Qt 界面实际串口线程连接和真实波形显示均通过。完整冻结帧平均传输 **{wire/1000:.2f} kB/s**，线路利用率 **{wire/92160*100:.2f}%**。最终通信错误均为 0，语义错误恰好对应 5 个故意非法命令；配置已恢复，采集已 STOP。AWG 测试表保留在未选中的易失 RAM，复位会清除。

## 当前运行镜像

`build/scope_cpu_runtime.bit`，SHA256：`{result['runtime_bit_sha256']}`。

C 固件与协议 build ID 仍为 `0xA4261028`，本次为 RTL 的 `cdc_repair_1` 修订，**请用镜像 SHA256 区分修复前后**。UpdateMEM 已显式嵌入 C ELF，未直接下载中间 `scope_cpu_test.bit`。

原 QSPI 镜像保持不变；因此断电重启会回到原固化版本，不能认为原 QSPI 的 CDC 结构也已经修复。

## 仍保留的其他提示

方法学中的 LUTAR-1 安全异步复位组合逻辑、RAM 异步控制、映射/DSP 性能建议和 DAC 相对 ADC 时钟的 TIMING-18 提示仍保留，未伪造约束消除。CDC Critical=0 不等于消除所有方法学提示，也不等于完成产品安全认证。未做任意电源跌落/外部毛刺测量或长期稳定性试验。

## 文件

- `before/`：原报告、原实物结果和首个失败仿真日志。
- `safety_simulation_pass.txt`：同合同修复后 PASS。
- `after_synth_cdc.rpt`：综合后 CDC。
- `../implementation/cdc.rpt`、`timing.rpt`、`drc.rpt`：布线后证据。
- `hardware/`：本次修复镜像的独立实物回归原始结果与界面截图。
- `verification.json`：汇总、源文件哈希及镜像哈希。
- `repair_plan.md`：根因与验证合同。
'''
(out/'修复报告.md').write_text(md,encoding='utf-8')
(r/'METHODOLOGY_RESOLUTION_REPORT.md').write_text('# CDC 修复结果\n\n[完整报告](reports/cdc_repair/修复报告.md)。CDC-1=845→0、CDC-13=10→0；无新 waiver 或时序例外。其他非 CDC 方法学提示保留。\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
