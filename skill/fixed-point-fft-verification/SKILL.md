---
name: fixed-point-fft-verification
description: Resolve FPGA FFT reference mismatches by matching quantization, windowing, scaling and IP configuration before comparing full complex outputs.
---

# 定点 FFT 的输入契约与逐点参考核验

适用：使用 AMD FFT IP 或定点 FFT 的信号处理工程；重点是位宽、窗函数和缩放导致的参考偏差。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 列出采样码转换、位宽、符号、窗量化、乘法舍入/截断、FFT 缩放、输出顺序及溢出规则。
2. 浮点 DFT 用于算法层；按实际生成 IP 对应的官方 bit-accurate C 模型做定点层核验，记录模型版本和配置。
3. 绑定同一冻结帧，核对完整复谱及摘要、主峰与谐波索引；避免只对主峰通过就宣称全部频谱正确。
4. 出现微小弱谐波偏差先检查模型契约，不盲改 RTL 或放宽容差；保存失败和修复后报告及核验代码哈希。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

此为方法与适配器参考，不附带厂商 DLL，也不承诺任意 FFT 配置适用。不能以通用浮点工具替代定点逐位参考；不能将历史通过声明为新的构建通过。
