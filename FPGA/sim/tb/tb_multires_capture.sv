`default_nettype none
module multires_capture_scenario ;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import multires_pkg::*;
  localparam int unsigned LENGTH=16384;
  localparam int unsigned TRIGGER_INDEX=LENGTH/2;
  localparam logic [63:0] FIRST_TS=64'hfffffffffffffff0;
  logic clk=0;always #5 clk=~clk;
  logic rst=1,module_enable=0,start=0;
  wire logic start_ready,busy,metadata_valid,bucket_valid,roi_valid,sample_request,done,config_error,cancelled;
  wire envelope_metadata_t metadata;
  wire envelope_bucket_t bucket;
  wire envelope_roi_t roi;
  wire frame_index_t sample_index,consumed_samples;
  wire logic sample_ready,sample_valid;
  wire logic [15:0] sample_word;
  wire logic frame_available,capture_busy,backend_error;
  wire logic [63:0] backend_timestamp;
  wire logic [31:0] backend_rate,backend_trigger_index,backend_length;
  logic metadata_ready=0,bucket_ready=0,roi_ready=0;
  logic [9:0] cfg_bucket_count=800;
  logic [11:0] cfg_roi_count=1024;
  int unsigned seed=20261020,random_state;
  multires_envelope dut(.clk(clk),.rst(rst),.module_enable(module_enable),.start(start),.start_ready(start_ready),.busy(busy),
    .cfg_sample_count(18'(backend_length)),.cfg_trigger_index(18'(backend_trigger_index)),.cfg_bucket_count(cfg_bucket_count),.cfg_roi_count(cfg_roi_count),
    .cfg_first_timestamp(backend_timestamp),.cfg_sample_rate(backend_rate),.metadata_valid(metadata_valid),.metadata_ready(metadata_ready),.metadata(metadata),
    .bucket_valid(bucket_valid),.bucket_ready(bucket_ready),.bucket(bucket),.roi_valid(roi_valid),.roi_ready(roi_ready),.roi(roi),
    .sample_request(sample_request),.sample_index(sample_index),.sample_ready(sample_ready),.sample_valid(sample_valid),.sample_word(sample_word),
    .done(done),.config_error(config_error),.cancelled(cancelled),.consumed_samples(consumed_samples));
  function automatic logic [15:0] expected_word(input int unsigned i);
    int unsigned raw_code;bit otr;
    raw_code=(i*37+123)%4096;
    otr=(i%17==0 || i==TRIGGER_INDEX);
    return {otr,3'd0,12'(raw_code)};
  endfunction
  generate begin:bram_backend
    wire measurement_result_t measurements;
    wire logic measurement_error,ready;
    uart_capture_backend backend(.clk(clk),.rst(rst),.single_pulse(1'b0),.stop_pulse(1'b0),.release_pulse(1'b0),.acquire_enable(1'b0),
      .pre_samples(18'd8192),.trigger_config(trigger_config_t'('0)),.dds_wave(DDS_DC),.dds_enable(1'b0),
      .dds_phase_inc(32'd0),.dds_phase_offset(32'd0),.dds_amplitude(16'd0),.dds_dc_offset(18'sd0),
      .capture_busy(capture_busy),.capture_ready(ready),.frame_available(frame_available),.backend_error(backend_error),
      .backend_timestamp(backend_timestamp),.backend_rate(backend_rate),.backend_trigger_index(backend_trigger_index),.backend_length(backend_length),
      .measurements(measurements),.measurement_error(measurement_error),.sample_request(sample_request),.sample_index(sample_index),
      .sample_ready(sample_ready),.sample_valid(sample_valid),.sample_word(sample_word));
  end endgenerate
  int unsigned jobs=0,reads_seen=0,buckets_seen=0,roi_seen=0,samples_covered=0,headers_seen=0,job=0;
  int unsigned selected_buckets,selected_roi;
  bit checking=0;
  int bt,rt,ct;
  string traces=".",prefix;
  always @(negedge clk)begin
    random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
    metadata_ready=random_state[2:0]!=0;bucket_ready=random_state[5:3]!=0;roi_ready=random_state[8:6]!=0;
  end
  always @(posedge clk)if(!rst && checking)begin:scoreboard
    int unsigned lo,hi,expected_otr,expected_min_index,expected_max_index;
    int mn,mx,x;logic [15:0] w;
    assert(frame_available && !backend_error && !capture_busy)else $fatal(1,"MULTIRES_FROZEN_OWNERSHIP_ASSERT");
    if(metadata_valid && metadata_ready)begin
      assert(metadata.sample_count==18'(LENGTH) && metadata.trigger_index==18'(TRIGGER_INDEX) && metadata.effective_buckets==10'(selected_buckets) &&
        metadata.first_timestamp==FIRST_TS && metadata.roi_start==18'(TRIGGER_INDEX-selected_roi/2) && metadata.roi_count==12'(selected_roi))else $fatal(1,"MULTIRES_CAPTURE_HEADER_ASSERT");
      headers_seen++;
    end
    if(sample_request && sample_ready)begin
      assert(sample_index==18'(reads_seen) && reads_seen<LENGTH)else $fatal(1,"MULTIRES_CAPTURE_READ_ONCE_ASSERT");reads_seen++;
    end
    if(bucket_valid && bucket_ready)begin
      lo=buckets_seen*LENGTH/selected_buckets;hi=(buckets_seen+1)*LENGTH/selected_buckets-1;
      mn=2048;mx=-2049;expected_min_index=lo;expected_max_index=lo;expected_otr=0;
      for(int unsigned i=lo;i<=hi;i++)begin
        w=expected_word(i);x=2047-int'({20'd0,w[11:0]});
        if(x<mn)begin mn=x;expected_min_index=i;end
        if(x>mx)begin mx=x;expected_max_index=i;end
        expected_otr|=32'(w[15]);
      end
      assert(bucket.bucket_index==10'(buckets_seen) && bucket.first_index==18'(lo) && bucket.last_index==18'(hi) && bucket.sample_count==18'(hi-lo+1) &&
        bucket.minimum===13'(mn) && bucket.maximum===13'(mx) && bucket.minimum_index==18'(expected_min_index) && bucket.maximum_index==18'(expected_max_index) && bucket.otr==1'(expected_otr))
        else $fatal(1,"MULTIRES_CAPTURE_BUCKET_SCOREBOARD backend=%0d job=%0d bucket=%0d",0,job,buckets_seen);
      $fwrite(bt,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",job,buckets_seen,lo,hi,hi-lo+1,mn,mx,expected_min_index,expected_max_index,expected_otr);
      buckets_seen++;samples_covered+=hi-lo+1;
    end
    if(roi_valid && roi_ready)begin
      lo=TRIGGER_INDEX-selected_roi/2+roi_seen;w=expected_word(lo);x=2047-int'({20'd0,w[11:0]});
      assert(roi.roi_index==12'(roi_seen) && roi.frame_index==18'(lo) && roi.raw_word===w && roi.signed_sample===13'(x) && roi.timestamp==FIRST_TS+64'(lo))
        else $fatal(1,"MULTIRES_CAPTURE_ROI_SCOREBOARD backend=%0d job=%0d point=%0d",0,job,roi_seen);
      $fwrite(rt,"%0d,%0d,%0d,%04x,%0d,%016x\n",job,roi_seen,lo,w,x,FIRST_TS+64'(lo));roi_seen++;
    end
  end
  initial begin
    if($value$plusargs("SEED=%d",seed))begin end
    if($value$plusargs("TRACE_DIR=%s",traces))begin end
    random_state=32'(seed)|32'd1;prefix="multires_bram";
    bt=$fopen({traces,"/",prefix,"_buckets.csv"},"w");rt=$fopen({traces,"/",prefix,"_roi.csv"},"w");ct=$fopen({traces,"/",prefix,"_cases.csv"},"w");assert(bt && rt && ct)else $fatal(1,"MULTIRES_CAPTURE_FILES");
    $fwrite(bt,"case,bucket,first,last,count,min,max,min_index,max_index,otr\n");$fwrite(rt,"case,roi_index,frame_index,word,signed,timestamp\n");
    $fwrite(ct,"case,samples,buckets,roi_samples,read_count,response_count,coverage_once\n");
    repeat(100)@(negedge clk);rst=0;module_enable=1;wait(frame_available);
    for(job=0;job<(3);job++)begin
      selected_buckets=job==0?800:job==1?400:100;
      selected_roi=job==0?512:job==1?1024:2048;
      reads_seen=0;buckets_seen=0;roi_seen=0;samples_covered=0;headers_seen=0;checking=1;
      wait(start_ready);@(negedge clk);cfg_bucket_count=10'(selected_buckets);cfg_roi_count=12'(selected_roi);start=1;
      @(negedge clk);start=0;wait(done);@(negedge clk);
      assert(reads_seen==LENGTH && consumed_samples==18'(LENGTH) && buckets_seen==selected_buckets && roi_seen==selected_roi && samples_covered==LENGTH && headers_seen==1 && !config_error && !cancelled)
        else $fatal(1,"MULTIRES_CAPTURE_FINAL_ASSERT");
      $fwrite(ct,"%0d,%0d,%0d,%0d,%0d,%0d,1\n",job,LENGTH,buckets_seen,roi_seen,reads_seen,consumed_samples);
      checking=0;jobs++;
      $display("MULTIRES_CAPTURE_JOB_PASS backend=%0d job=%0d samples=%0d buckets=%0d roi=%0d errors=0",0,job,LENGTH,buckets_seen,roi_seen);
    end
    $fclose(bt);$fclose(rt);$fclose(ct);
    $display("TEST_PASS tb_multires_capture backend=%0d seed=%0d jobs=%0d errors=0",0,seed,jobs);$finish;
  end
  initial begin #200000000;$fatal(1,"MULTIRES_CAPTURE_WATCHDOG backend=%0d state=%0d",0,dut.state);end
endmodule
module tb_multires_bram;
  timeunit 1ns;timeprecision 1ps;
  multires_capture_scenario  scenario();
endmodule
`default_nettype wire
