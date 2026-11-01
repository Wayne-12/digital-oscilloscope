`default_nettype none
module innovation_capture_scenario #(parameter integer CHANNEL_PROFILE=-1);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import multires_pkg::*;import innovation_pkg::*;import protocol_pkg::*;
  localparam integer N=16384;
  localparam logic [63:0] BASE=64'hfffffffffffffff0;
  logic clk=0,adc_clk=0;always #5ns clk=~clk;always #20ns adc_clk=~adc_clk;
  logic rst=1,enable=0,arm=0,source_valid=0;
  logic [15:0] source_word=0,words[0:N-1];logic [63:0] source_ts=0;
  wire [15:0] channel_word;wire [63:0] channel_timestamp;wire channel_valid;
  logic channel_stop=0;
  generate if(CHANNEL_PROFILE>=0)begin:channel_source
    innovation_channel_source #(.PROFILE(CHANNEL_PROFILE),.N(N)) source(
      .clk(adc_clk),.rst(rst),.stop(channel_stop),.word(channel_word),
      .timestamp(channel_timestamp),.valid(channel_valid));
  end else begin:no_channel_source
    assign channel_word=16'd0;assign channel_timestamp=64'd0;assign channel_valid=1'b0;
  end endgenerate
  trigger_config_t trigger_config;
  wire arm_ready,frame_available,capture_busy,capture_error,read_ready,read_valid;
  wire [15:0] read_word;wire [17:0] read_index;wire request;
  wire [63:0] frame_ts;wire [17:0] frame_trigger,frame_count;
  wire moments_busy,moments_done,moments_error;capture_moments_t stats;
  capture_moments summary(.clk(adc_clk),.rst(rst),.start(arm),.sample_valid(source_valid),.cfg_count(18'(N)),.sample_word(source_word),.sample_timestamp(source_ts),.busy(moments_busy),.done(moments_done),.error(moments_error),.result(stats));
  generate begin:bram_backend
    capture_state_t capture_state;capture_metadata_t frame_metadata;
    wire sd;wire [13:0] write_pointer;wire signed [12:0] decoded;wire [63:0] read_timestamp;
    assign arm_ready=capture_state==CAP_IDLE || capture_state==CAP_SINGLE_HOLD;
    assign read_ready=frame_available;
    bram_capture #(.USE_EXTENDED_TRIGGER(1)) memory(.clk_adc(adc_clk),.rst_adc(rst),.module_enable(enable),.arm(arm),.cfg_mode(CAP_SINGLE),.cfg_rising(1'b1),.cfg_threshold(13'sd0),.cfg_hysteresis(13'd8),.cfg_pre_samples(15'd8192),.cfg_auto_timeout(32'd0),.cfg_trigger(trigger_config),
      .sample_valid(source_valid),.sample_raw(source_word[11:0]),.sample_otr(source_word[15]),.sample_timestamp(source_ts),.capture_state(capture_state),.single_done(sd),.capture_error(capture_error),.busy(capture_busy),.write_pointer(write_pointer),
      .clk_sys(clk),.rst_sys(rst),.read_request(request&&read_ready),.frame_release(1'b0),.read_index(read_index[13:0]),.frame_ready(frame_available),.read_valid(read_valid),.frame_metadata(frame_metadata),.read_word(read_word),.read_signed(decoded),.read_timestamp(read_timestamp));
    assign frame_ts=frame_metadata.first_timestamp;assign frame_trigger={4'd0,frame_metadata.trigger_index};assign frame_count={3'd0,frame_metadata.frame_length};
    always @(posedge clk)if(!rst && request)assert(read_index<18'd16384)else $fatal(1,"INNOVATION_BRAM_RANGE");
  end endgenerate
  logic env_start=0,pack_start=0,uart_start=0;
  wire env_ready,env_busy,emvalid,bvalid,roivalid,env_done,env_error,env_cancel;wire [17:0] consumed;
  envelope_metadata_t emeta;envelope_bucket_t bucket;envelope_roi_t roi;
  wire bready,roiready;
  logic [11:0] roi_count=512;
  multires_envelope envelope(.clk(clk),.rst(rst),.module_enable(enable),.start(env_start),.start_ready(env_ready),.busy(env_busy),.cfg_sample_count(frame_count),.cfg_trigger_index(frame_trigger),.cfg_bucket_count(10'd800),.cfg_roi_count(roi_count),
    .cfg_first_timestamp(frame_ts),.cfg_sample_rate(32'd25000000),.metadata_valid(emvalid),.metadata_ready(1'b1),.metadata(emeta),.bucket_valid(bvalid),.bucket_ready(bready),.bucket(bucket),.roi_valid(roivalid),.roi_ready(roiready),.roi(roi),
    .sample_request(request),.sample_index(read_index),.sample_ready(read_ready),.sample_valid(read_valid),.sample_word(read_word),.done(env_done),.config_error(env_error),.cancelled(env_cancel),.consumed_samples(consumed));
  capture_result_meta_t cfg;wire pack_ready,pack_valid,pack_out_ready,pack_done,pack_error,pack_cancel;wire [7:0] pack_data;wire [31:0] bytes_seen;
  capture_result_stream packer(.clk(clk),.rst(rst),.module_enable(enable),.start(pack_start),.start_ready(pack_ready),.cfg(cfg),.bucket_valid(bvalid),.bucket_ready(bready),.bucket(bucket),.roi_valid(roivalid),.roi_ready(roiready),.roi(roi),.source_done(env_done),
    .out_valid(pack_valid),.out_ready(pack_out_ready),.out_data(pack_data),.done(pack_done),.error(pack_error),.cancelled(pack_cancel),.byte_count(bytes_seen));
  wire uart_ready,uart_valid,uart_done,uart_error;logic uart_out_ready=0;wire [7:0] uart_data;logic [31:0] total_bytes;frame_header_t header;
  capture_result_uart transport(.clk(clk),.rst(rst),.module_enable(enable),.start(uart_start),.start_ready(uart_ready),.cfg_total_bytes(total_bytes),.cfg_header(header),.in_valid(pack_valid),.in_ready(pack_out_ready),.in_data(pack_data),
    .out_valid(uart_valid),.out_ready(uart_out_ready),.out_data(uart_data),.done(uart_done),.error(uart_error));
  integer seed=20261020,unused,job,reads_seen,roi_seen,buckets_seen,wire_count,container_count,packet_file,container_file,meta_file,cycles;
  integer unsigned rng;string vectors,prefix;
  bit checking=0,env_finished,pack_finished,uart_finished;
  logic stall;logic [7:0] held_byte;
  initial begin #200ms;$fatal(1,"INNOVATION_CAPTURE_WATCHDOG backend=%0d",0);end
  always @(negedge clk)begin
    rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};uart_out_ready=rng[2:0]!=0;
  end
  always @(posedge clk)if(!rst && checking)begin
    assert(frame_available&&!capture_busy&&!capture_error&&!moments_error&&!env_error&&!env_cancel&&!pack_error&&!pack_cancel&&!uart_error)else $fatal(1,"INNOVATION_CAPTURE_STATE");
    if(stall)assert(uart_valid&&uart_data==held_byte)else $fatal(1,"INNOVATION_UART_STABILITY");
    stall=uart_valid&&!uart_out_ready;held_byte=uart_data;
    if(request&&read_ready)begin assert(read_index==18'(reads_seen))else $fatal(1,"INNOVATION_READ_ORDER");reads_seen++;end
    if(read_valid)assert(read_word==words[reads_seen-1])else $fatal(1,"INNOVATION_RAW_MEMORY_SCOREBOARD");
    if(roivalid&&roiready)begin
      assert(roi.roi_index==12'(roi_seen)&&roi.frame_index==18'(N/2-integer'(roi_count)/2+roi_seen)&&roi.raw_word==words[roi.frame_index]&&roi.timestamp==BASE+{46'd0,roi.frame_index})else $fatal(1,"INNOVATION_ROI_SCOREBOARD");roi_seen++;
    end
    if(bvalid&&bready)buckets_seen++;
    if(pack_valid&&pack_out_ready)begin $fdisplay(container_file,"%02x",pack_data);container_count++;end
    if(uart_valid&&uart_out_ready)begin $fdisplay(packet_file,"%02x",uart_data);wire_count++;end
    if(env_done)env_finished=1;if(pack_done)pack_finished=1;if(uart_done)uart_finished=1;
  end
  initial begin
    unused=$value$plusargs("SEED=%d",seed);rng=32'(seed)|1;trigger_config='0;trigger_config.kind=TRIG_OTR;cfg='0;header='0;stall=0;held_byte=0;
    if(!$value$plusargs("VECTOR_DIR=%s",vectors))$fatal(1,"CAPTURE_VECTOR_PATH");prefix="innovation_bram";
    if(CHANNEL_PROFILE<0)$readmemh({vectors,"/bram_words.hex"},words);
    else prefix=$sformatf("%s_channel%0d",prefix,CHANNEL_PROFILE);
    meta_file=$fopen({prefix,"_jobs.csv"},"w");$fdisplay(meta_file,"job,count,trigger,roi_start,roi_count,container_bytes,wire_bytes,crc32");
    repeat(100)@(negedge clk);rst=0;enable=1;wait(arm_ready);
    @(negedge adc_clk);arm=1;@(negedge adc_clk);arm=0;
    if(CHANNEL_PROFILE>=0)begin
      // Model output is stable here; forward every captured ADC sample with
      // an explicit one-edge verification adapter, retaining its raw code/OTR.
      while(!channel_valid || channel_timestamp<64'd128)@(negedge adc_clk);
      for(integer i=0;i<N;i++)begin
        assert(channel_valid && channel_timestamp==64'd128+64'(i))else $fatal(1,"INNOVATION_CHANNEL_SOURCE_GAP");
        source_valid=1;source_word=channel_word;words[i]=channel_word;source_ts=BASE+64'(i);
        @(negedge adc_clk);
      end
      channel_stop=1;
    end else for(integer i=0;i<N;i++)begin source_valid=1;source_word=words[i];source_ts=BASE+64'(i);@(negedge adc_clk);end
    source_valid=0;
    wait(frame_available);wait(!moments_busy);assert(frame_count==18'(N)&&frame_trigger==18'(N/2)&&frame_ts==BASE&&stats.count==18'(N))else $fatal(1,"INNOVATION_FROZEN_METADATA");
    for(job=0;job<3;job++)begin
      wait(env_ready&&pack_ready&&uart_ready);@(negedge clk);
      roi_count=job==0?12'd512:job==1?12'd1024:12'd2048;
      cfg='0;cfg.result_id=32'(job);cfg.reserved_storage=0;cfg.sample_count=18'(N);cfg.trigger_index=18'(N/2);cfg.roi_start=18'(N/2-integer'(roi_count)/2);cfg.roi_count=roi_count;cfg.bucket_count=800;
      if(CHANNEL_PROFILE>=0)cfg.result_id=cfg.result_id|(32'(CHANNEL_PROFILE+1)<<8);
      cfg.sample_rate=25000000;cfg.moments=stats;total_bytes=32'd137+32'd11200+32'(roi_count)*32'd3;
      header='0;header.seq=16'd65530;header.timestamp=BASE;header.sample_rate=cfg.sample_rate;header.trigger_index=32'(N/2);
      reads_seen=0;roi_seen=0;buckets_seen=0;wire_count=0;container_count=0;cycles=0;env_finished=0;pack_finished=0;uart_finished=0;stall=0;
      packet_file=$fopen($sformatf("%s_job%0d_uart.hex",prefix,job),"w");container_file=$fopen($sformatf("%s_job%0d_container.hex",prefix,job),"w");checking=1;
      env_start=1;pack_start=1;uart_start=1;@(negedge clk);env_start=0;pack_start=0;uart_start=0;
      while(!env_finished||!pack_finished||!uart_finished)begin @(negedge clk);cycles++;assert(cycles<5000000)else $fatal(1,"INNOVATION_CAPTURE_TIMEOUT");end
      assert(reads_seen==N&&roi_seen==integer'(roi_count)&&buckets_seen==800&&consumed==18'(N)&&bytes_seen==total_bytes&&container_count==integer'(total_bytes)&&wire_count==container_count+32*((container_count+1019)/1020))else $fatal(1,"INNOVATION_CAPTURE_COUNTS");
      checking=0;$fclose(packet_file);$fclose(container_file);
      $fdisplay(meta_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%08x",job,N,N/2,cfg.roi_start,roi_count,container_count,wire_count,stats.raw_crc32);
      $display("INNOVATION_CAPTURE_JOB_PASS backend=%0d job=%0d samples=%0d roi=%0d container=%0d wire=%0d errors=0",0,job,N,roi_count,container_count,wire_count);
    end
    $fclose(meta_file);$display("TEST_PASS tb_innovation_capture backend=%0d seed=%0d jobs=3 errors=0",0,seed);$finish;
  end
endmodule
module tb_innovation_bram;timeunit 1ns;timeprecision 1ps;innovation_capture_scenario scenario();endmodule

// Additional connected inputs; fixed-vector spike tests above remain intact.
module tb_innovation_bram_channel0;timeunit 1ns;timeprecision 1ps;innovation_capture_scenario #(.CHANNEL_PROFILE(0)) scenario();endmodule
module tb_innovation_bram_channel1;timeunit 1ns;timeprecision 1ps;innovation_capture_scenario #(.CHANNEL_PROFILE(1)) scenario();endmodule
module tb_innovation_bram_channel2;timeunit 1ns;timeprecision 1ps;innovation_capture_scenario #(.CHANNEL_PROFILE(2)) scenario();endmodule
module tb_innovation_bram_channel3;timeunit 1ns;timeprecision 1ps;innovation_capture_scenario #(.CHANNEL_PROFILE(3)) scenario();endmodule

module innovation_channel_source #(parameter integer PROFILE=0,N=16384)(
  input wire logic clk,rst,stop,
  output wire [15:0] word,output wire [63:0] timestamp,output wire valid
);
  timeunit 1ns;timeprecision 1ps;
  localparam integer GAIN=PROFILE==1?24576:PROFILE==2?12288:PROFILE==3?32768:16384;
  localparam integer OFFSET=PROFILE==1?37:PROFILE==2?-23:0;
  logic model_rst=1,dac_valid=0;logic [13:0] code=8192;logic force_otr=0;
  wire signed [31:0] ideal;wire cv,clip,fe,fv,av,otr,cotr;wire [11:0] raw,craw;wire signed [12:0] cs;
  integer tick=0,fd;string name;
  function automatic logic [13:0] stimulus(input integer k);
    integer x;
    x=k%256<128?-600+10*(k%128):600-10*(k%128);
    if(k%113==17)x=5000;else if(k%127==29)x=-5000;
    return 14'(8192+x);
  endfunction
  loopback_channel_model #(.GAIN_Q16(GAIN),.OFFSET_LSB(OFFSET),.INVERT(PROFILE==2),
    .NOISE_LSB(PROFILE==2?3:0),.DELAY_SAMPLES(PROFILE==2?2:0),.FRACTION_Q16(PROFILE==2?16384:0),
    .LPF_ALPHA_Q16(PROFILE==2?32768:65536),.CLIP_ENABLE(PROFILE==3),.CLIP_LOW(-700),.CLIP_HIGH(700)) channel(
    .clk_sample(clk),.rst(model_rst),.dac_code(code),.dac_valid(dac_valid),.noise_seed(32'd12345),
    .force_otr_enable(force_otr),.force_otr_value(1'b1),.ideal_sample(ideal),.sample_valid(cv),.channel_clipped(clip),
    .adc_force_otr_enable(fe),.adc_force_otr_value(fv));
  ad9226_model #(.T_CO_NS(PROFILE%2==0?3.5:7.0)) adc(.adc_clk(clk),.rst(model_rst),.ideal_sample(ideal),
    .noise_seed(32'd1),.force_otr_enable(fe),.force_otr_value(fv),.raw_code(raw),.otr(otr),.output_valid(av));
  adc_capture capture(.clk_sample(clk),.rst(model_rst),.capture_enable(!model_rst),.adc_data(raw),.adc_otr(otr),
    .sample_valid(valid),.sample_raw(craw),.sample_signed(cs),.sample_otr(cotr),.sample_timestamp(timestamp));
  assign word={cotr,3'b000,craw};
  initial begin
    name=$sformatf("innovation_%s_channel%0d_source.csv","bram",PROFILE);
    fd=$fopen(name,"w");assert(fd!=0)else $fatal(1,"INNOVATION_CHANNEL_TRACE_OPEN");
    $fdisplay(fd,"cycle,dac,ideal,channel_valid,clipped,force_enable,force_value,capture_valid,raw,otr,timestamp");
    wait(!rst);@(posedge clk);#1ns;model_rst=0;dac_valid=1;code=stimulus(0);
    while(!stop)begin
      @(posedge clk);#1ps;
      $fdisplay(fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",tick,code,ideal,cv,clip,fe,fv,valid,craw,cotr,timestamp);
      assert(valid==(tick>=8) && (!valid || cs==13'(2047-integer'({20'd0,craw}))))else $fatal(1,"INNOVATION_CHANNEL_ENCODING");
      #999ps;tick++;code=stimulus(tick);force_otr=tick==128+N/2;
    end
    model_rst=1;dac_valid=0;$fclose(fd);
  end
endmodule
`default_nettype wire
