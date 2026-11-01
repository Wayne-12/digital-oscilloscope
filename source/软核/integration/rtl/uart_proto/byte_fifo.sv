`default_nettype none
module byte_fifo #(parameter int unsigned ADDR_BITS=8)(
  input wire logic clk,rst,in_valid,out_ready,
  input wire logic [7:0] in_data,
  output wire logic in_ready,out_valid,
  output wire logic [7:0] out_data,
  output logic [ADDR_BITS:0] count
);
  timeunit 1ns;timeprecision 1ps;
  logic [7:0] memory[0:(1<<ADDR_BITS)-1];
  logic [ADDR_BITS-1:0] wp,rp;
  wire logic pop=out_valid && out_ready,push=in_valid && in_ready;
  assign out_valid=count!=0 && !rst;
  assign in_ready=!rst && (count<(ADDR_BITS+1)'(1<<ADDR_BITS) || pop);
  assign out_data=memory[rp];
  always_ff @(posedge clk)begin
    if(rst)begin wp<=0;rp<=0;count<=0;end
    else begin
      if(push)begin memory[wp]<=in_data;wp<=wp+1'b1;end
      if(pop)rp<=rp+1'b1;
      case({push,pop})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:begin end endcase
    end
  end
endmodule
`default_nettype wire
