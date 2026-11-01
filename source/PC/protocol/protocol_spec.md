# 任意波形表扩展（实物及固化验收通过）

能力位5（32），0xA4261027；保留此前全部功能。表固定1024点，每点有符号16位Q15整数，范围-32767～32767；-32768拒绝。输出沿用25MHz DDS的32位相位累加器，以有效相位最高10位查表；数字幅度是相对DAC中码的半摆幅，偏置和14位钳位规则不变。原始频率/相位/幅度/偏置仍通过SET_DDS设置；额外SELECT选择标准DDS或表。

所有字段小端。ACK为单字节0；拒绝沿用ERR_LENGTH/ERR_CONFIG/ERR_BUSY。BEGIN/CHUNK/COMMIT/SELECT要求DDS禁用、采集停止且不忙。表有两组BRAM：下载仅写非活动表，完整CRC通过后切换；失败不更改活动表。表在断电或复位后失效，需要PC重新下载；固化固件不等于永久保存用户表。下载成功不自动启用输出。

|命令|请求|成功响应|
|---|---|---|
|0x15 BEGIN|u32点数=1024|ACK；清空暂存计数/CRC，不清活动表|
|0x16 CHUNK|u16偏移+1～256个i16，偏移必须恰好为已接收点数|ACK；验证整块数值后追加|
|0x17 COMMIT|u16整表CRC16-CCITT（初值FFFF，多项式1021），按2048个小端数据字节计算|ACK；仅完整1024点且CRC相符时原子切换|
|0x18 READ|u16偏移、u16数量1～256|原4字节范围+对应活动表i16数据；不触发输出|
|0x19 STATUS|空|16字节：u8版本1、u8标志（bit0有效、bit1下载中、bit2已选表）、u16保留0、u16容量1024、u16已接收数、u16活动CRC、u16暂存CRC、u32保留0|
|0x1A SELECT|u8选择0标准DDS/1活动表|ACK，选表要求有效|

PC文件：UTF-8 CSV，单列value，恰好1024个有限归一化值[-1,1]，可省标题；按最近整数、半数远离零量化为Q15。下载后必须读回全部1024点逐字节比较并查询状态，才显示成功。

# 示波器二进制协议 v1

当前交付固件 `0xA4261027`、能力63：系统时钟100 MHz、UART 921600 bit/s、8N1、空闲高电平、数据位LSB first。115200 bit/s为旧固件基线；波特率由镜像决定。UART 使用相位累加分频；115200 档每位占 868 或 869 个系统周期。这里的“帧”是下面的协议包，与 UART 单字节的起止位不同。

## 字段和 CRC

所有多字节整数均为**小端序**，有符号整数使用二进制补码；禁止用主机本地结构体对齐方式直接拷贝。固定头部 26 字节，负载 0～1024 字节，CRC 2 字节；最短 28、最长 1052 字节。

| 字节偏移 | 字段 | 类型/长度 |
|---|---|---|
| 0 | magic | `55 AA`，2 字节 |
| 2 | version | u8，固定 1 |
| 3 | type | u8 |
| 4 | sequence | u16 |
| 6 | payload_length | u16，仅计算 payload |
| 8 | sample_timestamp | u64 |
| 16 | sample_rate | u32，Hz |
| 20 | trigger_index | u32，完整记录内的逻辑索引 |
| 24 | flags | u16 |
| 26 | payload | 0～1024 字节 |
| 26 + payload_length | CRC16 | u16，**低字节先发** |

CRC 算法为 **CRC-16/CCITT-FALSE（CRC-16/IBM-3740）**：宽度 16，多项式 `0x1021`，初值 `0xFFFF`，RefIn=false，RefOut=false，XorOut=`0x0000`。覆盖范围为 version（偏移 2）到 payload 最后一个字节；不覆盖 `55 AA` 和 CRC 本身。CRC 算法不反射与 CRC 结果的小端传输是两个独立约定。

