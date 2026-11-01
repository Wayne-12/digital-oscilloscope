`default_nettype none
module tb_spectrum_control #(parameter integer BAD=0);
  timeunit 1ns;timeprecision 1ps;
  import spectrum_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,enable=1,start=0,svalid=0,slast=0,mready=1,bready=0,rready=0;
  logic [31:0] rate=25000000;
  logic [17:0] source_index=0;
  logic [63:0] timestamp=0;
  wire ready,sready,mvalid,bvalid,rvalid,error,cancelled;
  spectrum_metadata_t meta;spectrum_bin_t bin_data;spectrum_result_t result;
  spectrum_analyzer dut(.clk(clk),.rst(rst),.module_enable(enable),.start(start),.start_ready(ready),
    .cfg_hann(1'b0),.cfg_sample_rate(rate),.cfg_first_timestamp(64'd0),.cfg_source_first_index(source_index),.cfg_threshold_q16(32'd131072),
    .sample_valid(svalid),.sample_ready(sready),.sample_signed(13'sd0),.sample_otr(1'b0),.sample_timestamp(timestamp),.sample_last(slast),
    .metadata_valid(mvalid),.metadata_ready(mready),.metadata(meta),.bin_valid(bvalid),.bin_ready(bready),.bin_data(bin_data),
    .result_valid(rvalid),.result_ready(rready),.result(result),.config_error(error),.cancelled(cancelled));
  integer sent,received,cycles,phase,kind,controls=0,recoveries=0;
  bit hit,accepted;
  task automatic launch;
    while(!ready)@(negedge clk);start=1;@(negedge clk);start=0;
  endtask
  // Stop at seven independently observable handshake/processing phases.
  task automatic run_until(input integer stop_phase);
    sent=0;received=0;cycles=0;hit=0;
    while(!hit)begin
      svalid=sent<1024;timestamp=64'(sent);slast=sent==1023;
      bready=stop_phase!=3;rready=stop_phase<0;mready=stop_phase!=1;
      @(posedge clk);accepted=svalid&&sready;
      if(accepted)sent++;
      if(bvalid&&bready)begin
        assert(bin_data.index==11'(received)&&bin_data.power==64'd0&&bin_data.real_part==32'sd0&&bin_data.imag_part==32'sd0)else $fatal(1,"CONTROL_ZERO_BIN");received++;
      end
      if(stop_phase<0&&rvalid&&rready)begin
        assert(!result.measurement_valid&&result.frequency_hz==0&&result.amplitude_q16==0&&received==1024&&sent==1024)else $fatal(1,"CONTROL_ZERO_RESULT");hit=1;
      end
      @(negedge clk);
      case(stop_phase)
        0:hit=dut.wrapper.state==1; // config valid
        1:hit=mvalid&&sent>=32;    // stalled frame metadata
        2:hit=sent>=64;            // partial input
        3:hit=bvalid;              // output stalled
        4:hit=dut.state==4;        // amplitude square root
        5:hit=dut.state==6;        // RMS square root
        6:hit=rvalid;              // result stalled
        default:begin end
      endcase
      cycles++;assert(cycles<100000)else $fatal(1,"CONTROL_TIMEOUT phase=%0d",stop_phase);
    end
    svalid=0;
  endtask
  initial begin #100ms;$fatal(1,"CONTROL_WATCHDOG");end
  initial begin
    repeat(6)@(negedge clk);rst=0;
    if(BAD!=0)begin
      launch();svalid=1;timestamp=BAD==2?64'd1:64'd0;slast=BAD==1;
      repeat(100)@(negedge clk);$fatal(1,"NEGATIVE_TEST_DID_NOT_FIRE");
    end
    // Invalid configuration must be rejected without starting an IP frame.
    rate=0;launch();assert(error&&!mvalid)else $fatal(1,"CONTROL_BAD_RATE");
    rate=25000000;source_index=18'd130049;launch();assert(error&&!mvalid)else $fatal(1,"CONTROL_BAD_RANGE");source_index=0;
    for(kind=0;kind<2;kind++)begin
      for(phase=0;phase<7;phase++)begin
        mready=1;launch();run_until(phase);
        if(kind==0)enable=0;else rst=1;
        repeat(6)@(negedge clk);
        assert(!mvalid&&!bvalid&&!rvalid&&!sready)else $fatal(1,"CONTROL_ABORT_OUTPUTS");
        enable=1;rst=0;repeat(6)@(negedge clk);mready=1;
        launch();run_until(-1);recoveries++;controls++;
        $display("SPECTRUM_CONTROL_POINT_PASS reset=%0d phase=%0d",kind,phase);
      end
    end
    $display("TEST_PASS tb_spectrum_control controls=%0d recoveries=%0d invalid=2 errors=0",controls,recoveries);$finish;
  end
endmodule
`default_nettype wire
