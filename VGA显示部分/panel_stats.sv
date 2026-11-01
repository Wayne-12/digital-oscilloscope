`timescale 1ns/1ps
// Both conversions are accumulated. One out-of-range sample selects nominal
// conversion for the entire record, including the waveform and cursors.
module panel_stats(input wire clk,reset,start,valid,finish,otr,
 input wire [11:0] raw,output reg done=0,calibrated=0,complete=0,
 output reg signed [31:0] mean_mv=0,
 output reg [31:0] vpp_mv=0,rms_mv=0,otr_count=0,
 output reg signed [15:0] minimum_mv=0,maximum_mv=0);
 `include "panel_calibration.svh"
 reg active=0,range_ok=0,finish_previous=0;
 reg [14:0] count=0;
 reg signed [31:0] sums[0:1];reg [47:0] squares[0:1];
 reg signed [15:0] lo[0:1],hi[0:1];
 wire signed [15:0] values[0:1];
 assign values[0]=to_mv(raw,0);assign values[1]=to_mv(raw,1);
 wire [31:0] squared[0:1];
 assign squared[0]=$signed(values[0])*$signed(values[0]);
 assign squared[1]=$signed(values[1])*$signed(values[1]);
 reg [31:0] remainder=0,root=0,trial_bit=0;reg [4:0] steps=0;
 wire [31:0] trial=root+trial_bit;
 integer i;
 always @(posedge clk)begin
  done<=0;finish_previous<=finish;
  if(reset)begin active<=0;count<=0;steps<=0;complete<=0;calibrated<=0;finish_previous<=0;end
  else begin
   if(start)begin
    active<=1;range_ok<=1;count<=0;otr_count<=0;steps<=0;complete<=0;
    for(i=0;i<2;i=i+1)begin sums[i]<=0;squares[i]<=0;lo[i]<=32767;hi[i]<=-32768;end
   end else if(active && valid)begin
    count<=count+1'b1;range_ok<=range_ok && raw>=CAL_LOW && raw<=CAL_HIGH;
    if(otr)otr_count<=otr_count+1'b1;
    for(i=0;i<2;i=i+1)begin
     sums[i]<=sums[i]+values[i];squares[i]<=squares[i]+squared[i];
     if(values[i]<lo[i])lo[i]<=values[i];if(values[i]>hi[i])hi[i]<=values[i];
    end
   end
   if(finish && !finish_previous && active)begin
    active<=0;complete<=count==16384;calibrated<=range_ok && count==16384;
    mean_mv<=sums[range_ok]<0 ? -((-sums[range_ok]+8192)>>>14) : ((sums[range_ok]+8192)>>>14);
    minimum_mv<=lo[range_ok];maximum_mv<=hi[range_ok];
    vpp_mv<=$signed(hi[range_ok])-$signed(lo[range_ok]);
    remainder<=squares[range_ok]>>14;root<=0;trial_bit<=32'h40000000;steps<=16;
   end else if(steps!=0)begin
    if(remainder>=trial)begin remainder<=remainder-trial;root<=(root>>1)+trial_bit;end
    else root<=root>>1;
    trial_bit<=trial_bit>>2;steps<=steps-1'b1;
    if(steps==1)begin rms_mv<=remainder>=trial ? (root>>1)+trial_bit : root>>1;done<=1;end
   end
  end
 end
endmodule
