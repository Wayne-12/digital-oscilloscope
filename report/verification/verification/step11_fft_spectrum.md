# 第十一步：FFT 与频谱测量

本步沿用 Vivado 2025.2、临时器件 `xc7a35tcsg324-1`，不选开发板、不添加最终管脚约束。使用 `vivado-simulate-rtl` 工作流。已安装的 `vivado-ip-configurator` 要求 2026.1，因此没有运行它的辅助程序；IP 参数由本机 2025.2 的目录和原生 Tcl API 配置、逐项回读。

## 文件与职责

| 文件 | 职责 |
|---|---|
| `PC/protocol/spectrum_reference.py` | 不依赖厂商 FFT 的直接 DFT、加窗、幅度与功率黄金模型 |
| `FPGA/scripts/generate_spectrum_vectors.py` | 可更换种子的离线输入及逐 bin 期望值 |
| `FPGA/rtl/measure/fft_ip_wrapper.sv` | 独立 FFT IP 包装、配置、帧边界、复位、反压 |
| `FPGA/rtl/measure/spectrum_analyzer.sv` | 输入加窗、全谱输出、主峰、幅度、频率与元数据 |
| `FPGA/rtl/measure/spectrum_isqrt.sv` | 64 位整数开方，32 周期，最近整数舍入 |
| `FPGA/rtl/measure/fft_hann_lut.sv` | 1024 点周期 Hann 的无符号 17 位 Q0.16 系数 |
| `FPGA/ip/scope_fft_1024/scope_fft_1024.xci` | 2025.2 生成的实际 Xilinx FFT 9.1 revision 15 |
| `FPGA/scripts/ensure_scope_fft_ip.tcl` | 可重建的唯一 IP 配置及精确参数回读 |

直接 DFT 结果在首次运行 IP 仿真之前生成，容差也在此时固定：复数分量每项最多 128 个 FFT 整数单位；主峰幅度和主音 RMS 最多 8192 Q16 单位，即 0.125 个 ADC 码。禁止根据观察到的失败任意放宽容差。

## 固定接口约定

全部自写 RTL/TB 使用 SystemVerilog、`timeunit 1ns; timeprecision 1ps;`。功能寄存器同步复位。测试时钟由 TB 产生，核心内无组合逻辑生成的时钟。

FFT 固定 1024 点，单通道、Radix-2 Burst I/O、nonrealtime、自然顺序输出；2048 点仅保留为后续扩展，当前不能配置。实虚输入各 16 位，旋转因子 24 位，内部 convergent rounding，**不缩放**。输出有效宽度 27 位，分别符号扩展至 32 位 AXI lane。AXI 数据低半为实部，高半为虚部；XK_INDEX 占 TUSER 的低 10 位，其余为零。

13 位有符号输入 `x` 左移 3 位进入 FFT，可理解为 Q1.15 的 `x/4096`；输出二进制小数点保持不变，即 Q12.15。对原始 ADC 码进行反相转换仍使用已有的 `2047-raw`，不在此处改变编码或覆盖原始数据。

包装层以 `start/start_ready` 启动一帧，配置字 bit0 为 FWD_INV：正变换 1、反变换 0。配置握手后额外等待 4 拍才接收数据。输入必须恰好 1024 次 `valid && ready`，仅最后一个样本置 TLAST。输出 bin 为 0…1023，TLAST 也仅在 bin1023。反变换不除以 N。无缩放计划、无块浮点指数，不能把输出误当作已除以 N。

厂商数据格式与逆变换约定参考 [AMD FFT PG109](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/xfft/v9_1/pg109-xfft.pdf)。实际可用属性、端口及 IP revision 以本机 2025.2 生成文件和 `fft_contract_readback.txt` 为准。

输入及所有输出采用 valid/ready。元数据必须先被接收，才释放 bin 输出。输出或结果被反压时保持稳定。`result_valid` 握手结束才允许新任务。一次任务中配置锁存，不读取正在改变的下一帧配置。

