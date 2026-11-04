# 案例与迁移规则

## 报告字段

`scripts/summary_report.py` 的 CSV 字段为：`category`（指标类别）、`metric`（名称）、`value`（值）、`unit`（单位）、`status`（证据/测量状态）、`scope`（本次、当前镜像或历史镜像等适用范围）、`firmware_build`（版本）、`source`（来源文件）、`source_sha256`（来源哈希）、`notes`（限制和备注）。

缺失布线报告使用 `UNAVAILABLE`；未测 BER 使用 `NOT_MEASURED`；没有匹配当前镜像的正式 UART 结果使用 `NOT_QUALIFIED`。这些状态都不能替换为 0 或 PASS。

只解析独立实现报告时，可在本目录运行 `python -c "import sys; sys.path.insert(0,'scripts'); from summary_report import implementation_rows; print(implementation_rows('your_routed_report_directory'))"`。该目录须含实际 `timing.rpt` 和 `utilization.rpt`；返回值保留来源路径和状态。使用者必须确认报告与目标构建匹配。

## 触发条件和历史观察

旧镜像长稳可能被误计入当前镜像；缺失报告填零、BRAM 取整和把 CRC 错误写成 BER 会产生虚假性能结论。

## 可复用处理流程

1. 运行 python -m unittest discover -s tests -v；脚本与测试仅依赖标准库。
2. 用 scripts/summary_report.py 中 implementation_rows 解析匹配的实际布线报告；导出 schema 和字段含义见 references/case.md。
3. 将 build ID、镜像 SHA256、设备身份、波特率与测试条件一起绑定，区分 current-image-test 与 historical-other-image。
4. 未测或缺失标记 UNAVAILABLE/NOT_MEASURED；使用临时文件与原子替换导出 UTF-8 BOM CSV，保存失败不能破坏旧报告。

## 验证与判定

历史实物导出 232 行 CSV；测试包含错设备、过期证据、镜像篡改、分数 BRAM、校正/标称值区分和原子保存失败。副本测试另行实跑。

## 迁移前需重新确认

原 collect 函数仍扫描 FPGA/output 与 PC/acceptance_runs 等目录，需要按新项目适配。Vivado 报告格式改变应拒绝或显式更新解析，不猜测缺失数值；工具不会认证手工输入真实性。

迁移不能只替换目录名：检查输入数据/报文合同、工具版本、器件与 IP 配置、时间和单位、失败返回值以及所有外部依赖。对案例模板，先用最小正例和故意失败的负例验证检查确实会拒绝错误，再接入完整工程。

本例不附伪造提示词或模型回答。赛用报告的大模型协作记录应从真实开发对话中提取，不能用此页说明代替。
