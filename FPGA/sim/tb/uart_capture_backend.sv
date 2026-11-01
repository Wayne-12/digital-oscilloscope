`default_nettype none
// Verification adapter only. Reuses real capture RAM, trigger, measurement and
// DDS RTL. Its task-based arm/config crossing is NOT a hardware CDC circuit.
module uart_capture_backend(
  input wire logic clk,rst,single_pulse,stop_pulse,release_pulse,acquire_enable,
  input wire logic [17:0] pre_samples,
  input wire scope_pkg::trigger_config_t trigger_config,
  input wire scope_pkg::dds_wave_t dds_wave,
  input wire logic dds_enable,
  input wire logic [31:0] dds_phase_inc,dds_phase_offset,
  input wire logic [15:0] dds_amplitude,
  input wire logic signed [17:0] dds_dc_offset,
  output wire logic capture_busy,capture_ready,frame_available,backend_error,
  output wire logic [63:0] backend_timestamp,
  output wire logic [31:0] backend_rate,backend_trigger_index,backend_length,
  output wire scope_pkg::measurement_result_t measurements,
  output wire logic measurement_error,
  input wire logic sample_request,
  input wire logic [17:0] sample_index,
  output wire logic sample_ready,sample_valid,
  output wire logic [15:0] sample_word
);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  logic adc_clk=0;always #20 adc_clk=~adc_clk;
  logic arm,source_valid,initial_fill,filling,start_toggle,seen_toggle;
  logic [14:0] chosen_pre;
  trigger_config_t chosen_trigger;
  adc_raw_t raw;
  logic otr;
  sample_timestamp_t timestamp;
  capture_state_t cap_state;
  capture_metadata_t metadata;
  wire logic busy,cap_error,single_done;
  wire bram_addr_t write_pointer;
  wire adc_sample_t read_signed;
  wire sample_timestamp_t read_timestamp;
  assign capture_busy=busy || filling || start_toggle!=seen_toggle;
  assign capture_ready=!capture_busy && !frame_available && (cap_state==CAP_IDLE || cap_state==CAP_SINGLE_HOLD);
  assign backend_timestamp=metadata.first_timestamp;
  assign backend_rate=32'd25000000;
  assign backend_trigger_index={18'd0,metadata.trigger_index};
  assign backend_length={17'd0,metadata.frame_length};
  assign backend_error=cap_error;
  assign sample_ready=frame_available && !release_pulse;
  bram_capture #(.USE_EXTENDED_TRIGGER(1)) capture(
    .clk_adc(adc_clk),.rst_adc(rst),.module_enable(initial_fill || acquire_enable),.arm(arm),
    .cfg_mode(CAP_SINGLE),.cfg_rising(1'b1),.cfg_threshold(13'sd0),.cfg_hysteresis(13'd8),
    .cfg_pre_samples(chosen_pre),.cfg_auto_timeout(32'd0),.cfg_trigger(chosen_trigger),
    .sample_valid(source_valid),.sample_raw(raw),.sample_otr(otr),.sample_timestamp(timestamp),
    .capture_state(cap_state),.single_done(single_done),.capture_error(cap_error),.busy(busy),.write_pointer(write_pointer),
    .clk_sys(clk),.rst_sys(rst),.read_request(sample_request && sample_ready),.frame_release(release_pulse),
    .read_index(sample_index[13:0]),.frame_ready(frame_available),.read_valid(sample_valid),.frame_metadata(metadata),
    .read_word(sample_word),.read_signed(read_signed),.read_timestamp(read_timestamp));
  always @(posedge clk)begin
    if(rst)start_toggle<=0;else if(single_pulse)start_toggle<=!start_toggle;
    if(!rst && sample_request && sample_ready)begin
      assert(sample_index<18'd16384)else $fatal(1,"UART_BACKEND_INDEX_ASSERT");
      assert(!capture_busy)else $fatal(1,"UART_READ_DURING_CAPTURE_ASSERT");
    end
  end
  task automatic fill_frame(input int unsigned pre,input bit first);
    filling=1;chosen_pre=15'(pre);chosen_trigger=trigger_config;
    if(first)begin chosen_trigger='0;chosen_trigger.kind=TRIG_OTR;end
    @(negedge adc_clk);arm=1;
    @(negedge adc_clk);arm=0;
    for(int unsigned i=0;i<16384;i++)begin
      if(!first && !acquire_enable)break;
      source_valid=1;raw=12'(i*37+123);otr=(i%17==0 || i==pre);
      timestamp=64'hfffffffffffffff0+64'(i);
      @(negedge adc_clk);
    end
    source_valid=0;
    if(first)wait(frame_available);
    else if(acquire_enable)wait(frame_available || !acquire_enable);
    filling=0;
  endtask
  initial begin
    arm=0;source_valid=0;raw=0;otr=0;timestamp=0;initial_fill=1;filling=1;seen_toggle=0;chosen_pre=8192;chosen_trigger='0;
    wait(!rst);fill_frame(8192,1);initial_fill=0;
    forever begin wait(start_toggle!=seen_toggle);seen_toggle=start_toggle;fill_frame(32'(pre_samples),0);end
  end
  logic measure_start,measure_input;
  adc_sample_t measure_x;
  logic [63:0] measure_ts;
  wire logic measure_ready,measure_busy,measure_done,measure_valid;
  measurement_core measure(.clk(clk),.rst(rst),.start(measure_start),.frame_length(18'd16384),.sample_rate_hz(32'd25000000),
    .threshold(13'sd0),.hysteresis(13'd8191),.sample_valid(measure_input),.sample_signed(measure_x),.sample_timestamp(measure_ts),
    .sample_ready(measure_ready),.busy(measure_busy),.measurement_done(measure_done),.measurement_valid(measure_valid),
    .measurement_error(measurement_error),.result(measurements));
  initial begin
    measure_start=0;measure_input=0;measure_x=0;measure_ts=0;wait(!rst);
    @(negedge clk);measure_start=1;@(negedge clk);measure_start=0;
    for(int unsigned i=0;i<16384;i++)begin
      wait(measure_ready);measure_input=1;measure_x=13'sd2047-$signed({1'b0,12'(i*37+123)});measure_ts=64'(i);
      @(negedge clk);
    end
    measure_input=0;wait(measure_done);
    assert(measurements.stats_valid && !measure_valid && !measurement_error)else $fatal(1,"UART_MEASURE_BACKEND_ASSERT");
  end
  wire logic [13:0] dac_code;
  wire logic [31:0] dac_phase;
  wire logic dac_valid;
  dds_core dds(.clk_dac(adc_clk),.rst(rst),.enable(dds_enable),.waveform(dds_wave),.phase_inc(dds_phase_inc),
    .phase_offset(dds_phase_offset),.amplitude(dds_amplitude),.dc_offset(dds_dc_offset),.dac_code(dac_code),.sample_phase(dac_phase),.sample_valid(dac_valid));
  always @(negedge adc_clk)begin
    #0.001;
    if(!rst)begin
    assert(!$isunknown(dac_code))else $fatal(1,"UART_DDS_UNKNOWN_ASSERT");
    if(!dds_enable)assert(dac_code==14'd8192)else $fatal(1,"UART_DDS_SAFE_ASSERT");
    if(dds_enable && dds_wave==DDS_DC && dac_valid)assert(dac_code==14'd8092)else $fatal(1,"UART_DDS_DC_ASSERT");
    end
  end
endmodule
`default_nettype wire