| 输入字节（ASCII） | CRC 数值 | 线上 CRC 字节 |
|---|---|---|
| 空输入 | FFFF | FF FF |
| `123456789` | 29B1 | B1 29 |
| `abc` | 514A | 4A 51 |

算法每字节先 `crc ^= byte << 8`，再重复 8 次：检查旧 bit15，左移 1 位；旧 bit15 为 1 时异或 1021；每次保留低 16 位。PC 参考实现使用标准库 `binascii.crc_hqx(data, 0xffff)`。

flags：RESPONSE=`0x0001`，ERROR=`0x0002`，MORE=`0x0004`，FIRST=`0x0008`，LAST=`0x0010`。请求 flags 必须为 0。普通响应 type=request.type OR `0x80`，sequence 回显请求值。响应头时间戳、采样率和触发索引取命令执行时的后端元数据；波形响应另见分段规则。请求的这三个字段会被完整解析，目前不参与配置。

## 命令

`uN`/`iN` 分别表示 N 位无符号/有符号整数。以下 payload 中的偏移从 payload 起点计算。除 PING、版本、状态、能力、配置读回、波形、包络、测量的正常响应外，命令均返回 1 字节状态码。

| 请求 type | 命令 | 请求 payload |
|---|---|---|
| 01 | PING | 0～1024 字节，响应逐字节回显 |
| 02 | 读取版本 | 空；响应 8 字节：`01 00 00 00` + u32 build=`0x20261022` |
| 03 | 读取状态 | 空；响应格式见下表 |
| 10 | 设置记录 | u32 length，u32 pre_ratio_ppm |
| 11 | 设置触发 | 24 字节，见下表 |
| 20 | 单次捕获 | 空 |
| 21 | 停止 | 空 |
| 30 | 读取波形 | u32 offset，u32 count；count 必须大于 0 |
| 31 | 读取测量 | 空；响应 64 字节，见下表 |
| 40 | 设置 DDS | 16 字节，见下表 |
| 04 | 查询扩展能力 | 空；仅在版本 build 的 bit31=1 时查询，响应 `<u32 flags, u16 max_buckets, u16 max_roi>` |
| 05 | 读取当前配置 | 空；仅在能力 flags bit1=1 时使用；响应 48 字节，见下文 |
| 32 | 读取板端包络 | `<u16 bucket_count>`，1～800；读取当前冻结帧，响应 B2 分包 |

状态码：0=OK，1=ERR_LENGTH，2=ERR_CONFIG，3=ERR_BUSY，4=ERR_NO_FRAME，5=ERR_UNKNOWN。非零状态响应带 ERROR 标志。合法 CRC 的未知命令仍有错误响应；CRC、版本、帧长度和超时错误不响应。语义验证失败不得修改配置。

### 板端多分辨率扩展（2026-10-24）

新增实物版本 build 为 `0xA0261024`：bit31 表示支持能力查询，低 31 位仍为构建标识 `0x20261024`。原 8 字节版本响应、协议 version=1、CRC 和已有命令均兼容。旧 build 没有该标志时不探测新命令，PC 回退完整原始快照，不制造“未知命令”计数。

能力 flags 的 bit0=1 表示支持板端 min/max 包络和同一冻结帧的原始 ROI；该版本能力响应为 flags=1、max_buckets=800、max_roi=2048。ROI 复用 READ_WAVE，不重新触发。包络扫描与原始读取共享后端读口，互斥执行；传输未结束时 SINGLE 不得释放当前帧。

### 实物闭环校准配置读回扩展（2026-10-25）

新 build 为 `0xA0261025`，能力响应 flags=3、max_buckets=800、max_roi=2048。bit1 表示支持 GET_CONFIG，旧命令与多分辨率格式保持兼容。

GET_CONFIG（0x05）请求必须为空，响应 type=0x85，payload 是执行命令时锁存的 48 字节配置快照：

