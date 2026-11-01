`default_nettype none
// Pin-only abstraction; no high-impedance value enters core arithmetic.
module scope_pin_model (
  input wire logic clk,
  input wire scope_pkg::dac_code_t dac_data,
  input wire logic dac_data_oe,
  input wire logic dac_clk_oe,
  input wire logic adc_clk_oe,
  output wire [13:0] dac_da,
  output wire dac_aclk,
  output wire dac_wr1,
  output wire adc_clk
);
  timeunit 1ns;
  timeprecision 1ps;
  assign dac_da = dac_data_oe ? dac_data : 14'bz;
  assign dac_aclk = dac_clk_oe ? clk : 1'bz;
  assign dac_wr1 = dac_clk_oe ? clk : 1'bz;
  assign adc_clk = adc_clk_oe ? clk : 1'bz;
endmodule : scope_pin_model
`default_nettype wire