`module_enable=0` 或复位取消当前帧，清空输出 valid，重新保持 FFT 同步低有效复位至少 4 拍后才允许重启；中断的帧不会产生伪有效结果。零采样率、原帧起点大于 130048 均拒绝启动，输出 `config_error`。

## 加窗、幅度与功率

矩形窗系数为 65536。周期 Hann 使用 `round_away(65536*(0.5-0.5*cos(2*pi*i/N)))`，17 位保留值 65536。乘法显式使用有符号 34 位；除以 65536 时最近舍入、半值远离零，检查结果落在 signed16 范围后截取。

Hann 的系数和为 33554432，相干增益 CG=0.5；平方和为 1649267045280。矩形窗 CG=1。功率修正使用 `U=sum(w²)/(65536²*N)`，不能把 U 与 CG² 混用。

设 `Z[k]` 为 IP 输出的整数复数值，`P=Re²+Im²`。每个 27 位分量平方显式扩展为 54 位，相加为 64 位输出；不会以 32 位表达式截断平方结果。

对实数输入，`|x16|<=32768`、N=1024，精确变换的 `|Z|<=2^25`、P<=2^50；计入已固定的整数误差容差后仍小于 2^51。最大左移 10 位小于 2^61，64 位开方输入有余量。RTL 另用断言检查移位前上位和开方后的第 33 位，所有满幅场景都参与实际 IP 比较。

- 普通正频率 bin 的峰值码幅度：`A=2*sqrt(P)/(8*N*CG)`。
- DC 与 Nyquist 不加倍，使用 `sqrt(P)/(8*N*CG)`。
- 单边功率：`P/(64*N²*U)`，仅普通正频率 bin 再乘 2。软件黄金模型提供完整换算函数，并以 Parseval 检验能量。
- RTL 主音 `amplitude_q16`：矩形窗 `round(sqrt(P<<8))`，Hann `round(sqrt(P<<10))`。
- RTL 主音 `rms_q16`：矩形窗 `round(sqrt(P<<7))`，Hann `round(sqrt(P<<9))`。这是**主音** RMS，整帧时域 RMS 沿用第七步测量模块。
- 频率：最近整数 Hz，`(peak_bin*sample_rate+512)>>10`。没有做亚 bin 插值。
- `dc_mean_q16`：矩形窗 `Re(Z[0])*8`，Hann `Re(Z[0])*16`；Hann 下表示按窗权归一的 DC 估计，不等同于任意非相干输入的未加窗算术平均。

这里的 sample_rate 是原始采样率，不能替换为 100 MHz FFT 处理时钟，也不受冻结帧读取时插入的等待周期影响。

每帧输出全部 1024 个 bin。主 AC 搜索排除 DC、Nyquist：矩形窗搜索 1…511；Hann 还排除其相邻 bin，搜索 2…510，避免纯 DC/Nyquist 的窗扩散被误报为主 AC。边界频段仍可在全谱中读取。相同功率取较小 bin。

只有峰值功率非零且峰值幅度达到配置门限，才置 `measurement_valid`。回归门限为 2 个 ADC 码；无效时主频、主峰 bin、主音幅度及 RMS 都明确清零。OTR 累积为本帧 `clipped` 标志，保留报告，不擅自改变样本或频率。

## 与前序步骤的连接

`tb_spectrum_capture` 直接复用第九步的真实 BRAM 后端 `uart_capture_backend` 和第十步 `multires_envelope`，不以数组假替存储器。冻结 16384 点，触发索引 8192，输出 800 个包络桶，并把原帧 7680…8703 的 1024 点 ROI 送入 FFT，分别验证矩形窗与 Hann。

scoreboard 同时检查 ROI 原始索引、反相有符号码、OTR、跨 64 位回绕的时间戳、FFT 逐 bin 数据及最终结果。ROI 内触发索引为 512。包络处理和 FFT 结果先后完成各自记录，避免要求两个 done 同拍而死锁。

这属于模块和真实存储链路的增量集成；最终板级顶层、UART 频谱包定义、共享读口仲裁和硬件时序收敛仍由后续整机集成完成。

## 回归与重建