| 偏移 | 内容 |
|---|---|
| 0 / 4 | u32 record_length / pre_samples（实际样本数，不是 ppm） |
| 8～31 | 当前 SET_TRIGGER 的完整 24 字节格式 |
| 32～47 | 当前 SET_DDS 的完整 16 字节格式；频率为最初成功接受的 Hz 值 |

读取不修改配置。非法请求长度返回 ERR_LENGTH。主机在 STOP 后保存快照，临时下发测试 DDS 和自动触发，结束、取消或错误时均恢复 DDS 与触发，再逐字节比较 GET_CONFIG；校准流程不修改记录配置。原始数据仍由 READ_WAVE 读取；本扩展没有生成校准样本或直接改写 ADC 码的命令。零点、多点拟合、频响与相对校正由 PC 对真实完整帧计算。首次实测定义组合链路相对基线，不代表绝对电压校准。

B2 正常包的 payload 为 `<u32 first_bucket, u32 record_length, u16 effective_buckets, u16 encoding>`，随后为多个 `<i16 minimum, i16 maximum, u8 otr_any>`。encoding=1。每包最多 202 桶，payload 最长 1022 字节；最后一包可短。min/max 使用 `2047-raw_code` 的 signed13 数值，符号扩展为 i16；OTR 是该桶所有点的逻辑或。时间戳、采样率和触发索引始终来自完整冻结帧，各包保持相同。

有效桶数 `B=min(record_length, requested_buckets)`，第 i 桶覆盖 `[floor(i*N/B), floor((i+1)*N/B)-1]`，无遗漏、无重叠，保留单点尖峰。最小/最大值的标称电压为 `(signed_code+0.5)*10/4095 V`，与现有原始码换算一致。

首包 sequence 回显请求，后包依次加 1 并允许 16 位回绕。FIRST/MORE/LAST 沿用波形分包规则。PC 严格检查请求序号、连续桶索引、总长度、桶数、encoding、时间戳、采样率、触发索引、极值范围/顺序、OTR 和完成标志。不满足合同的数据不得显示为有效概览。

STOP 在包已提交时先完成该包的长度和 CRC，再终止剩余包；原始冻结帧仍保留，可重新请求。取消扫描若存在未完成的内存读取，排空旧响应之后才重新允许请求。新 SINGLE 会替换旧冻结帧；PC 用完整帧首时间戳校验 ROI 身份，拒绝把新帧样本混入历史概览。

800 桶概览实际响应为 `800*5+4*(12+28)=4160 B`；2048 点原始 ROI 响应为 `2048*2+5*(8+28)=4276 B`。组合为 8436 B，对比 16384 点完整原始响应 33956 B，约减少到四分之一。上述包含响应分包头与 CRC，不含请求、状态轮询、USB 时延和扫描等待，不等同于界面刷新率提升四倍。

记录长度仅接受 16384；预触发比例为 0～1000000 ppm。预触发样本数为 `floor(((length-1)*ratio_ppm+500000)/1000000)`。复位默认 length=16384、pre_samples=8192。捕获忙时禁止改变记录和触发配置，读回长度取冻结 BRAM 帧元数据。

单次捕获会先释放已有冻结帧，等待后端 ready，然后输出 single_pulse。等待上限为 100000 个系统周期，超时返回 ERR_BUSY。STOP 清除 acquire_enable 并输出 stop_pulse；正在发送的波形包完整发完，后续分段取消。上位机收到 STOP 成功响应后应丢弃尚未结束的波形重组状态。

### 设置触发（24 字节）

| 偏移 | 字段 | 类型/限制 |
|---|---|---|
| 0 | kind | u8，0上升、1下降、2窗口进入、3窗口离开、4正脉宽、5负脉宽、6欠幅、7过幅、8 OTR |
| 1 | reserved | u8，必须 0 |
| 2 | threshold | i16，-4096～4095；校验后转 signed13 |
| 4 | hysteresis | u16，0～8191 |
| 6 / 8 | window_low / high | i16，各为 -4096～4095 |
| 10 / 14 | width_min / max | u32，采样时间戳单位；脉宽类型要求 min>0 且 max>=min |
| 18 | amplitude_limit | u16，0～16383 |
| 20 | observation_samples | u32，<=16384；幅度触发要求 >=2 |

