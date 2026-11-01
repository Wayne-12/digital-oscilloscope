# 第十步：多分辨率 min/max 包络与触发 ROI

冻结帧后处理使用 18 位记录索引、16 位原始采样字和 BRAM 读接口；包络保留真实极值及位置，ROI 保留原始码、OTR 和时间戳。

## 分桶与位宽合同

合法帧长 N 为 1～16384，请求桶数 C 为 1～800。有效桶数 B=min(N,C)。第 i 桶使用闭区间：

```text
first(i) = floor(i*N/B)
last(i)  = floor((i+1)*N/B)-1
```

第一个桶从 0 开始，相邻桶首尾连续，最后一个桶结束于 N-1。所有原始样本各进入一桶，桶长之差最多为 1。min/max 的比较量是 signed13 的 `2047-raw_code`，范围 -2048～2047；相等极值保留最早出现的帧索引。每桶额外输出样本计数、极值索引和所有 OTR 的逻辑或。

实现只在每帧开始调用已有 `measure_udiv` 一次，计算 N=q*B+r；随后用余数累加进位生成精确的 floor 边界，无逐桶除法、无乘法分桶和整帧复制。N、索引、桶端点和样本计数均为 18 位；B、r、余数累加器为 10 位，进位和为 11 位。时间戳为 64 位自然回绕，所有算术扩展及 signed 比较显式写出。

## ROI 合同

请求 ROI 长度为 512～2048，也可用 0 显式关闭。短帧使用 R=min(N,requested_roi)。触发索引 T 必须满足 0<=T<N；非空 ROI 按以下方式放置：

```text
start = min(max(T-floor(R/2),0),N-R)
count = R
trigger_in_roi = T-start
```

靠近帧首尾时整体移动窗口，保持有效长度，不读越界。ROI 每点带 roi_index、frame_index、完整 raw_word、signed_sample，以及 `first_timestamp+frame_index` 的 64 位时间戳。触发点可由 `roi_start+roi_trigger_index` 精确还原为原始帧索引。奇数 ROI 长度使用 floor(R/2) 放置触发点。

## 文件与接口

| 文件 | 作用 |
|---|---|
| `FPGA/rtl/common/multires_pkg.sv` | 元数据、桶和 ROI 结构及独立的 18 位帧索引 |
| `FPGA/rtl/multires/multires_envelope.sv` | 单时钟冻结帧扫描、整数边界、极值累计和双输出流 |
| `PC/protocol/envelope_reference.py` | Python 整数 floor/slice 黄金模型 |
| `PC/tests/test_envelope_reference.py` | 分桶、短帧、ROI、非法配置及正负尖峰的独立模型测试 |
| `FPGA/sim/tb/tb_multires.sv` | 随机延迟读源、独立背压、逐样本 scoreboard 和控制恢复 |
| `FPGA/sim/tb/tb_multires_capture.sv` | BRAM 冻结帧集成测试 |
| `FPGA/sim/tb/tb_multires_fault.sv` | 三项预期失败断言测试 |
| `FPGA/scripts/generate_multires_vectors.py` / `audit_multires_traces.py` | 生成刺激与黄金结果，独立审计实际 CSV 及索引覆盖 |

新增 RTL 和 testbench 均为 SystemVerilog、`1ns/1ps`、`default_nettype none`。功能寄存器同步高有效复位，不依赖仿真初值。所有内部顺序逻辑只使用输入系统时钟；没有组合逻辑产生的内部时钟。

start 只在 start_ready=1 时接受，立即锁存全部配置。先用 metadata valid/ready 输出一次元数据，再顺序读取每个逻辑样本；最多一个读请求在途，读响应最早在请求握手后的下一个时钟采入。源帧须由调用方保持冻结至 done，取消时须等待在途读排空。

bucket 和 ROI 使用独立 valid/ready；任一输出阻塞都会暂停后续读取，数据保持稳定。两条流属于同一帧元数据，不跨帧交错；done 只在最后的包络和 ROI 均被接收后产生。输出为内部结构化流，UART 包装在后续系统集成时连接。

