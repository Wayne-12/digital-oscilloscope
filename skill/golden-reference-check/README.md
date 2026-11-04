# 黄金参考比对与可追溯报告

类型：校验脚本。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

软件算法、RTL 仿真输出和已导出的硬件数值结果；支持统计、包络、FIR、DFT 及自定义参考。

## 来源与提炼依据

原工程的参考模型与固定记录长度、ADC 编码、UART 和 UI 约定混合，无法直接用于其他题目；只检查数组公共部分、同函数自比对或忽略 NaN 会导致误通过。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 先写清输入输出的单位、位宽、顺序、缩放与舍入，选择独立于被测实现的参考模型。
2. 使用 examples/demo_suite.json 的文件或外部命令接口接入自己的输出；不要把黄金输出当成实际输出。
3. 运行 python scripts/verify_all.py；总结果查看 reports 下最新 verification_summary.json，故意失败套件的 ERROR 是预期检出。
4. 运行 python scripts/check_portability.py 检查脱离原工程的隔离运行。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

原工具已有 16 项单元测试、4 个软件算法示例、16384 点历史 CSV 换算检查和故意错误检出。创建后的副本另行实跑，结果记录于根目录 validation.json。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

浮点 DFT 不等同于定点 FFT 签核。CSV 标称电压一致不证明 ADC 绝对精度。主机墙钟时间不等于 FPGA 延迟。本工具未实现 PYNQ 驱动或硬件资源自动采集。

## 原始依据

- `提炼/README.md` → [source_01.md](references/source/source_01.md)
- `提炼/验收结果.md` → [source_02.md](references/source/source_02.md)
- `提炼/docs/提炼说明.md` → [source_03.md](references/source/source_03.md)
- `提炼/docs/接入与接口说明.md` → [source_04.md](references/source/source_04.md)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。

完整配置、单位与适配器接口见 [references/interface.md](references/interface.md)。