在 PowerShell 7 中运行：

```powershell
& 'D:\示波器\FPGA\scripts\run_spectrum_tb.ps1' -PythonExe 'D:\Python\python3.14\python3.14.7\python.exe' -Project
& 'D:\示波器\FPGA\scripts\run_spectrum_synthesis.ps1'
```

种子默认 20261020、42，可通过 `-Seeds` 替换。脚本在 ASCII 临时目录中从零编译；项目验证先验证目录边界和无重解析点，再删除准确的 `scope_smoke.sim`，运行全部五个新 TB。Design Sources 保持纯 RTL/IP，模型与 TB 只参与仿真。项目最终仿真顶层为 `tb_spectrum`，设计顶层仍为已有的安全硬件包装 `scope_hw_top`。

每个种子覆盖 42 个独立频谱输入、5 个原始复数 FFT 输入、2 个真实 BRAM ROI 任务；此外覆盖 7 个阶段撤销使能、7 个阶段复位及每次恢复、2 个非法配置、291 个 64 位整数开方向量。故意破坏 TLAST 和时间戳的独立负例必须触发指定断言。

基础精度使用 k=7、37、113、311、499 等相干单音，检查 k*fs/1024；包括 25/50/65 MSPS，不以 1 kHz、10 kHz 验收 1024 点 FFT 主频。另测双音、方波奇偶谐波、非相干泄漏、加窗、噪声、随机满幅、正负满幅 DC、Nyquist、静音和低于门限输入。

正式结果、最大误差、资源、重复运行与原生项目一致性、未改动前序源码、源码压缩包及 SHA256 校验由同目录报告中的 `acceptance.json` 冻结。预期负例错误与真正回归失败分别记录。

本次报告目录为 `FPGA/reports/spectrum/20261022_132343_c1e2f042`，综合报告为 `FPGA/reports/spectrum_synthesis/20261022_132501_a7e2b552`。双种子合计 88 个频谱帧、10 个复数原始帧，核对 100352 个复数 bin、4096 个真实 BRAM ROI 点，零非预期错误。最大分量误差 51 个 FFT 整数单位；最大主音幅度误差 293 Q16（约 0.004471 个 ADC 码），最大主音 RMS 误差 207 Q16。远端泄漏的 Hann/矩形窗功率比约 0.0041504。

原生工程从删除仿真目录开始通过五个 TB，六份 CSV 与独立仿真、固定种子重跑完全一致。实际综合为零锁存器、零黑盒；原语计数 2501 LUT、2415 FF、19 DSP、6 RAMB18；利用率报告的 Slice LUT 为 2161，BRAM Tile 为 3，二者与原语计数口径不同。

全部仿真和审核通过后，回归脚本在最后保存 JSON 时遇到 PowerShell 整数 Hashtable 键序列化问题。修复仅将阶段路径字典改为 seed/path 对象数组；原执行脚本完整保存在报告中。恢复程序重新检查全部 PASS 日志、24 份暂存 HDL 与现行源码的逐字节一致性、原始及暂存向量，并重新执行四组 CSV 审核，结果完全一致，再生成汇总。没有修改 RTL 或测试数据，也没有将失败测试改为通过；该恢复过程记录在验收 JSON 中。今后正常重跑直接使用已修复脚本，无需恢复程序。

## 工具提示与验证边界

保留厂商 FFT 生成 VHDL 的 VRFC 10-9145 命名空间提示；它不是自写 RTL 的符号扩展或隐式网络警告。综合保留厂商 IP 参数依赖提示、ROM 地址寄存器打包提示，以及本模块的常数输出、高位裁剪、仅仿真使用的逐样本时间戳端口提示。不得把这些提示改写成“全部零警告”。厂商 ROM/系数的初始化不替代本模块控制寄存器的复位；复位恢复均由实际 IP 仿真验证。

综合使用实际 FFT DCP，验收要求零锁存器、零黑盒，并记录完整资源；不等同于布局布线后的 100 MHz 时序签核。尚未建立最终引脚约束，也未声称模拟模拟前端或板上测量精度。
