`default_nettype none
module tb_innovation_control #(parameter integer BAD=0);
  timeunit 1ns;timeprecision 1ps;
  import innovation_pkg::*;import multires_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,en=1,start=0,bv=0,rv=0,sd=0,ready_out=1;
  wire ready,br,rr,ov,done,error,cancelled;wire [7:0] data;wire [31:0] bytes_seen;
  capture_result_meta_t cfg;envelope_bucket_t bucket;envelope_roi_t roi;
  capture_result_stream dut(.clk(clk),.rst(rst),.module_enable(en),.start(start),.start_ready(ready),.cfg(cfg),.bucket_valid(bv),.bucket_ready(br),.bucket(bucket),.roi_valid(rv),.roi_ready(rr),.roi(roi),.source_done(sd),.out_valid(ov),.out_ready(ready_out),.out_data(data),.done(done),.error(error),.cancelled(cancelled),.byte_count(bytes_seen));
  task automatic launch;wait(ready);@(negedge clk);start=1;@(negedge clk);start=0;endtask
  task automatic finish_job;
    bv=1;sd=1;wait(br);@(posedge clk);@(negedge clk);bv=0;wait(done);@(negedge clk);assert(bytes_seen==151)else $fatal(1,"CONTROL_CONTAINER_LENGTH");sd=0;
  endtask
  initial begin #1ms;$fatal(1,"INNOVATION_CONTROL_WATCHDOG");end
  initial begin
    cfg='0;bucket='0;roi='0;cfg.sample_count=512;cfg.sample_rate=25000000;cfg.bucket_count=1;cfg.moments.count=512;cfg.moments.last_timestamp=511;bucket.last_index=511;
    repeat(6)@(negedge clk);rst=0;
    if(BAD!=0)begin
      if(BAD==2)begin cfg.roi_count=512;roi.raw_word=2047;roi.timestamp=1;end else bucket.minimum_index=512;
      launch();if(BAD==1)bv=1;else rv=1;
      repeat(1000)@(negedge clk);$fatal(1,"NEGATIVE_TEST_DID_NOT_FIRE");
    end
    cfg.sample_count=0;launch();assert(error&&!ov)else $fatal(1,"CONTROL_BAD_COUNT");cfg.sample_count=512;
    cfg.roi_start=18'h3ffff;cfg.roi_count=512;launch();assert(error&&!ov)else $fatal(1,"CONTROL_ROI_OVERFLOW");cfg.roi_start=0;cfg.roi_count=0;
    for(integer reset_kind=0;reset_kind<2;reset_kind++)begin
      for(integer phase=0;phase<3;phase++)begin
        launch();
        if(phase==0)repeat(8)@(negedge clk);
        else begin
          bv=1;sd=1;wait(br);@(posedge clk);@(negedge clk);bv=0;
          if(phase==1)wait(dut.state==3&&dut.position==2);else wait(dut.state==4&&dut.position==2);
          @(negedge clk);
        end
        if(reset_kind==0)en=0;else rst=1;bv=0;rv=0;sd=0;
        repeat(4)@(negedge clk);assert(!ov&&!br&&!rr)else $fatal(1,"CONTROL_CANCEL_OUTPUTS");en=1;rst=0;
        launch();finish_job();
      end
    end
    $display("TEST_PASS tb_innovation_control invalid=2 cancels=3 resets=3 recoveries=6 errors=0");$finish;
  end
endmodule
`default_nettype wire
