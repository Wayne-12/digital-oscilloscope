# 定点 FFT 的输入契约与逐点参考核验

类型：踩坑清单、案例模板。本目录是独立 Skill 单元，中文为正文，文件路径使用英文。

## 适用范围

使用 AMD FFT IP 或定点 FFT 的信号处理工程；重点是位宽、窗函数和缩放导致的参考偏差。

## 来源与提炼依据

初始审计用理想浮点窗，忽略 Q3/Q16 输入舍入，约 0.01 ADC 码的弱谐波相邻桶排序不同；放宽容差会掩盖参考契约错误。

从本队真实开发问题提炼，原始源码/报告的字节副本列于下方。`provenance.json` 记录来源路径与 SHA256。历史报告只证明其标明版本、环境与范围；本目录新增说明不是当年的大模型对话记录。

## 使用方法

1. 列出采样码转换、位宽、符号、窗量化、乘法舍入/截断、FFT 缩放、输出顺序及溢出规则。
2. 浮点 DFT 用于算法层；按实际生成 IP 对应的官方 bit-accurate C 模型做定点层核验，记录模型版本和配置。
3. 绑定同一冻结帧，核对完整复谱及摘要、主峰与谐波索引；避免只对主峰通过就宣称全部频谱正确。
4. 出现微小弱谐波偏差先检查模型契约，不盲改 RTL 或放宽容差；保存失败和修复后报告及核验代码哈希。

详细操作与迁移规则见 [SKILL.md](SKILL.md)，案例见 [references/case.md](references/case.md)。

## 已验证效果

历史验证记录保留理想浮点窗导致的失败与修正后的通过说明；参考适配器固定 1024 点 signed16 并依赖匹配 IP 模型。本次只读审查，未加载厂商 DLL。

集合本次实际执行结果见上一级 `validation.json`。不要把文件齐全/说明校验通过理解成新的上板或综合通过。

## 失效条件与边界

此为方法与适配器参考，不附带厂商 DLL，也不承诺任意 FFT 配置适用。不能以通用浮点工具替代定点逐位参考；不能将历史通过声明为新的构建通过。

## 原始依据

- `FPGA/scripts/fft_bitaccurate_reference.py` → [source_01.py](references/source/source_01.py)
- `FPGA/scripts/audit_board_analysis.py` → [source_02.py](references/source/source_02.py)
- `docs/verification/fpga_measure_fft_1024_20261026.md` → [source_03.md](references/source/source_03.md)
- `FPGA/reports/board/20261026_162503_verified/manifest.json` → [source_04.json](references/source/source_04.json)

`references/source/` 是溯源快照；其中脚本可能仍依赖原工程路径、工具、模块或设备，不是可直接跨项目运行的入口。明确标为 `scripts/` 的可执行副本按本页说明运行。迁移时使用自己的参数、硬件合同和验证，保留修改前后证据。