窗口触发还要求 `window_low+hysteresis < window_high-hysteresis`。比较和迟滞语义沿用第七步 `trigger_core`。先对线上完整字段检查范围，再缩窄，防止高位被截断后误接受。

### 设置 DDS（16 字节）

| 偏移 | 字段 | 类型/限制 |
|---|---|---|
| 0 | waveform | u8：0正弦、1方波、2三角波、3直流 |
| 1 | enable | u8，0 或 1 |
| 2 | frequency_hz | u32，0～12500000 |
| 6 | phase_offset | u32，相位字，模 2^32 |
| 10 | amplitude | u16，0～16383，DAC LSB |
| 12 | dc_offset | i32，-131072～131071；校验后转 signed18 |

第一版 DAC 采样率固定 25 MHz。相位增量为 `floor((frequency_hz*2^32+12500000)/25000000)`，即最近整数、半值向上；使用 64 位中间量。配置输出连接已有 `dds_core`，DDS 的饱和及安全中码规则沿用第四步。此版没有运行中 DAC 换频命令。

## 状态响应（48 字节）

| 偏移 | 字段 |
|---|---|
| 0 | u8 flags：bit0 capture_busy，bit1 frame_available，bit2 dds_enable |
| 1 | u8 backend_error |
| 2 / 3 | u8 协议版本 1 / 保留 0 |
| 4 / 8 | u32 record_length / pre_samples |
| 12 / 16 / 20 / 24 | u32 CRC / 长度 / 版本 / 超时错误计数 |
| 28 / 32 | u32 未知命令 / 命令语义错误计数 |
| 36 / 40 | u32 UART 错误停止位 / RX FIFO 溢出计数 |
| 44 | u32 已通过 CRC 的帧数，包括本次状态请求 |

所有计数器复位清零，以 u32 自然回绕。未知命令同时计入“未知命令”和“命令语义错误”。解析错误按被拒绝的候选帧头计数：一个受损物理包若含多个 `55 AA`，可能产生多个候选错误。UART 假起始脉冲另有 false_starts 输出；持续低电平只记一次停止位错误，返回高电平后才重新找起始位。

## 测量响应（64 字节）

| 偏移 | 字段 |
|---|---|
| 0 / 1 / 2 / 3 | u8 stats_valid / period_valid / duty_valid / measurement_error |
| 4 | u32 sample_count |
| 8 / 10 / 12 | i16 minimum / maximum / mean |
| 14 / 16 | u16 peak_to_peak / rms |
| 18 | 保留 2 字节，0 |
| 20 / 28 | i64 sum / u64 square_sum |
| 36 | u64 period_q16，采样周期单位 |
| 44 / 48 / 52 | u32 frequency_hz / duty_ppm / period_count |
| 56 | 保留 8 字节，0 |

测量值来自已有 `measurement_core` 的完成结果；本命令不隐式启动新测量。没有完整合格周期时 period_valid=0、frequency_hz=0，不能将其解释为有效频率。

测量核最大记录长度为 16384 点；线上 sample_count 和 period_count 使用已有 u32 字段，帧格式和 CRC 定义不变。

## 波形分段

正常波形包 type=`B0`。payload 为 `u32 absolute_offset | u32 total_record_length | u16 sample_words[]`。每包最多 508 点，样本格式保留 `{OTR,3'b000,raw_code[11:0]}`，每个字低字节先发。

第一包 sequence=请求 sequence，后续每包加 1，模 65536 回绕。第一包带 FIRST，最后一包带 LAST，其他包带 MORE；FIRST 可以与 LAST 同时出现。首包 offset 可以非零。每包 timestamp=`frame.first_timestamp+absolute_offset`，模 2^64；trigger_index 始终为完整记录中的位置，不随分段移动。

