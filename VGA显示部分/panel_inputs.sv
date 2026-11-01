`timescale 1ns/1ps
module panel_inputs #(parameter CLOCK_HZ=25000000,DEBOUNCE=250000)(
 input wire clk,reset,input wire [9:0] pins,
 output reg [9:0] filtered=0,output reg [31:0] milliseconds=0);
 (* ASYNC_REG="TRUE" *) reg [9:0] meta=0,sync=0;
 reg [$clog2(DEBOUNCE+1)-1:0] count[0:9];
 reg [$clog2(CLOCK_HZ/1000)-1:0] tick=0;
 integer i;
 always @(posedge clk)begin
  meta<=pins;sync<=meta;
  if(reset)begin
   meta<=0;sync<=0;filtered<=0;milliseconds<=0;tick<=0;
   for(i=0;i<10;i=i+1)count[i]<=0;
  end else begin
   if(tick==CLOCK_HZ/1000-1)begin tick<=0;milliseconds<=milliseconds+1'b1;end
   else tick<=tick+1'b1;
   for(i=0;i<10;i=i+1)begin
    if(sync[i]==filtered[i])count[i]<=0;
    else if(count[i]==DEBOUNCE-1)begin filtered[i]<=sync[i];count[i]<=0;end
    else count[i]<=count[i]+1'b1;
   end
  end
 end
endmodule
