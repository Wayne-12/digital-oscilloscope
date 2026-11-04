---
name: versioned-metrics-report
description: Collect FPGA timing, resource and UART evidence into version-scoped reports that reject mismatched images and preserve unavailable measurements.
---

# 按镜像与来源归档性能、资源和验收数据

适用：汇总时序、LUT/FF/BRAM/DSP、测量和通信结果，尤其存在多个固件版本的工程。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 运行 python -m unittest discover -s tests -v；脚本与测试仅依赖标准库。
2. 用 scripts/summary_report.py 中 implementation_rows 解析匹配的实际布线报告；导出 schema 和字段含义见 references/case.md。
3. 将 build ID、镜像 SHA256、设备身份、波特率与测试条件一起绑定，区分 current-image-test 与 historical-other-image。
4. 未测或缺失标记 UNAVAILABLE/NOT_MEASURED；使用临时文件与原子替换导出 UTF-8 BOM CSV，保存失败不能破坏旧报告。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

原 collect 函数仍扫描 FPGA/output 与 PC/acceptance_runs 等目录，需要按新项目适配。Vivado 报告格式改变应拒绝或显式更新解析，不猜测缺失数值；工具不会认证手工输入真实性。
