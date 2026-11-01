`default_nettype none
module tb_spectrum_capture;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import multires_pkg::*;import spectrum_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,enable=0,env_start=0,fft_start=0,hann=0;
  wire frame_available,capture_busy,backend_error,measurement_error,capture_ready;
  wire [63:0] backend_timestamp;
  wire [31:0] backend_rate,backend_trigger_index,backend_length;
  measurement_result_t measurements;
  wire request,read_ready,read_valid;
  wire [17:0] read_index;
  wire [15:0] read_word;
  uart_capture_backend backend(.clk(clk),.rst(rst),.single_pulse(1'b0),.stop_pulse(1'b0),.release_pulse(1'b0),.acquire_enable(1'b0),
    .pre_samples(18'd8192),.trigger_config(trigger_config_t'('0)),.dds_wave(DDS_DC),.dds_enable(1'b0),
    .dds_phase_inc(32'd0),.dds_phase_offset(32'd0),.dds_amplitude(16'd0),.dds_dc_offset(18'sd0),
    .capture_busy(capture_busy),.capture_ready(capture_ready),.frame_available(frame_available),.backend_error(backend_error),
    .backend_timestamp(backend_timestamp),.backend_rate(backend_rate),.backend_trigger_index(backend_trigger_index),.backend_length(backend_length),
    .measurements(measurements),.measurement_error(measurement_error),.sample_request(request),.sample_index(read_index),
    .sample_ready(read_ready),.sample_valid(read_valid),.sample_word(read_word));
  wire env_ready,env_busy,emvalid,ebvalid,roivalid,env_done,env_error,env_cancel;
  logic emready=0,ebready=0;
  wire roiready;
  envelope_metadata_t emeta;envelope_bucket_t bucket;envelope_roi_t roi;
  wire [17:0] consumed;
  multires_envelope envelope(.clk(clk),.rst(rst),.module_enable(enable),.start(env_start),.start_ready(env_ready),.busy(env_busy),
    .cfg_sample_count(18'(backend_length)),.cfg_trigger_index(18'(backend_trigger_index)),.cfg_bucket_count(10'd800),.cfg_roi_count(12'd1024),
    .cfg_first_timestamp(backend_timestamp),.cfg_sample_rate(backend_rate),.metadata_valid(emvalid),.metadata_ready(emready),.metadata(emeta),
    .bucket_valid(ebvalid),.bucket_ready(ebready),.bucket(bucket),.roi_valid(roivalid),.roi_ready(roiready),.roi(roi),
    .sample_request(request),.sample_index(read_index),.sample_ready(read_ready),.sample_valid(read_valid),.sample_word(read_word),
    .done(env_done),.config_error(env_error),.cancelled(env_cancel),.consumed_samples(consumed));
  wire fft_ready,mvalid,bvalid,rvalid,fft_error,fft_cancel;
  logic mready=0,bready=0,rready=0;
  spectrum_metadata_t meta;spectrum_bin_t bin_data;spectrum_result_t result;
  spectrum_analyzer dut(.clk(clk),.rst(rst),.module_enable(enable),.start(fft_start),.start_ready(fft_ready),
    .cfg_hann(hann),.cfg_sample_rate(backend_rate),.cfg_first_timestamp(backend_timestamp+64'd7680),.cfg_source_first_index(18'd7680),.cfg_threshold_q16(32'd131072),
    .sample_valid(roivalid),.sample_ready(roiready),.sample_signed(roi.signed_sample),.sample_otr(roi.raw_word[15]),.sample_timestamp(roi.timestamp),.sample_last(roi.roi_index==12'd1023),
    .metadata_valid(mvalid),.metadata_ready(mready),.metadata(meta),.bin_valid(bvalid),.bin_ready(bready),.bin_data(bin_data),
    .result_valid(rvalid),.result_ready(rready),.result(result),.config_error(fft_error),.cancelled(fft_cancel));
  integer seed=20261020,unused,cf,f,cid,win,fs,src,eo,ev,ep,ef,ea,er,ed,rc,idx,a,b,received,roi_seen,reads,buckets,cycles,jobs=0;
  integer gr[0:1023],gi[0:1023],input_values[0:1023],input_otrs[0:1023];
  logic [63:0] ts,its[0:1023];
  integer unsigned rng;
  string vectors,expected;
  bit got_result,got_envelope;
  integer bt,rt,pt;
  initial begin #100ms;$fatal(1,"SPECTRUM_CAPTURE_WATCHDOG");end
  initial begin
    unused=$value$plusargs("SEED=%d",seed);rng=32'(seed)|32'd1;
    if(!$value$plusargs("VECTOR_DIR=%s",vectors)||!$value$plusargs("EXPECTED_DIR=%s",expected))$fatal(1,"CAPTURE_PATHS");
    bt=$fopen("spectrum_capture_bins.csv","w");rt=$fopen("spectrum_capture_results.csv","w");pt=$fopen("spectrum_capture_roi.csv","w");
    $fdisplay(bt,"case_id,bin,real,imag,power");$fdisplay(rt,"case_id,valid,peak_bin,frequency_hz,amplitude_q16,rms_q16,dc_mean_q16,clipped,peak_power");
    $fdisplay(pt,"case_id,roi_index,frame_index,signed,otr,timestamp");
    repeat(100)@(negedge clk);rst=0;enable=1;wait(frame_available);
    assert(backend_length==16384&&backend_trigger_index==8192&&backend_timestamp==64'hfffffffffffffff0)else $fatal(1,"CAPTURE_FROZEN_METADATA");
    cf=$fopen({vectors,"/integration_cases.txt"},"r");if(!cf)$fatal(1,"CAPTURE_CASE_OPEN");
    while(!$feof(cf))begin
      rc=$fscanf(cf,"%d %d %d %d %h %d %d %d %d %d %d %d\n",cid,win,fs,src,ts,eo,ev,ep,ef,ea,er,ed);assert(rc==12)else $fatal(1,"CAPTURE_CASE_FORMAT");
      f=$fopen($sformatf("%s/fft_%0d.txt",expected,cid),"r");if(!f)$fatal(1,"CAPTURE_GOLD_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d %d\n",idx,a,b);assert(rc==3&&idx==n)else $fatal(1,"CAPTURE_GOLD_FORMAT");gr[n]=a;gi[n]=b;end $fclose(f);
      f=$fopen($sformatf("%s/samples_%0d.txt",vectors,cid),"r");if(!f)$fatal(1,"CAPTURE_INPUT_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d %d %h\n",idx,a,b,its[n]);assert(rc==4&&idx==n)else $fatal(1,"CAPTURE_INPUT_FORMAT");input_values[n]=a;input_otrs[n]=b;end $fclose(f);
      wait(env_ready&&fft_ready);@(negedge clk);env_start=1;@(negedge clk);env_start=0;
      wait(emvalid);@(negedge clk);
      assert(emeta.roi_start==18'd7680&&emeta.roi_count==12'd1024&&emeta.roi_trigger_index==12'd512)else $fatal(1,"CAPTURE_ROI_METADATA");
      hann=1'(win);fft_start=1;emready=1;@(negedge clk);fft_start=0;emready=0;
      received=0;roi_seen=0;reads=0;buckets=0;cycles=0;got_result=0;got_envelope=0;
      while(!got_result||!got_envelope)begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};mready=rng[0];bready=rng[3:1]!=0;rready=rng[6:4]!=0;ebready=rng[9:7]!=0;
        @(posedge clk);
        assert(frame_available&&!backend_error&&!env_error&&!fft_error&&!env_cancel&&!fft_cancel)else $fatal(1,"CAPTURE_OWNERSHIP");
        if(request&&read_ready)begin assert(read_index==18'(reads))else $fatal(1,"CAPTURE_READ_ORDER");reads++;end
        if(ebvalid&&ebready)buckets++;
        if(roivalid&&roiready)begin
          assert(roi.roi_index==12'(roi_seen)&&roi.frame_index==18'(7680+roi_seen)&&roi.signed_sample==13'(input_values[roi_seen])&&
            roi.raw_word[15]==1'(input_otrs[roi_seen])&&roi.timestamp==its[roi_seen])else $fatal(1,"CAPTURE_ROI_SCOREBOARD");
          $fdisplay(pt,"%0d,%0d,%0d,%0d,%0d,%016x",cid,roi_seen,roi.frame_index,roi.signed_sample,roi.raw_word[15],roi.timestamp);roi_seen++;
        end
        if(mvalid&&mready)assert(meta.source_first_index==18'd7680&&meta.first_timestamp==ts)else $fatal(1,"CAPTURE_FFT_METADATA");
        if(bvalid&&bready)begin
          assert(bin_data.index==11'(received)&&bin_data.last==(received==1023))else $fatal(1,"CAPTURE_BIN_ORDER");
          assert($signed(bin_data.real_part)-gr[received]<=128&&$signed(bin_data.real_part)-gr[received]>=-128&&
            $signed(bin_data.imag_part)-gi[received]<=128&&$signed(bin_data.imag_part)-gi[received]>=-128)else $fatal(1,"CAPTURE_DFT");
          $fdisplay(bt,"%0d,%0d,%0d,%0d,%0d",cid,received,bin_data.real_part,bin_data.imag_part,bin_data.power);received++;
        end
        if(env_done)got_envelope=1;
        if(rvalid&&rready)begin
          assert(result.measurement_valid==1'(ev)&&result.peak_bin==11'(ep)&&result.frequency_hz==32'(ef)&&result.clipped==1'(eo)&&
            $signed(result.dc_mean_q16)==ed&&$signed(result.amplitude_q16)-ea<=8192&&$signed(result.amplitude_q16)-ea>=-8192&&
            $signed(result.rms_q16)-er<=8192&&$signed(result.rms_q16)-er>=-8192)else $fatal(1,"CAPTURE_RESULT");
          $fdisplay(rt,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cid,result.measurement_valid,result.peak_bin,result.frequency_hz,result.amplitude_q16,result.rms_q16,result.dc_mean_q16,result.clipped,result.peak_power);got_result=1;
        end
        @(negedge clk);cycles++;assert(cycles<500000)else $fatal(1,"CAPTURE_JOB_TIMEOUT");
      end
      assert(reads==16384&&buckets==800&&roi_seen==1024&&received==1024&&consumed==18'd16384)else $fatal(1,"CAPTURE_FINAL_COUNTS");
      $display("SPECTRUM_CAPTURE_JOB_PASS case=%0d samples=16384 buckets=800 roi=1024 bins=1024 errors=0",cid);jobs++;
    end
    $fclose(cf);$fclose(bt);$fclose(rt);$fclose(pt);$display("TEST_PASS tb_spectrum_capture seed=%0d jobs=%0d errors=0",seed,jobs);$finish;
  end
endmodule
`default_nettype wire