module_enable 撤销会同步丢弃未完成帧，产生 cancelled；若已有读请求，保持 busy 并进入 ABORT_WAIT，待旧响应返回后才重新允许 start，避免旧样本混入新帧。复位必须与后端协调，以清除在途事务。非法帧长、桶数、ROI 长度和触发索引以 config_error 脉冲拒绝，拒绝期间不请求内存。

## 验证内容

每个固定种子包含 80 组核心用例，共 3,437,056 个输入样本、55,702 个桶和 74,616 个 ROI 点。覆盖：

- 覆盖短帧、桶边界、可整除与不可整除长度，最大 16384 点。
- 常量、全正、全负、单调递增/递减、交替极值和伪随机输入；相同原始帧使用 800/400/200/100 等多种桶数。
- 每个桶首、中、尾的正负单点尖峰，及选定桶边界两侧的全帧独立尖峰；每种子共 9624 个尖峰保留检查。
- 桶数 1/3/17/127/799/800、关闭 ROI、奇数 ROI、触发位于首/尾及窗口移动边界，64 位时间戳进位。
- 元数据、内存请求、包络和 ROI 的独立暂停；运行中改变外部配置不得影响已开始的帧。

scoreboard 对每个请求和响应核对顺序索引，对每个输入样本检查读取计数及所属桶；再将实际输出桶的闭区间逐点累计，要求每个索引覆盖次数恰为 1，且所有桶的独立样本计数之和等于帧长。包络数值、极值索引、OTR、ROI 原码/符号/时间戳逐项对照 Python 黄金结果。脚本对实际 CSV 再做一次完整索引覆盖审计。

控制测试包含 8 项非法配置、7 个阶段撤销使能、7 个阶段协调复位，以及每次后的短帧恢复。特别覆盖在途读排空，以及包络和 ROI 分别阻塞的情形。负向测试向读索引、样本保留位和响应协议注入故障，必须分别触发范围、格式和无请求响应断言；预期失败不能当成正常回归错误忽略。

缓存集成使用 16K BRAM：读取 800/400/100 桶，输出 512/1024/2048 点 ROI，并独立核对极值、索引、OTR 和时间戳。

## 重现与验收

```powershell
# 在 D:\示波器，使用 PowerShell 7
& .\FPGA\scripts\run_multires_tb.ps1 -PythonExe 'D:\Python\python3.14\python3.14.7\python.exe' -Project
& .\FPGA\scripts\run_multires_synthesis.ps1
# 更换种子入口
& .\FPGA\scripts\run_multires_tb.ps1 -Seeds 123,456
```

刺激保存在 sim/vectors/multires，黄金结果在 sim/expected/multires，实际 CSV、日志、完整命令、种子和源码 SHA-256 在 reports/multires。正式回归使用 20261020、42 两个种子，再重放首种子；清理并重建原工程的行为仿真后，实际轨迹必须逐文件一致。每个 testbench 有 watchdog、自动断言与终端 PASS；验收同时检查日志和完成用例数。

最终仿真目录为 `FPGA/reports/multires/20261022_125121_d0347ac8`，独立综合目录为 `FPGA/reports/multires_synthesis/20261022_124821_52000e70`。两种子合计 160 组核心数据用例与 8 次真实缓存读出，累计检查 7,234,560 次输入样本、115,604 个桶、160,496 个 ROI 点和 19,248 个尖峰，差异为 0。首种子重放与原工程从零重编译的九份 CSV 均逐文件一致。

独立综合的包络核心使用 953 个 LUT*、796 个 FF*，DSP=0、RAM=0、锁存器=0、读索引宽度=18，综合警告为 0。HDL 编译、展开及运行没有 warning/error；Vivado 主控制台保留板卡库、既有 IP 路径和大数组无法加入默认波形窗口的环境提示，完整文本在 project/console.log。验收清单 `acceptance.json` 与已验证 SHA-256 的 `source_snapshot.zip` 一并归档。

本步完成内部算法和真实冻结缓存的行为级集成。最终板级顶层连接、总线仲裁、UART 包装、布局布线及管脚仍在后续系统集成范围。
