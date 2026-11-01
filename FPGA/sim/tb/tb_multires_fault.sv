`default_nettype none
module tb_multires_fault #(parameter int unsigned BAD=1);
  timeunit 1ns;timeprecision 1ps;
  logic clk=0;always #5 clk=~clk;
  logic rst=1,module_enable=0,start=0,sample_valid=0;
  logic [15:0] sample_word=0;
  wire logic sample_request;
  multires_envelope dut(.clk(clk),.rst(rst),.module_enable(module_enable),.start(start),.start_ready(),.busy(),
    .cfg_sample_count(18'd16),.cfg_trigger_index(18'd8),.cfg_bucket_count(10'd800),.cfg_roi_count(12'd512),.cfg_first_timestamp(64'd0),.cfg_sample_rate(32'd25000000),
    .metadata_valid(),.metadata_ready(1'b1),.metadata(),.bucket_valid(),.bucket_ready(1'b1),.bucket(),.roi_valid(),.roi_ready(1'b1),.roi(),
    .sample_request(sample_request),.sample_index(),.sample_ready(1'b1),.sample_valid(sample_valid),.sample_word(sample_word),.done(),.config_error(),.cancelled(),.consumed_samples());
  initial begin
    repeat(12)@(negedge clk);rst=0;module_enable=1;
    if(BAD==3)begin sample_valid=1;end
    else begin
      start=1;@(negedge clk);start=0;wait(sample_request);
      if(BAD==1)force dut.index=18'h20000;
      else begin wait(dut.state==4'd5);@(negedge clk);sample_word=16'h1000;sample_valid=1;end
    end
    #10000;$fatal(1,"MULTIRES_NEGATIVE_TEST_DID_NOT_FIRE");
  end
endmodule
`default_nettype wire
