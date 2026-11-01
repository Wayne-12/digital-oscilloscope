`default_nettype none
// Restoring unsigned divider: 64 clocks, no combinational '/' operator.
module measure_udiv (
  input wire logic clk,rst,start,
  input wire logic [63:0] dividend,divisor,
  output logic busy,done,
  output logic [63:0] quotient,remainder
);
  timeunit 1ns;timeprecision 1ps;
  logic [63:0] numerator,denominator,q;
  logic [64:0] r,trial;
  logic [5:0] index;
  always_comb trial={r[63:0],numerator[index]};
  always_ff @(posedge clk)begin
    if(rst)begin busy<=1'b0;done<=1'b0;quotient<=64'd0;remainder<=64'd0;
      numerator<=64'd0;denominator<=64'd0;q<=64'd0;r<=65'd0;index<=6'd0;end
    else begin
      done<=1'b0;
      if(start && !busy)begin
        numerator<=dividend;denominator<=divisor;q<=64'd0;r<=65'd0;index<=6'd63;busy<=1'b1;
      end else if(busy)begin
        if(trial>={1'b0,denominator})begin r<=trial-{1'b0,denominator};q[index]<=1'b1;end
        else begin r<=trial;q[index]<=1'b0;end
        if(index==6'd0)begin
          busy<=1'b0;done<=1'b1;
          quotient<={q[63:1],trial>={1'b0,denominator}};
          remainder<=64'(trial>={1'b0,denominator}?trial-{1'b0,denominator}:trial);
        end else index<=index-6'd1;
      end
    end
  end
endmodule
`default_nettype wire
