`default_nettype none
// Hardware-only wrapper. Core tests supply ideal clocks directly to scope_core.
// scope_clk_wiz is a Vivado 2025.2 Clocking Wizard IP (100 MHz -> 25 MHz).
module scope_hw_top (
  input wire logic sys_clk_100,
  input wire logic arst,
  input wire logic module_enable,
  output wire [13:0] dac_da,
  output wire dac_aclk,
  output wire dac_wr1,
  output wire adc_clk,
  output wire logic capture_enable
);
  timeunit 1ns;
  timeprecision 1ps;
  wire clk_sample, clock_locked;
  wire dac_data_oe, dac_clk_oe, adc_clk_oe;
  wire [13:0] dac_data;
  wire forwarded_dac, forwarded_wr1, forwarded_adc;
  wire dac_forward_reset, adc_forward_reset;
  // Hold the ODDR Q nodes low throughout high-Z. Without this, exposing an
  // already-high free-running Q can create a Z->1 edge before the next clock.
  // OE assertion/release happens in the low phase; C remains a BUFG clock.
  assign dac_forward_reset = arst || !dac_clk_oe;
  assign adc_forward_reset = arst || !adc_clk_oe;
  scope_clk_wiz clock_wizard (
    .clk_in1(sys_clk_100), .reset(arst),
    .clk_out1(clk_sample), .locked(clock_locked)
  );
  scope_core core (
    .clk_sample(clk_sample), .arst(arst), .clock_locked(clock_locked),
    .module_enable(module_enable), .clock_restart(1'b0),
    .dac_data_oe(dac_data_oe), .dac_clk_oe(dac_clk_oe), .adc_clk_oe(adc_clk_oe),
    .capture_enable(capture_enable), .dac_data(dac_data),
    .state(), .core_rst(), .enable_qualified()
  );
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .SRTYPE("ASYNC"), .INIT(1'b0)) dac_oddr (
    .C(clk_sample), .CE(1'b1), .D1(1'b1), .D2(1'b0), .R(dac_forward_reset), .S(1'b0), .Q(forwarded_dac)
  );
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .SRTYPE("ASYNC"), .INIT(1'b0)) wr1_oddr (
    .C(clk_sample), .CE(1'b1), .D1(1'b1), .D2(1'b0), .R(dac_forward_reset), .S(1'b0), .Q(forwarded_wr1)
  );
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .SRTYPE("ASYNC"), .INIT(1'b0)) adc_oddr (
    .C(clk_sample), .CE(1'b1), .D1(1'b1), .D2(1'b0), .R(adc_forward_reset), .S(1'b0), .Q(forwarded_adc)
  );
  for (genvar bit_index = 0; bit_index < 14; bit_index++) begin : g_dac_data
    OBUFT data_buffer (.I(dac_data[bit_index]), .T(!dac_data_oe), .O(dac_da[bit_index]));
  end
  OBUFT dac_buffer (.I(forwarded_dac), .T(!dac_clk_oe), .O(dac_aclk));
  OBUFT wr1_buffer (.I(forwarded_wr1), .T(!dac_clk_oe), .O(dac_wr1));
  OBUFT adc_buffer (.I(forwarded_adc), .T(!adc_clk_oe), .O(adc_clk));
endmodule : scope_hw_top
`default_nettype wire
