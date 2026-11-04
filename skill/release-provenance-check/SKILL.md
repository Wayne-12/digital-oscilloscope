---
name: release-provenance-check
description: Verify release file hashes and bind FPGA source snapshots, firmware ELF and programming images so stale or mismatched artifacts are rejected.
---

# 源码、ELF、位流与发布镜像的一致性校验

适用：FPGA 发布包、带 MicroBlaze ELF 的位流，以及同一硬件 build ID 下的软件修订。

先读 [references/case.md](references/case.md) 的历史故障与验证边界；需要原始证据时按 [README.md](README.md) 的映射读取 `references/source/`，不要一次加载全部文件。

1. 冻结来源清单，记录相对路径 SHA256、工具版本、器件和配置；将输入源、ELF、运行 bit 与 SPI 文件分开标识。
2. 在实施后显式用匹配的 MMI/处理器路径执行 UpdateMEM，产出独立 runtime 位流；不得把中间 bit 作为已嵌入固件发布。
3. 在工作区运行 python scripts/verify_manifest.py --root WORKSPACE --manifest MANIFEST，核对 sha256 映射中的每个文件并拒绝越界路径。
4. 发布时再运行项目自身的源快照、功能、时序和 Flash 图像校验。通用哈希脚本只做文件一致性，不替代这些检查。

交付时写明触发条件、输入/目标身份、实际执行步骤、证据位置、结果和未验证范围。对现场没有执行的检查给出待验证状态，不用历史 PASS 替代。

哈希不证明功能正确性或清单真实性；核验清单应来自可信发布过程。通用脚本只支持 sha256 字段，不自动猜测其他清单格式。固件更新后的真实板端执行仍需独立确认。