offset+count 用 33 位加法比较被冻结帧长度，不能先缩窄到后端地址宽度。包内禁止插入其他响应；命令响应可在波形包边界插入。正在传输时再次请求波形返回 ERR_BUSY。PC `WaveAssembler` 检查连续 offset、sequence、时间戳、长度和触发元数据。

## 背压、超时与重新同步

内部字节流使用 valid/ready，阻塞期间生产者必须保持 valid 和 data。RX/TX 默认各有 256 字节 FIFO。物理 UART **没有 RTS/CTS**：RX 满时丢弃新字节并增加 rx_overruns。上位机建议逐命令等待响应，或实现受控窗口；不能把内部 ready 当作线上流控。

解析器保留 2048 字节候选队列。候选版本、长度、CRC 或空闲间隔超时错误时仅滑动一个字节，重新搜索 `55 AA`，因此不会把受损包内的潜在帧头整段丢弃。CRC 正确的 payload 可任意包含 `55 AA`，不会被误拆包。默认间隔超时 100000 个系统周期（100 MHz 下 1 ms），应大于一个 UART 字节时间；字节级快速测试单独缩短为 200 周期。消费者对已验证帧的暂停不算线路超时。

`scope_uart_endpoint` 连接 UART 与协议核心；CRC 正确且命令被接受时锁存 `last_request_header`。后端接口在系统时钟域使用，真实采样域的握手和 BRAM 连接由板级顶层实现。

参考代码：本目录 `scope_protocol.py`；回归入口：`FPGA/scripts/run_uart_tb.ps1 -Project`。


## 冻结帧测量及 1024 点 FFT 摘要扩展

GET_CAPABILITIES bit2=1 表示支持板端测量及 FFT（flags=7），build ID 为 0xA0261026。冻结后先完成 FPGA 分析再发布 frame_available，分析期间 status busy=1；摘要与波形头共享 timestamp、sample_rate、trigger_index。原始 ROI 最大2048点与 FFT 长度无关。

READ_MEASURE=0x31，空请求，响应0xB1共64字节，沿用基础测量格式。未冻结帧时返回 ERR_BUSY 或 ERR_NO_FRAME。样本单位为2047−raw，标称电压为 (signed+0.5)×10/4095，PC使用精确sum/square_sum保留半码校正；新固件不再返回全零占位。

READ_SPECTRUM=0x33，空请求，响应0xB3共96字节，小端：

| 偏移 | 类型 | 内容 |
|---|---|---|
| 0 | u8 | 版本1 |
| 1 | u8 | bit0主峰有效，bit1前1024点出现OTR |
| 2、3 | u8 | 错误及保留，正常均0 |
| 4 | u16 | 固定1024 |
| 6、7 | u8 | 窗函数1（周期Hann）及保留0 |
| 8 | u32 | 源偏移0 |
| 12、14 | u16 | 主峰bin及保留0 |
| 16 | u32 | 主峰频率Hz |
| 20、24 | u32 | 主峰峰值幅度及RMS幅度，ADC码Q16 |
| 28 | i32 | 加窗直流ADC码Q16 |
| 32起 | 四项，每项16字节 | H2～H5：阶次u8、有效u8、bin u16、频率Hz u32、峰值幅度Q16 u32、保留u32 |

频率按bin×fs/1024四舍五入。Hann主峰搜索bin2～510；谐波要求主峰bin≥4且h×bin<511，取目标±1 bin最大峰值幅度。无效阶次的有效位为0。缺帧、忙、长度错误按标准错误码拒绝。主峰不等于任意波形的基频；尤其偶次谐波强于基波时，应结合时域判读。

频谱仅作主峰和主要谐波摘要。低频精确测频使用整帧阈值交越；FPGA摘要固定周期Hann，不受PC显示窗切换影响。新固件UI会额外读取92字节的测量包和124字节频谱包，每帧增加216字节响应及56字节请求。
# 2026-10-26 三模式扩展（候选 build 0xA1261026）

