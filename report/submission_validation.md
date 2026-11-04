# 提交包校验记录

2026-11-04 完成目录迁移验证：

- PC 离线回归：167 项，全部通过，见 ../sim/results/submission_pc_tests.log。
- 本地 C 测试：通过，见 ../sim/results/submission_c_tests.log。
- MicroBlaze 固件：编译成功，text=25976、data=2、bss=2372 字节。新编译 ELF 与正式 ELF 的 SHA256 均为 f8b0c7508edd8ade16f410476b272140ec48a81d3a7f2a20e3c2cd6494c98cd8。
- 生产源码快照：RELEASE_VERIFIED；正式固化文件：FLASH_IMAGE_VERIFIED。
- 技能集合：333 个文件哈希校验通过。
- 数据表：4 份工作簿，所有工作表已渲染检查；数据区不含说明页、备注列、结论列和单元格批注。40 份 CSV 已去除说明行及说明列。
- 本次未重新运行 FPGA 综合实现，未下载位流，未连接串口或改写 Flash。历史综合实现和上板证据按原记录保留。

系统默认 Python 没有界面依赖。回归采用原工作区 .venv-ui 的 Python，在本机环境加载 Qt。提交包入口会优先使用本地 .venv 或原工作区 .venv-ui；迁移到其他电脑按 README 安装依赖。
