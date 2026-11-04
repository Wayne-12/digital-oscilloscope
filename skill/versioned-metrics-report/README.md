# 按镜像与来源归档性能、资源和验收数据

类型：校验脚本、报告模板。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

汇总时序、LUT/FF/BRAM/DSP、测量和通信结果，尤其存在多个固件版本的工程。

## 来源与提炼依据

旧镜像长稳可能被误计入当前镜像；缺失报告填零、BRAM 取整和把 CRC 错误写成 BER 会产生虚假性能结论。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 运行 python -m unittest discover -s tests -v；脚本与测试仅依赖标准库。
2. 用 scripts/summary_report.py 中 implementation_rows 解析匹配的实际布线报告；导出 schema 和字段含义见 references/case.md。
3. 将 build ID、镜像 SHA256、设备身份、波特率与测试条件一起绑定，区分 current-image-test 与 historical-other-image。
4. 未测或缺失标记 UNAVAILABLE/NOT_MEASURED；使用临时文件与原子替换导出 UTF-8 BOM CSV，保存失败不能破坏旧报告。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

历史实物导出 232 行 CSV；测试包含错设备、过期证据、镜像篡改、分数 BRAM、校正/标称值区分和原子保存失败。副本测试另行实跑。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

原 collect 函数仍扫描 FPGA/output 与 PC/acceptance_runs 等目录，需要按新项目适配。Vivado 报告格式改变应拒绝或显式更新解析，不猜测缺失数值；工具不会认证手工输入真实性。

## 原始依据

- `PC/protocol/summary_report.py` → [source_01.py](references/source/source_01.py)
- `PC/tests/test_summary_report.py` → [source_02.py](references/source/source_02.py)
- `docs/verification/summary_csv_implementation_20261027.md` → [source_03.md](references/source/source_03.md)
- `FPGA/reports/summary_hardware/20261027_final/report.json` → [source_04.json](references/source/source_04.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