此扩展仍使用 v1 帧头、CRC 和序号。能力 bit 3 (`8`) 表示提供板端采集模式；支持原分析功能的新镜像总能力值为 `15`。旧镜像能力 `7` 的正式 UART 验收保持原版本边界。

| 请求 | 负载 | 成功响应 |
|---|---|---|
| `0x12 SET_CAPTURE_MODE` | `<B3xI>`：mode，3 个零保留字节，AUTO 超时采样周期数 | `0x92`，一个零字节 |
| `0x13 GET_CAPTURE_CONFIG` | 空 | `0x93`，同样的 8 字节配置 |
| `0x22 RUN` | 空 | `0xA2`，一个零字节 |
| `0x23 RELEASE_FRAME` | 空 | `0xA3`，一个零字节 |

模式 0=AUTO、1=NORMAL、2=SINGLE。超时计数非零，单位为 25 MHz ADC 周期；默认 `2500000`，即预触发历史就绪后等待 100 ms。AUTO 可提前响应真实触发，无触发时超时捕获；NORMAL 只响应真实触发；SINGLE 只捕获一次后保持。`0x20 SINGLE` 始终临时执行单次，且不修改所选配置。RUN 使用所选配置。

模式修改需要先 STOP；采集/分析活动中或 acquire_enable 仍有效时返回 BUSY。RUN 开始新采集前释放原冻结帧；STOP 可取消等待或采集，不删除已完成的冻结帧。AUTO/NORMAL 在一帧完成后冻结，PC 可反复读取波形、包络、ROI、测量、频谱而保持同一身份。PC 读取完成后发送 RELEASE_FRAME，FPGA 内部重新装载采集；无需再发 SINGLE。SINGLE 模式拒绝 RELEASE_FRAME。此方式具有读取与分析死区，不是连续无死区采样。

其他错误码沿用原协议：长度不符=1，非法配置=2，忙=3，无冻结帧=4，不支持=5。所有新命令必须检查成功 ACK 后才改变主机本地状态。GET_CAPTURE_CONFIG 仅表示所选模式与超时，不能单独证明上一次捕获是否自动触发；自动触发实际行为由专项仿真和不可达门限实物测试验证。

# 2026-10-27 整帧饱和计数扩展

候选 build `0xA2261027`，能力 flags=31（新增 bit4=16）。旧三模式版本 `0xA1261026` 的能力仍为15。新扩展沿用 v1 帧头、CRC与序号。

`READ_SATURATION (0x34)` 负载为空，成功响应 `0xB4`，负载16字节 `<BBHIII>`：version=1、flags、reserved=0、count=16384、saturated_samples、events。flags bit0表示有效，bit1表示板内诊断帧，其余必须零。饱和样本的定义为原始12位码0或4095；每点最多计一次。连续事件为同一线性帧内最大连续饱和区间，帧首帧尾不合并，读握手停顿不切断事件。OTR位不参与该定义。统计由FPGA扫描完整冻结帧完成，头部时间戳/采样率/触发索引绑定该帧，ROI与重复读取不改变计数。未完成采集/分析时返回BUSY或NO_FRAME。

`SET_DIAGNOSTIC (0x14)` 负载1字节，需要先STOP；0=正常ADC，1=按采样时间戳mod16注入码型（相位0/1/2/15为raw0，相位7为raw4095，其余raw2047），2=全raw4095，3=全raw2047。只替换捕获存储器输入，不改变DAC物理输出。所有注入帧的统计flags明确置diagnostic，STOP与RESET清除注入。普通UI不暴露注入控制，供明确标记的板内非零计数验收使用。

界面以完整帧的饱和样本数和连续事件数替代OTR报警与ROI点数。原始OTR位、ROI读取和数据有效性检查继续保留。旧固件只有局部窗口时不得显示伪造的整帧零计数。

