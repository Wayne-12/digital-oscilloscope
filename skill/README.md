# 示波器工程可复用技能包

工程根目录下的 `skills/` 为集合目录，每个直接子目录是一个独立 Skill。共 12 项，按赛事的脚本、案例和踩坑经验分类；不是 12 项已验证的跨板产品。

| 子目录 | 能力 | 类型 |
|---|---|---|
| [golden-reference-check](golden-reference-check/README.md) | 黄金参考比对与可追溯报告 | 校验脚本 |
| [layered-rtl-regression](layered-rtl-regression/README.md) | 单元到系统的分层回归与结果复用门禁 | 案例模板、校验脚本 |
| [windows-vivado-environment](windows-vivado-environment/README.md) | Windows 中文路径下的 Vivado 进程环境隔离 | 案例模板、踩坑清单 |
| [release-provenance-check](release-provenance-check/README.md) | 源码、ELF、位流与发布镜像的一致性校验 | 校验脚本、踩坑清单 |
| [qspi-release-verification](qspi-release-verification/README.md) | QSPI 固化的备份、独立读回与冷启动验收 | 案例模板、踩坑清单 |
| [cdc-reset-enable-debug](cdc-reset-enable-debug/README.md) | 复位与使能 CDC 的根因排查和异步切换验证 | 踩坑清单、案例模板 |
| [cooperative-serial-service](cooperative-serial-service/README.md) | 显示刷新期间的串口服务与控制权交接 | 踩坑清单、案例模板 |
| [uart-fault-injection](uart-fault-injection/README.md) | 串口协议故障注入与验收证据分级 | 校验脚本、案例模板 |
| [versioned-metrics-report](versioned-metrics-report/README.md) | 按镜像与来源归档性能、资源和验收数据 | 校验脚本、报告模板 |
| [fixed-point-fft-verification](fixed-point-fft-verification/README.md) | 定点 FFT 的输入契约与逐点参考核验 | 踩坑清单、案例模板 |
| [adc-iob-placement-check](adc-iob-placement-check/README.md) | ADC 输入 IOB 的实际布局与时序验收 | 校验模板、踩坑清单 |
| [transactional-hardware-tests](transactional-hardware-tests/README.md) | 硬件自检的状态快照、恢复与证据边界 | 案例模板、踩坑清单 |

## 交付与使用

每项 `README.md` 写明适用范围、使用方法、失效条件、验证效果和真实问题来源；`SKILL.md` 提供可被智能体发现的入口；`provenance.json` 与 `references/source/` 保留原始依据。脚本类有独立入口，案例/踩坑类按流程适配自己的工程。原始工程未移动或修改。

可独立运行的副本：golden-reference-check、uart-fault-injection、versioned-metrics-report，以及 release-provenance-check 的通用清单校验器。其他目录是可复用方法和原始案例，不宣称原工程专用脚本已经参数化为跨板工具。

本次验证见 [validation.json](validation.json)，打包内容哈希见 [collection_manifest.json](collection_manifest.json)。本次不进行新的 Vivado 综合、RTL 仿真、硬件连接、下载、Flash 擦写或模拟精度验收。历史 PASS 只支持历史版本和当时条件。

当前未实现 PYNQ Overlay/DMA 驱动，也未完成换板复用验证，不将本集合称为“已获得 PYNQ 额外加分”。赛事最终仓库要求 `skill/` 时可按规则将集合目录重命名或复制为 `skill/`，本次按用户要求保留 `skills/`。

## 尚需赛用材料

补充真实大模型协作记录（提示词、回答和自我纠错轨迹），不要编造历史对话。主作品仍需完整 FPGA 工程、实现报告、真实上板证据和设计报告。原始来源包含第三方/IP 模型接口时按对应许可处理；未擅自替整个原项目声明许可证，也未打包厂商 DLL、IP 二进制或位流。
