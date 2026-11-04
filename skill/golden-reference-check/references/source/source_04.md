# 配置与接入

配置文件编码为 UTF-8，可带 BOM。所有数据文件、`evidence_files` 和命令工作目录相对配置文件所在目录解析；不依赖启动终端的目录。运行 `python -m goldencheck` 时需位于包含 `goldencheck/` 的工具包根目录。

## 最小配置

```json
{
  "schema_version": 1,
  "name": "我的算法验证",
  "cases": [{
    "id": "case-001",
    "evidence": "simulation-output",
    "input": {"path": "input.json"},
    "reference": {"model": "fir", "params": {"taps": [0.25, 0.5, 0.25]}},
    "observed": {"path": "actual.json"},
    "tolerance": {"atol": 0.000001, "rtol": 0.00001}
  }]
}
```

`id` 非空且套件内唯一。`evidence` 和 `description` 用于说明来源与结论范围，工具不会认证来源标签。一次运行可以包含不同长度、不同算法和不同数据来源。

## 输入和输出

- JSON 默认读取整个文档。`keys` 可逐级选择对象键/数组索引，例如 `{"path":"x.json","keys":["result",0]}`。
- CSV 指定 `column`，例如 `{"path":"capture.csv","column":"raw_code_12bit"}`。支持 UTF-8 BOM、空行和 `#` 开头的整行元数据；数值列转为浮点数。适用于普通数值 CSV，不支持带换行的单元格。
- JSON 支持嵌套数组、对象、数字、布尔、字符串和 null。复数必须转换为 `[real, imag]`。
- 字典多键/缺键、数组多点/少点都失败，不能通过裁切输出掩盖错误。整数与浮点可以按数值比较；大于双精度可精确表示范围的整数优先用 JSON 保留，CSV 浮点读取不适合大整数逐位比对。
- 数组顺序参与比较，不自动重新排列、插值、同步或估计延迟。对齐应在适配器中明确完成并记录。

## 内置黄金参考模型

| model | params | 约定 |
|---|---|---|
| `identity` | 无 | 用于检查传输或回放；输入应是一维有限数值数组 |
| `affine` | `scale`, `offset` | `y=x*scale+offset`，无隐式量化 |
| `statistics` | 无 | count/minimum/maximum/mean/rms/vpp，RMS 包含 DC |
| `envelope` | 正整数 `buckets` | 桶数限制到输入长度，边界 `floor(i*N/B)`，首个相同极值优先，last 为闭区间索引 |
| `fir` | 非空数值数组 `taps` | 因果卷积、初始零状态、输出与输入等长、不追加尾部 drain |
| `dft` | `window`: rectangular/hann；`normalization`: none/forward | 负指数前向 DFT，全 N 点复谱；Hann 为周期窗；forward 表示除 N；默认不归一化 |

DFT 为独立 O(N²) 定义，限制最多 4096 点；无自动零填充、ADC 位移、窗增益补偿、定点舍入或硬件缩放。要验证原工程定点 FFT，应自定义位宽和缩放一致的参考，不能把本例浮点 FFT 比对直接用于硬件签核。

## 自定义参考

把 `my_reference.py` 放到工具包根目录或 Python 可导入路径：

```python
def gain(data, factor=2):
    return [x * factor for x in data]
```

配置写为 `"reference":{"model":"my_reference:gain","params":{"factor":2}}`。接口为 `function(data, **params) -> JSON可序列化结果`。参考程序不应导入被测程序来计算相同输出，否则不能提供独立性；源文件哈希自动记录，外部依赖及版本请加入 `evidence_files` 或另附环境文件。

## 外部被测程序

```json
"observed": {
  "mode": "command",
  "argv": ["{python}", "board_adapter.py", "{input}", "{output}"],
  "timeout_seconds": 30
}
```

占位符只能作为完整参数使用：`{python}` 是当前 Python；`{input}` 是本次解析后的输入 JSON 临时文件；`{output}` 是待写的实际结果 JSON 路径。其余参数原样传递。程序必须成功返回并写入输出；不得自行写黄金结果代替实际输出。套件中的 reference.params 不自动传给被测程序，必须通过显式命令参数或其独立配置固定两侧契约。

外部仿真/C++/PYNQ 适配器均遵守这一接口即可：读取输入 → 调用自己的被测实现/驱动 → 等待完成 → 把实际输出写入 `{output}`。超时、非零退出或没有结果文件均 ERROR。标准输出不作为结果，非零退出时报告保留最多 2000 字节 stderr 摘要；完整进程日志需由适配器自行保存。

临时输出 JSON 被复制入报告 artifacts 后清理。`subprocess.run` 的超时终止直接子进程，不保证杀死它另外启动的进程树；适配器应自行管理其他进程。工具没有内置 UART/PYNQ 连接和设备恢复逻辑，相关测试需由现有驱动承担。

推荐给 suite 增加 `"evidence_files":["board_adapter.py","build_manifest.json"]`，把被测源文件、位流哈希及版本说明也归档。工具不自动追踪命令的全部依赖。

## 容差

全局 `atol`、`rtol` 默认为零，允许非负有限数值。`overrides` 仅作用于准确的叶子路径：

```json
"tolerance": {
  "atol": 0,
  "rtol": 0,
  "overrides": {"/rms": {"atol": 0.01}, "/bins/0/1": {"atol": 0.000001}},
  "max_details": 30
}
```

路径按照 JSON Pointer，键中的 `/` 写成 `~1`，`~` 写成 `~0`。不存在的路径、容器路径、非法容差直接 ERROR，避免拼写错误静默放宽判定。max_details 只限制报告展示的差异条数，不影响完整遍历和失败计数。

报告 RMSE/最大误差对全部已对齐的数值叶子聚合，包含不同字段，单位可能不同；混合指标只能用于诊断，不应解释为某种统一物理误差。相对误差最大值只统计参考非零项；零参考靠绝对误差判定。结构差异单独计入 mismatches。

## 性能、资源和来源证据

复制 `examples/metrics_template.json` 填入真实值，保留原始工具报告/测量方法，在套件顶层加入：

```json
"metrics": [{"path": "my_metrics.json"}],
"evidence_files": ["timing.rpt", "utilization.rpt", "bitstream_manifest.json"]
```

指标文件格式：

```json
{"scope":"器件、构建哈希、测量时间、工具版本、测量方法与限制", "metrics":[
  {"name":"kernel_latency", "value":null, "unit":"cycles"}
]}
```

数值标为 PROVIDED，null 标为 UNAVAILABLE。工具自动读取、计算文件 SHA256 并纳入报告，不自动验证指标与某块板卡/位流匹配，也不对性能资源设通过门槛。使用者应保证同一构建来源，不能混合历史不同版本的数据。`scope` 不能为空。

## 输出格式

`report.json` 包含 suite/status/summary/environment/configuration/cases/metrics/evidence_files；case 包含 status、compared、numeric_compared、mismatches、max_abs_error、rmse、details、输入来源、模型来源、实际输出来源与时间。ERROR case 可能没有比较指标。

`report.html` 可离线打开，无网络依赖；`summary.csv` 和 `metrics.csv` 为 UTF-8 BOM，适合 Excel 查看。`suite.snapshot.json` 留存当时配置，`artifacts/` 保存输入/实际原文件、完整黄金值/实际值、显式附加证据。

报告中的历史原路径用于溯源，复制报告文件夹后应通过 artifact 相对路径查看附件；不依赖原路径才能阅读结果。要重新运行，则复制整个工具包并用 examples 配置执行。
