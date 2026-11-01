`timescale 1ns/1ps
module tb_interpolator(output reg done=0);
 reg clk=0;always #5 clk=~clk;
 reg reset=1,enable=1;reg [1:0] phase=0;
 reg signed [19:0] next_value=0;wire signed [19:0] value;
 panel_interpolator dut(.clk(clk),.reset(reset),.enable(enable),.phase(phase),.next_value(next_value),.value(value));
 task tick(input integer p,input integer n);
 begin @(negedge clk);phase=p;next_value=n;@(posedge clk);#1;end endtask
 task interval(input integer a,input integer b);
 integer p,expected;begin
  tick(3,a);
  for(p=0;p<4;p=p+1)begin
   tick(p,b);expected=a+(((b-a)*p)>>>2);
   if($signed(value)!==expected)$fatal(1,"interpolation A=%d B=%d phase=%d expected=%d got=%d",a,b,p,expected,$signed(value));
   if($signed(value)<(a<b?a:b) || $signed(value)>(a>b?a:b))$fatal(1,"interpolation overshoot");
  end
 end endtask
 integer i;
 initial begin
  repeat(2)@(negedge clk);reset=0;
  interval(-100,100);interval(100,-100);interval(128,128);
  interval(-22862,22862);interval(22862,-22862);
  interval(0,1600);interval(1600,0);interval(0,0);
  for(i=-128;i<128;i=i+1)interval(i*97,(127-i)*41);
  enable=0;tick(0,-4321);if(value!==-20'sd4321)$fatal(1,"nonzoom bypass");
  tick(3,9000);if(value!==20'sd9000)$fatal(1,"nonzoom phase independent");
  done=1;$display("INTERPOLATION_TEST_PASS");
 end
endmodule
