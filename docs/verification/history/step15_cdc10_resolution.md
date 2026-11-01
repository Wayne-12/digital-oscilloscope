> 2026-10-24 工程范围调整：本文涉及的部分旧版报告已完整移至工程外备份，原始 PASS/FAIL 与哈希未改写；历史路径对照见 `docs/verification/历史报告归档说明.md`。本文旧记录不能代替现版工程验证。

# SRAM 捕获就绪位 CDC-10 修正记录

本检查基于暂定 XC7A35T，仅供估算。

原始证据：`FPGA/reports/provisional_synthesis/20261022_225349_106672/sram_capture/artifacts/cdc.rpt`。
Vivado 2025.2 报告 1 条 Critical CDC-10：`ms_reg[2]/C -> can_arm_meta_reg/D`，同步深度为 2。

实际 RTL `FPGA/rtl/capture/sram_capture.sv` 在 ADC 时钟域直接采样 `ms==C_IDLE`。
`ms` 是存储域状态机，译码组合逻辑位于两级同步器前，可能在状态跳转时毛刺。
两级同步器只能降低亚稳态传播概率，不能保证译码毛刺不会被当成有效电平。

修正方案：新增源域寄存器 `can_arm_memory`，由存储域时钟对就绪条件寄存；ADC 域只同步该寄存器。
这会使 ready 的传播多一个存储时钟周期，接口仍通过 `arm_ready` 握手，不改变已接收样本或帧格式。
`can_arm_memory` 使用存储域同步复位，不依赖初值。

```diff
  logic seen_start,seen_abort;
+ logic can_arm_memory;
...
- else begin can_arm_meta<=ms==C_IDLE;can_arm_sync<=can_arm_meta;end
+ else begin can_arm_meta<=can_arm_memory;can_arm_sync<=can_arm_meta;end
...
+ always_ff @(posedge clk_memory) begin
+   if(rst_memory)can_arm_memory<=1'b0;
+   else can_arm_memory<=ms==C_IDLE;
+ end
```

需验证：重跑 SRAM 全空间/多帧/异常测试、系统长记录与紧急撤销用例，再对 `sram_capture` 单独综合和报告 CDC。
通过条件是 CDC-10 消失，其他已审阅的 Gray 指针 CDC-6 与冻结元数据 CDC-15 保留原始报告并说明契约。

验证结果：修正后 CDC-10=0，CDC-3=3，CDC-6=2，CDC-15=411。
SRAM两个种子、重放和7项故障检查全部PASS；系统用例7/8在两个种子下全部PASS。
最终综合及审计入口返回0，报告为 `FPGA/reports/provisional_synthesis/20261022_232236_513872/`。
