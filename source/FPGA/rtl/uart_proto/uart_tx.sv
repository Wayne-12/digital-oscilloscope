`default_nettype none
module uart_tx #(parameter int unsigned CLOCK_HZ=100000000,BAUD=115200)(
  input wire logic clk,rst,in_valid,input wire logic [7:0] in_data,
  output wire logic in_ready,output logic tx,done,output logic busy
);
  timeunit 1ns;timeprecision 1ps;
  logic [31:0] phase;
  logic [32:0] advanced;
  logic [9:0] bits;
  logic [3:0] index;
  assign in_ready=!busy && !rst;
  always_comb advanced={1'b0,phase}+33'(BAUD);
  initial assert(BAUD>0 && CLOCK_HZ>=16*BAUD)else $fatal(1,"UART_TX_PARAMETER_FAIL");
  always_ff @(posedge clk)begin
    if(rst)begin phase<=0;bits<=10'h3ff;index<=0;tx<=1;done<=0;busy<=0;end
    else begin
      done<=0;
      if(!busy)begin
        tx<=1;
        if(in_valid)begin bits<={1'b1,in_data,1'b0};index<=0;phase<=0;busy<=1;tx<=0;end
      end else if(advanced>=33'(CLOCK_HZ))begin
        phase<=32'(advanced-33'(CLOCK_HZ));
        if(index==4'd9)begin busy<=0;done<=1;tx<=1;end
        else begin index<=index+4'd1;tx<=bits[index+4'd1];end
      end else phase<=advanced[31:0];
    end
  end
endmodule
`default_nettype wire
