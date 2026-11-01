`default_nettype none
// One-entry elastic DISPLAY branch. Raw word/timestamp never pass through math.
module calibration_apply(
  input wire clk,rst,module_enable,
  input wire in_valid,
  output wire in_ready,
  input wire [15:0] in_raw_word,
  input wire [63:0] in_timestamp,
  input wire calibration_valid,
  input wire signed [31:0] correction_q20,offset_q16,
  output logic out_valid,
  input wire out_ready,
  output logic [15:0] out_raw_word,
  output logic [63:0] out_timestamp,
  output logic signed [31:0] display_q16,
  output logic corrected,saturated
);
  timeunit 1ns;timeprecision 1ps;
  logic signed [63:0] value,difference,product,rounded;
  wire signed [12:0] decoded=scope_pkg::adc_raw_to_signed(in_raw_word[11:0]);
  assign in_ready=module_enable && !rst && (!out_valid || out_ready);
  always_comb begin
    value=$signed({{51{decoded[12]}},decoded});
    difference=(value<<<16)-$signed({{32{offset_q16[31]}},offset_q16});
    product=difference*$signed({{32{correction_q20[31]}},correction_q20});
    if(product<0)rounded=-(((-product)+64'sd524288)>>>20);
    else rounded=(product+64'sd524288)>>>20;
    if(!calibration_valid)rounded=value<<<16;
  end
  always_ff @(posedge clk)begin
    if(rst)begin out_valid<=0;out_raw_word<=0;out_timestamp<=0;display_q16<=0;corrected<=0;saturated<=0;end
    else if(!module_enable)begin out_valid<=0;corrected<=0;saturated<=0;end
    else begin
      if(out_valid && out_ready)out_valid<=0;
      if(in_valid && in_ready)begin
        out_valid<=1;out_raw_word<=in_raw_word;out_timestamp<=in_timestamp;corrected<=calibration_valid;
        saturated<=rounded>64'sd2147483647 || rounded< -64'sd2147483648;
        if(rounded>64'sd2147483647)display_q16<=32'sh7fffffff;
        else if(rounded< -64'sd2147483648)display_q16<=32'sh80000000;
        else display_q16<=32'(rounded);
      end
    end
  end
endmodule
`default_nettype wire
