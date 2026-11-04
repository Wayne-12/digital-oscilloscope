# 本次交付验收结果

验收日期：2026-11-03（北京时间）。运行环境：Windows 11、Python 3.14.7，仅标准库。

**总结果：PASS。** 未连接、下载或烧录开发板；未修改原示波器工程。

| 验证项 | 实际结果 |
|---|---|
| 单元测试 | 16 / 16 通过 |
| 通用算法示例 | 统计、非整除包络、独立进程 FIR、FFT 对直接 DFT，4 / 4 通过 |
| 历史示波器 CSV 一致性 | 完整 16384 点，0 处不一致；最大绝对误差 8.881784197001252e-16 V，容差 1e-12 V |
| 错误检出 | 数值错误 FAIL、长度错误 FAIL、缺失结果 ERROR，全部符合预期 |
| 脱离原工程运行 | 仅复制工具源码、示例、测试与脚本到独立临时目录，隔离 Python 启动后全套再次通过 |

报告入口：

- [最终一键验收汇总](reports/20261103T024103_841813Z/verification_summary.json)
- [通用算法 HTML 报告](reports/20261103T024103_841813Z/demo/report.html)
- [历史采集导出 HTML 报告](reports/20261103T024103_841813Z/scope/report.html)
- [故意失败的错误检出报告](reports/20261103T024103_841813Z/negative/report.html)
- [完整单元测试日志](reports/20261103T024103_841813Z/unittest.log)
- [独立目录可移植性证明](reports/portability_20261103T024105_137499Z/portability.json)

`negative/report.html` 的套件总状态为 ERROR 是预期结果。是否验收通过应查看一键汇总中对应检查的 status，而非把故意缺失文件当成实际交付缺陷。

历史 CSV 来源是已有导出的字节级副本，元数据声明“硬件 UART”。本次只证明原始码与标称电压的导出换算一致；不证明新的硬件实测、标定精度、模拟带宽或板端 FFT 正确性。

报告已提供主机参考耗时与外部程序墙钟时间，硬件性能/资源无本次证据时标记 UNAVAILABLE。填写实际指标后可用通用 metrics 接口导入，不能用软件耗时替代硬件延迟。

日后重新验收可运行 `python scripts/verify_all.py`；独立目录验证运行 `python scripts/check_portability.py`。这些运行会产生新的时间戳目录，不自动改写本页的本次交付记录。需要重新打包时运行 `python scripts/package_delivery.py`。
