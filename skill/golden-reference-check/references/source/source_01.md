# 黄金参考比对、自动测试与报告工具

这是从数字示波器工程中提炼出的独立 Python 工具包 `goldencheck`。把输入数据交给黄金参考模型，再把独立得到的实际输出逐项比对，自动生成可追溯的 HTML、CSV 和 JSON 报告。

**只依赖 Python 标准库；无需 Vivado、Qt、串口、NumPy 或原示波器工程。** 可复制整个“提炼”文件夹到其他位置运行。建议 Python 3.10 及以上；本次实际验证版本见报告。

本交付是通用验证工具，不是已经实现的 PYNQ Overlay 或 DMA 驱动，也不宣称已获得赛事 Skill 加分认定。若之后迁移到 PYNQ，可在板上驱动外增加输出 JSON 的适配器，继续使用同一套模型和报告。

## 立即使用

Windows 双击 `运行验证.cmd`；或在本文件夹打开 PowerShell：

```powershell
python scripts/verify_all.py
```

程序自动执行单元测试、通用算法示例、历史示波器导出检查和故意失败的示例。每次在 `reports/UTC时间戳/` 下生成新结果，不覆盖旧报告。总验收看 `verification_summary.json` 的 `status`。

单独运行：

```powershell
python -m goldencheck examples/demo_suite.json --out reports/my_demo_01
python -m goldencheck examples/scope_suite.json --out reports/my_scope_01
python -m goldencheck examples/negative_suite.json --out reports/my_negative_01
python -m unittest discover -s tests -v
```

`--out` 必须是尚不存在的新目录。返回码：`0` 全部通过；`1` 有数值或结构不一致；`2` 有输入、配置、程序执行等错误。故意失败示例应返回 `2`，其中两项 FAIL、一项 ERROR；一键验证会检查这些结果是否符合预期。

## 已提供的三个验证场景

| 场景 | 被测输出来源 | 验证内容 | 结论边界 |
|---|---|---|---|
| 通用算法 | 手算统计/包络文件；独立软件 FIR、基 2 FFT 进程 | 已知统计量、非整除分桶与同值索引、FIR 卷积、FFT 全复谱 | 合成数据与软件算法验证，不代表硬件结果 |
| 示波器历史数据 | 原项目 `示波器快照001.csv` 的完整原样副本 | 16384 个原始 ADC 码换算值与导出标称电压一致 | 离线导出一致性，不等于标定、模拟精度或本次上板验收 |
| 错误检出 | 故意改错数值、截短数组、缺失输出 | 防止静默误通过，验证 FAIL/ERROR 判定 | 预期失败，不能作为实物缺陷结论 |

原项目 `参考数据/` 的文件标注为模型生成，所以没有把它们当成真实硬件测试证据。历史采集副本保留了完整 CSV 元数据；其来源标签由原文件声明，本工具没有重新核验采集现场。

## 文件说明

| 路径 | 用途 |
|---|---|
| `goldencheck/core.py` | CSV/JSON 读取、严格比对、外部程序运行、来源哈希 |
| `goldencheck/models.py` | 独立参考：恒等、仿射、统计、包络、FIR、DFT |
| `goldencheck/__main__.py` | 配置运行、证据归档、CLI 返回码 |
| `goldencheck/report.py` | HTML、CSV、JSON 报告 |
| `examples/` | 可直接运行的配置、完整数据副本和独立被测程序 |
| `examples/metrics_template.json` | 性能/资源导入模板；缺失值为 null |
| `tests/` | 数值、边界、错误处理、进程与报告测试 |
| `scripts/verify_all.py` | 一键回归与验收汇总 |
| `scripts/make_examples.py` | 确定性再生成软件示例；不会生成硬件数据 |
| `scripts/check_portability.py` | 复制到独立临时目录，用隔离模式验证不依赖原工程 |
| `scripts/package_delivery.py` | 重新生成交付清单及 ZIP |
| `docs/接入与接口说明.md` | 其他算法、外部程序及可选性能/资源证据接入 |
| `docs/提炼说明.md` | 来源、提炼改动、通用性和验收口径 |
| `reports/` | 本次已跑通的结果，以及后续每次运行结果 |
| `交付清单.json` | 交付文件 SHA256 清单，不包含后续新增报告 |
| `验收结果.md` | 本次最终验证结果与报告入口 |

## 报告如何解读

每个 case 分别记录数据来源、文件 SHA256、参考模型源文件 SHA256、配置快照、比较点数、误差、截断后的差异详情、参考计算时间及外部程序墙钟时间。实际与参考输出均保存到 `artifacts/`，输入/实际输出原文件也会归档。

判定公式：`abs(actual - expected) <= atol + rtol * abs(expected)`。字典必须同键、数组必须同长；布尔值不作为数字比较；NaN、无穷、空结果、缺失文件及程序失败不能通过。容差路径使用 JSON Pointer，写错路径直接报错。

`reference_seconds` 是运行参考模型的主机耗时；`observed_wall_seconds` 包括外部 Python/可执行程序启动、I/O 及计算时间。**不能把这些时间写成 FPGA 核延迟或硬件吞吐率。** 文件模式没有本次执行时间，显示为空。

可通过配置导入带范围说明的性能和资源 JSON；工具给出 `PROVIDED` 标记和来源哈希，不把用户提供值自动认定为硬件实测。未提供证据时显示 `UNAVAILABLE`，不填零。该接口只收集证据，不自动调用综合工具或判断资源目标是否达成。

## 接入自己的项目

1. 选择内置参考或编写 `module:function` 模型，明确单位、位宽、缩放与舍入。
2. 准备真实待测结果 JSON/CSV；也可用命令模式调用仿真、C/C++ 程序或已有硬件驱动。
3. 复制示例配置，修改输入、参考参数、实际输出和容差。
4. 运行工具并查看 HTML；保留配置、原始报告和真实硬件证据。

配置中的命令和自定义 Python 模型会执行本机代码，只运行你信任的配置。命令使用参数数组且不经 shell；工具不会自动连接、下载或烧录开发板。完整接入约定见 `docs/接入与接口说明.md`。
