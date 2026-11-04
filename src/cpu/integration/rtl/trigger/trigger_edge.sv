`default_nettype none
module trigger_edge (
  input wire logic clk, rst, enable, sample_valid, rising,
  input wire scope_pkg::adc_sample_t sample_signed, threshold,
  input wire logic [12:0] hysteresis,
  output wire logic trigger_hit,
  output logic qualified
);
  timeunit 1ns;timeprecision 1ps;
  logic signed [14:0] value_ext,low_level,high_level;
  always_comb begin
    value_ext=$signed({{2{sample_signed[12]}},sample_signed});
    low_level=$signed({{2{threshold[12]}},threshold})-$signed({2'b00,hysteresis});
    high_level=$signed({{2{threshold[12]}},threshold})+$signed({2'b00,hysteresis});
  end
  // Strict crossing prevents flat threshold data firing when hysteresis=0.
  assign trigger_hit=!rst && enable && sample_valid && qualified &&
    (rising ? (value_ext>high_level) : (value_ext<low_level));
  always_ff @(posedge clk)begin
    if(rst || !enable)qualified<=1'b0;
    else if(sample_valid)begin
      if(trigger_hit)qualified<=1'b0;
      else if(rising ? (value_ext<=low_level) : (value_ext>=high_level))qualified<=1'b1;
    end
  end
endmodule
`default_nettype wire
