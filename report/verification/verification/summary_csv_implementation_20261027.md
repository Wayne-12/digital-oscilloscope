# 汇总报告 CSV 实施与实物验收（2026-10-27）

结论：实物UI导出通过，当前镜像0xA4261027，39帧短时UART证据及真实测量被汇入同一个232行CSV。入口位于UI顶部“汇总 CSV”，原“保存 CSV”继续导出原始波形。

统一列为category、metric、value、unit、status、scope、firmware_build、source、source_sha256、notes。包含设备身份/时间、冻结帧身份、PC名义电压测量、FPGA完整帧测量/整帧饱和/FFT谐波、实际布线后的时序、LUT/FF/BRAM/DSP/IO资源、当前连接与FPGA复位以来错误计数，以及带来源/版本的UART实测报告。所有实现证据按当前版本匹配且发布bitstream哈希一致；找不到报告时明确UNAVAILABLE，不填零。CSV为UTF-8 BOM、原子替换保存。

实物核对：setup8.234ns、hold0.017ns、BRAM13块、DSP42均与实际实现报告一致。通过真实ScopeWindow和COM12采集后点击导出，测量、资源、时序和误码字段齐全。主动构造导出路径失败后串口仍连接，同一会话再次导出成功，结束配置恢复一致。

当前短测：回显89144字节、39帧、SHORT_PASS，错误新增零；不认定正式UART长稳。历史0xA0261026正式记录（回显13418616字节/600.03秒、两小时长稳）标为historical-other-image，不继承到当前固件。原5次command_rejected是任意波形主动拒绝测试，CSV注明它是复位以来累计计数。CRC错误计数不冒充逐位误码率，未测BER明确NOT_MEASURED。

离线122项PC回归通过，包含缺失/过时/错误设备证据、固件哈希篡改、UTF8、分数BRAM和原子保存失败验证。CSV为PC功能，无额外FPGA固件更改；当前A4261027仍仅临时加载，固化须用户指示。

证据：[最终CSV](../../FPGA/reports/summary_hardware/20261027_final/scope_summary.csv)、[实物验收](../../FPGA/reports/summary_hardware/20261027_final/report.json)、[截图](../../FPGA/reports/summary_hardware/20261027_final/ui_summary.png)、[当前UART短测](../../PC/acceptance_runs/awg_summary_smoke_20261027/report.json)。
