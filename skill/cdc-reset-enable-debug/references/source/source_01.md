# 复位/使能 CDC 修复报告

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
| 布线后建立 WNS | +10.111 ns | +10.578 ns |
| 布线后保持 WHS | +0.009 ns | +0.028 ns |
| 未约束内部端点 / 负裕量端点 | 0 / 0 | 0 / 0 |
| DRC Error/Critical Warning | 无阻塞项 | 无阻塞项 |

23 个场景包含 20 个相位上的亚周期 OFF 脉冲、长 OFF、失锁并停止时钟、短复位，以及每次恢复后的完整预热；使用 AMD ODDR/OBUFT/glbl 模型，失锁且时钟完全停止时仍检查输出为高阻。数字仿真证明的是事件与顺序，不是模拟亚稳态概率的直接测量。

实物回归：534 个 PING 包、四类标准 DDS 的 ADC 测量/FFT、AUTO/NORMAL/SINGLE/STOP、1024 点 AWG 下载/全表读回/错误拒绝及四类闭环波形、四档包络与首中尾 ROI、原 Qt 界面实际串口线程连接和真实波形显示均通过。完整冻结帧平均传输 **88.29 kB/s**，线路利用率 **95.80%**。最终通信错误均为 0，语义错误恰好对应 5 个故意非法命令；配置已恢复，采集已 STOP。AWG 测试表保留在未选中的易失 RAM，复位会清除。

## 当前运行镜像

`build/scope_cpu_runtime.bit`，SHA256：`5577ad2c6f9c8cbec9a5d2bce5fcd138d8e3a1370eb447731b31d1c06d8bdd60`。

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
