`default_nettype none
module tb_ad9767_fault;
  timeunit 1ns; timeprecision 1ps;
  logic rst,enable,aclk,wr1,bclk,wr2;
  logic [13:0] data;
  wire [13:0] in_code,out_code;
  wire iv,ov;
  integer unsigned edges;
  string fault;
  ad9767_model dut(.rst(rst),.bus_enable(enable),.aclk(aclk),.wr1(wr1),
    .bclk(bclk),.wr2(wr2),.da(data),.input_code(in_code),.dac_code(out_code),
    .input_valid(iv),.dac_valid(ov),.accepted_edges(edges));
  initial begin
    rst=1;enable=0;aclk=0;wr1=0;bclk=0;wr2=0;data=8192;
    if(!$value$plusargs("FAULT=%s",fault))$fatal(1,"TEST_FAIL missing FAULT");
    #5ns;rst=0;enable=1;
    if(fault=="b_unknown")begin bclk=1'bx;#2ns;end
    if(fault=="first_mid")data=8193;
    #5ns;
    aclk=1;
    if(fault!="skew")wr1=1;
    if(fault=="setup")begin
      #5ns;aclk=0;wr1=0;#4ns;data=8193;#1ns;aclk=1;wr1=1;
    end
    #0.5ns;
    if(fault=="hold")data=8193;
    #5ns;
    $fatal(1,"FAULT_NOT_DETECTED %s",fault);
  end
  initial begin #1us;$fatal(1,"FAULT_NOT_DETECTED watchdog");end
endmodule
`default_nettype wire
