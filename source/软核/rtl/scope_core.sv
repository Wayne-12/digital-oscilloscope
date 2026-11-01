`default_nettype none
module scope_core (
  input wire logic clk_sample,
  input wire logic arst,
  input wire logic clock_locked,
  input wire logic module_enable,
  input wire logic clock_restart,
  output wire logic dac_data_oe,
  output wire logic dac_clk_oe,
  output wire logic adc_clk_oe,
  output logic capture_enable = 1'b0,
  output wire scope_pkg::dac_code_t dac_data,
  output wire scope_pkg::safe_state_t state,
  output wire logic core_rst,
  output wire logic enable_qualified
);
  timeunit 1ns;
  timeprecision 1ps;
  wire logic emergency;
  wire logic data_oe_reg, dac_oe_reg, adc_oe_reg, capture_reg;
  // The safety qualifier can fall asynchronously to catch a short withdrawal.
  // Only this two-flop sampler may receive it as ordinary internal data.
  (* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) logic [1:0] enable_internal=2'b00;
  always_ff @(posedge clk_sample)
    enable_internal <= {enable_internal[0], enable_qualified && !core_rst};
  assign emergency = arst || !clock_locked;
  scope_reset_sync #(.FALLING_EDGE(1'b1)) reset_sync (
    .clk(clk_sample), .arst(emergency), .rst(core_rst)
  );
  scope_enable_sync enable_sync (
    .clk(clk_sample), .rst(core_rst), .module_enable(module_enable),
    .enable_qualified(enable_qualified)
  );
  scope_safe_ctrl safe_ctrl (
    .clk(clk_sample), .rst(core_rst), .enable_qualified(enable_internal[1]),
    .clock_restart(clock_restart), .dac_data_oe(data_oe_reg),
    .dac_clk_oe(dac_oe_reg), .adc_clk_oe(adc_oe_reg),
    .capture_request(capture_reg), .state(state)
  );
  assign dac_data = scope_pkg::DAC_MID_CODE;
  // core_rst asserts asynchronously and releases after two falling edges.
  // Keep immediate pin isolation without a raw reset/LOCKED combinational bypass.
  assign dac_data_oe = data_oe_reg && !core_rst;
  assign dac_clk_oe = dac_oe_reg && !core_rst;
  assign adc_clk_oe = adc_oe_reg && !core_rst;
  // Ordinary data-path enables change only on a local rising edge. The stop
  // state machine drops capture before disabling the forwarded ADC clock.
  always_ff @(posedge clk_sample) begin
    if(core_rst) capture_enable<=1'b0;
    else capture_enable<=capture_reg && enable_internal[1] && !clock_restart;
  end
endmodule : scope_core
`default_nettype wire
