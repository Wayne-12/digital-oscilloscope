`timescale 1ns/1ps
// Four horizontal pixels per sample interval. The read pipeline presents B
// throughout an interval; A was prefetched during the preceding interval.
// phase 0 is exactly A; phase 3 advances 3/4 of the way toward B. This is
// display-only interpolation: no acquisition or measurement memory is changed.
module panel_interpolator #(parameter WIDTH=20)(
 input wire clk,reset,enable,input wire [1:0] phase,
 input wire signed [WIDTH-1:0] next_value,
 output reg signed [WIDTH-1:0] value=0);
 reg signed [WIDTH-1:0] left_value=0;
 wire signed [WIDTH:0] delta={next_value[WIDTH-1],next_value}-{left_value[WIDTH-1],left_value};
 wire signed [WIDTH+3:0] fraction=delta*$signed({1'b0,phase});
 wire signed [WIDTH+3:0] interpolated=$signed(left_value)+(fraction>>>2);
 always @(posedge clk)begin
  if(reset)begin left_value<=0;value<=0;end
  else begin
   if(phase==3)left_value<=next_value;
   value<=enable?interpolated:next_value;
  end
 end
endmodule
