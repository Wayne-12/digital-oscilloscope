`timescale 1ns/1ps
module tb_mailbox;
 reg clk=0; always #20 clk=~clk;
 reg rst=1,strobe=0,rd=0,wr=0;
 reg [31:0] address=0,wdata=0; wire [31:0] rdata;
 wire ready,hr,br,qv,sv; wire [7:0] qd,sd;
 reg hv=0,bv=0,qr=0,sr=0; reg [7:0] hd=0,bd=0;
 scope_cpu_mailbox dut(.clk(clk),.rst(rst),.io_strobe(strobe),.io_read(rd),.io_write(wr),
 .io_address(address),.io_wdata(wdata),.io_be(4'hf),.io_rdata(rdata),.io_ready(ready),
 .host_valid(hv),.host_data(hd),.host_ready(hr),.backend_valid(bv),.backend_data(bd),.backend_ready(br),
 .request_valid(qv),.request_data(qd),.request_ready(qr),.response_valid(sv),.response_data(sd),.response_ready(sr));
 task read_reg(input [7:0] a, input [31:0] expected);
  @(negedge clk); address=32'hc0000000+a; strobe=1; rd=1;
  #1; if(!ready || rdata!==expected) $fatal(1,"READ a=%h got=%h expected=%h",a,rdata,expected);
  @(negedge clk); strobe=0;rd=0;
 endtask
 task write_reg(input [7:0] a,input [31:0] v);
  @(negedge clk); address=32'hc0000000+a; wdata=v;strobe=1;wr=1;
  #1; if(!ready) $fatal(1,"WRITE blocked");
  @(negedge clk); strobe=0;wr=0;
 endtask
 integer i;
 initial begin
  repeat(4) @(negedge clk); rst=0;
  read_reg(0,32'h53435031); read_reg(4,10);
  // Empty read stalls; it must not advance the FIFO read pointer.
  @(negedge clk); address=32'hc0000008; strobe=1;rd=1;
  repeat(4) begin @(negedge clk); if(ready) $fatal(1,"empty read did not stall"); end
  hv=1;hd=8'h55;
  @(negedge clk); hv=0; #1; if(!ready || rdata!=85) $fatal(1,"stalled read lost data");
  @(negedge clk);strobe=0;rd=0;
  // Fill CPU->backend FIFO, test ready deassertion and byte order.
  for(i=0;i<256;i=i+1) write_reg(12,i);
  read_reg(4,8);
  @(negedge clk);qr=1;
  for(i=0;i<256;i=i+1) begin
   #1; if(!qv || qd!==8'(i)) $fatal(1,"FIFO order %d",i);
   @(negedge clk);
  end
  qr=0; if(qv) $fatal(1,"FIFO did not empty");
  @(negedge clk);bv=1;bd=8'haa;
  @(negedge clk);bv=0;
  read_reg(16,170);write_reg(20,8'h37);
  #1;if(!sv || sd!=8'h37) $fatal(1,"response mismatch");
  @(negedge clk);sr=1;@(negedge clk);sr=0;
  write_reg(24,32'h12345678);read_reg(24,32'h12345678);
  read_reg(252,0);
  @(negedge clk);rst=1;repeat(2) @(negedge clk);rst=0;
  read_reg(4,10);read_reg(24,0);
  $display("MAILBOX_TEST_PASS full, empty, ordering, reset, bidirectional, heartbeat");$finish;
 end
 initial begin #1000000; $fatal(1,"watchdog"); end
endmodule
