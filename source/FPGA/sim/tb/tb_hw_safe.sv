`default_nettype none
// Separate integration test with real Clocking Wizard / UNISIM primitives.
module tb_hw_safe;
  timeunit 1ns;
  timeprecision 1ps;
  wire sys_clk;
  logic arst, module_enable, checking;
  wire [13:0] dac_da;
  wire dac_aclk, dac_wr1, adc_clk, capture_enable;
  int unsigned dac_edges, adc_edges, startups, clock_checks, pulse_checks;
  realtime dac_last_rise, dac_last_fall, adc_last_rise, adc_last_fall;
  // ODDR.v in the installed UNISIM library specifies C->Q = 100 ps.
  // A Z->0 interval starts at OE assertion; its first rise includes that
  // delay. Subsequent complete high/low intervals each remain exactly 20 ns.
  localparam realtime UNISIM_CQ_NS = 0.100;
  ideal_clock clock100 (.frequency_hz(32'd100000000), .clk(sys_clk));
  scope_hw_top dut (
    .sys_clk_100(sys_clk), .arst(arst), .module_enable(module_enable),
    .dac_da(dac_da), .dac_aclk(dac_aclk), .dac_wr1(dac_wr1),
    .adc_clk(adc_clk), .capture_enable(capture_enable)
  );
  task automatic check_hiz();
    assert (dac_da === 14'bz && dac_aclk === 1'bz && dac_wr1 === 1'bz &&
            adc_clk === 1'bz && capture_enable === 1'b0)
      else $fatal(1, "TEST_FAIL hardware wrapper not high-Z");
  endtask
  task automatic await_safe();
    for (int unsigned index = 0; index < 8; index++) begin
      @(posedge dut.clk_sample);
      #5ps;
      if (dut.core.state === scope_pkg::SAFE_HIZ) begin check_hiz(); return; end
    end
    $fatal(1, "TEST_FAIL hardware-wrapper shutdown deadlock");
  endtask
  task automatic check_clock_interval(input realtime width_ns, input realtime expected_ns,
                                       input string signal_name);
    pulse_checks++;
    assert (width_ns >= expected_ns - 0.0011 && width_ns <= expected_ns + 0.0011)
      else $fatal(1, "TEST_FAIL %s width=%0f ns, expected %0f ns", signal_name, width_ns, expected_ns);
  endtask
  always @(posedge dut.dac_data_oe) begin
    dac_edges = 0;
    adc_edges = 0;
    dac_last_rise = -1.0;
    dac_last_fall = -1.0;
    adc_last_rise = -1.0;
    adc_last_fall = -1.0;
    #2ps;
    assert (dac_da === 14'd8192) else $fatal(1, "TEST_FAIL real OBUFT data code");
  end
  always @(posedge dac_aclk) begin
    if (dac_aclk === 1'b1) begin
      dac_edges++;
      if (dac_last_fall >= 0.0)
        check_clock_interval($realtime - dac_last_fall,
                             (dac_edges == 1) ? 20.0 + UNISIM_CQ_NS : 20.0, "ACLK low");
      dac_last_rise = $realtime;
      #2ps;
      assert (dac_wr1 === 1'b1) else $fatal(1, "TEST_FAIL real ODDR ACLK/WR1 mismatch");
    end
  end
  always @(negedge dac_aclk) begin
    if (checking && !arst && dut.clock_locked && dut.dac_clk_oe && dac_aclk === 1'b0) begin
      if (dac_last_rise >= 0.0) check_clock_interval($realtime - dac_last_rise, 20.0, "ACLK high");
      dac_last_fall = $realtime;
    end
  end
  always @(posedge adc_clk) begin
    if (adc_clk === 1'b1) begin
      adc_edges++;
      if (adc_last_fall >= 0.0)
        check_clock_interval($realtime - adc_last_fall,
                             (adc_edges == 1) ? 20.0 + UNISIM_CQ_NS : 20.0, "ADC CLK low");
      adc_last_rise = $realtime;
      assert (dac_edges >= 16) else $fatal(1, "TEST_FAIL real ADC output started early");
    end
  end
  always @(negedge adc_clk) begin
    if (checking && !arst && dut.clock_locked && dut.adc_clk_oe && adc_clk === 1'b0) begin
      if (adc_last_rise >= 0.0) check_clock_interval($realtime - adc_last_rise, 20.0, "ADC CLK high");
      adc_last_fall = $realtime;
    end
  end
  always @(dac_aclk or dac_wr1) begin
    #2ps;
    if (checking) begin
      assert (dac_aclk === dac_wr1) else $fatal(1, "TEST_FAIL ACLK/WR1 phase or high-Z mismatch");
    end
  end
  always @(dut.dac_clk_oe or dut.adc_clk_oe) begin
    #2ps;
    if (checking && !arst && dut.clock_locked && !dut.core.core_rst) begin
      assert (dut.clk_sample === 1'b0) else $fatal(1, "TEST_FAIL real clock OE changed in high phase");
    end
  end
  always @(posedge capture_enable) begin
    assert (adc_edges == 256) else $fatal(1, "TEST_FAIL real ADC wait count=%0d", adc_edges);
    startups++;
  end
  // Check the actual BUFG output at both phases and every core clock port.
  always @(dut.clk_sample) begin
    #2ps;
    if (checking && dut.clock_locked) begin
      assert (dut.core.reset_sync.clk === dut.clock_wizard.inst.clkout1_buf.O &&
              dut.core.enable_sync.clk === dut.clock_wizard.inst.clkout1_buf.O &&
              dut.core.safe_ctrl.clk === dut.clock_wizard.inst.clkout1_buf.O)
        else $fatal(1, "TEST_FAIL core clock differs from real Wizard BUFG output");
      clock_checks++;
    end
  end
  initial begin
    arst = 1'b1;
    module_enable = 1'b1;
    checking = 1'b0;
    dac_edges = 0;
    adc_edges = 0;
    startups = 0;
    clock_checks = 0;
    pulse_checks = 0;
    dac_last_rise = -1.0;
    dac_last_fall = -1.0;
    adc_last_rise = -1.0;
    adc_last_fall = -1.0;
    #200ns;
    checking = 1'b1;
    check_hiz();
    arst = 1'b0;
    wait (capture_enable === 1'b1);
    #5ps;
    module_enable = 1'b0;
    await_safe();
    module_enable = 1'b1;
    wait (capture_enable === 1'b1);
    #1ns;
    arst = 1'b1;
    #5ps;
    check_hiz();
    assert (startups == 2 && clock_checks > 1000 && pulse_checks > 2000)
      else $fatal(1, "TEST_FAIL wrapper test incomplete");
    $display("WRAPPER_SIM_PASS ODDR=3 OBUFT=17 startups=%0d BUFG_clock_checks=%0d", startups, clock_checks);
    $display("CLOCK_PULSE_PASS rate=25000000 half_period_ns=20 checks=%0d", pulse_checks);
    $display("TEST_PASS tb_hw_safe assertions_failed=0");
    $finish;
  end
  initial begin
    #100us;
    $fatal(1, "TEST_FAIL tb_hw_safe timeout");
  end
endmodule : tb_hw_safe
`default_nettype wire
