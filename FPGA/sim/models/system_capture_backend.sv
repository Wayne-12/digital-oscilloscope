`default_nettype none
// Verification-only integration adapter. Command to ADC and frozen-memory
// connectivity is exercised here; cross-domain task controls are NOT hardware
// CDC and this module is never included in Design Sources.
module system_capture_backend #(parameter int CASE_ID=0)(
  input wire logic clk_sys,rst,emergency_enable,
  input wire logic single_pulse,stop_pulse,release_pulse,acquire_enable,
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
  output wire logic [15:0] sample_word,
  output wire scope_pkg::safe_state_t safe_state,
  output wire logic safe_capture,safe_dac_data_oe,safe_dac_clk_oe,safe_adc_clk_oe,
  output wire [13:0] pin_dac,
  output wire pin_aclk,pin_wr1,pin_adc_clk,
  output wire logic live_valid,
  output wire logic [11:0] live_raw,
  output wire logic live_otr,
  output wire logic [63:0] live_timestamp,
  output wire logic measurement_done,measurement_valid,
  output wire logic [31:0] effective_phase_inc
);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  localparam int unsigned RATE=25000000;
  logic clk_adc=0;always #(20ns)clk_adc=~clk_adc;
  wire core_rst,enable_qualified;wire [13:0] unused_mid;
  scope_core safety(.clk_sample(clk_adc),.arst(rst),.clock_locked(1'b1),
    .module_enable(acquire_enable&&emergency_enable),.clock_restart(1'b0),
    .dac_data_oe(safe_dac_data_oe),.dac_clk_oe(safe_dac_clk_oe),
    .adc_clk_oe(safe_adc_clk_oe),.capture_enable(safe_capture),
    .dac_data(unused_mid),.state(safe_state),.core_rst(core_rst),.enable_qualified(enable_qualified));
  wire [13:0] dds_code,dac_input,dac_output;wire [31:0] dds_phase;wire dds_valid,di_valid,do_valid;
  integer unsigned dac_edges;
  scope_dds_rate_adapter #(.DAC_RATE_HZ(RATE)) rate_adapter(.phase_inc_25m(dds_phase_inc),.phase_inc_actual(effective_phase_inc));
  dds_core dds(.clk_dac(clk_adc),.rst(rst),.enable(dds_enable&&safe_dac_clk_oe),
    .waveform(dds_wave),.phase_inc(effective_phase_inc),.phase_offset(dds_phase_offset),
    .amplitude(dds_amplitude),.dc_offset(dds_dc_offset),.dac_code(dds_code),.sample_phase(dds_phase),.sample_valid(dds_valid));
  scope_pin_model pins(.clk(clk_adc),.dac_data(dds_code),.dac_data_oe(safe_dac_data_oe),
    .dac_clk_oe(safe_dac_clk_oe),.adc_clk_oe(safe_adc_clk_oe),
    .dac_da(pin_dac),.dac_aclk(pin_aclk),.dac_wr1(pin_wr1),.adc_clk(pin_adc_clk));
  ad9767_model dac(.rst(rst),.bus_enable(safe_dac_data_oe&&safe_dac_clk_oe),
    .aclk(clk_adc),.wr1(clk_adc),.bclk(1'b0),.wr2(1'b0),.da(dds_code),
    .input_code(dac_input),.dac_code(dac_output),.input_valid(di_valid),.dac_valid(do_valid),.accepted_edges(dac_edges));
  wire signed [31:0] ideal_sample;wire channel_valid,channel_clip,force_en,force_val;
  wire signed [31:0] model_sample;
  logic [63:0] source_tick;
  wire force_otr=(CASE_ID==6)&&source_tick==64'd9500;
  wire pos_spike=(CASE_ID==5)&&source_tick==64'd9501;
  wire neg_spike=(CASE_ID==5)&&source_tick==64'd9503;
  loopback_channel_model #(.GAIN_Q16(16384),.NOISE_LSB(0)) channel(
    .clk_sample(clk_adc),.rst(rst),.dac_code(dac_output),.dac_valid(do_valid),
    .noise_seed(32'd1),.force_otr_enable(force_otr),.force_otr_value(1'b1),
    .ideal_sample(ideal_sample),.sample_valid(channel_valid),.channel_clipped(channel_clip),
    .adc_force_otr_enable(force_en),.adc_force_otr_value(force_val));
  assign model_sample=pos_spike?32'sd1950:neg_spike?-32'sd1950:ideal_sample;
  always_ff @(posedge clk_adc)if(rst)source_tick<=64'd0;else source_tick<=source_tick+64'd1;
  wire [11:0] adc_raw;wire adc_otr,adc_valid;
  ad9226_model #(.T_CO_NS(3.5)) adc(.adc_clk(clk_adc),.rst(rst),.ideal_sample(model_sample),
    .noise_seed(32'd1),.force_otr_enable(force_en),.force_otr_value(force_val),
    .raw_code(adc_raw),.otr(adc_otr),.output_valid(adc_valid));
  wire signed [12:0] live_signed;
  adc_capture capture_adc(.clk_sample(clk_adc),.rst(rst),.capture_enable(safe_capture),
    .adc_data(adc_raw),.adc_otr(adc_otr),.sample_valid(live_valid),
    .sample_raw(live_raw),.sample_signed(live_signed),.sample_otr(live_otr),.sample_timestamp(live_timestamp));
  logic arm_pending,arm_issued,arm;
  always_ff @(posedge clk_sys)if(rst||stop_pulse||release_pulse)arm_pending<=1'b0;
    else if(single_pulse)arm_pending<=1'b1;
  always_ff @(negedge clk_adc)begin
    if(rst||!acquire_enable)begin arm<=1'b0;arm_issued<=1'b0;end
    else begin
      arm<=arm_pending&&safe_capture&&!arm_issued;
      if(arm_pending&&safe_capture&&!arm_issued)arm_issued<=1'b1;
    end
  end
  wire cap_busy,frame,cap_error,read_valid,arm_ready,mem_read_ready;wire [15:0] read_word;
  wire [63:0] read_timestamp;wire signed [12:0] read_signed;
  assign backend_rate=RATE;
  assign capture_busy=cap_busy||arm_pending&&!arm_issued;
  assign capture_ready=!capture_busy&&!frame&&arm_ready;
  assign frame_available=frame;
  assign backend_error=cap_error;
  assign sample_ready=frame&&!capture_busy&&!release_pulse&&mem_read_ready;
  assign sample_valid=read_valid;assign sample_word=read_word;
  generate begin:g_bram
    capture_state_t capture_state;capture_metadata_t metadata;wire [13:0]write_pointer;wire sd;
    bram_capture #(.USE_EXTENDED_TRIGGER(1)) memory(.clk_adc(clk_adc),.rst_adc(rst),
      .module_enable(safe_capture),.arm(arm),.cfg_mode(CASE_ID==0?CAP_AUTO:CAP_SINGLE),
      .cfg_rising(1'b1),.cfg_threshold(13'sd0),.cfg_hysteresis(13'd8),
      .cfg_pre_samples(pre_samples[14:0]),.cfg_auto_timeout(32'd256),.cfg_trigger(trigger_config),
      .sample_valid(live_valid),.sample_raw(live_raw),.sample_otr(live_otr),.sample_timestamp(live_timestamp),
      .capture_state(capture_state),.single_done(sd),.capture_error(cap_error),.busy(cap_busy),.write_pointer(write_pointer),
      .clk_sys(clk_sys),.rst_sys(rst),.read_request(sample_request&&sample_ready),.frame_release(release_pulse),
      .read_index(sample_index[13:0]),.frame_ready(frame),.read_valid(read_valid),
      .frame_metadata(metadata),.read_word(read_word),.read_signed(read_signed),.read_timestamp(read_timestamp));
    assign backend_timestamp=metadata.first_timestamp;
    assign backend_trigger_index={18'd0,metadata.trigger_index};
    assign backend_length={17'd0,metadata.frame_length};
    assign arm_ready=capture_state==CAP_IDLE;
    assign mem_read_ready=1'b1;
  end endgenerate
  // Measure one complete accepted sample stream: one complete BRAM record.
  // Its exact input timestamps are traced separately from the frozen record.
  logic measure_start;
  wire measure_ready,measure_busy;
  measurement_core measure(.clk(clk_adc),.rst(rst),.start(measure_start),.frame_length(18'd16384),
    .sample_rate_hz(RATE),.threshold(13'sd0),.hysteresis(13'd8),
    .sample_valid(live_valid&&measure_ready),.sample_signed(live_signed),.sample_timestamp(live_timestamp),
    .sample_ready(measure_ready),.busy(measure_busy),.measurement_done(measurement_done),
    .measurement_valid(measurement_valid),.measurement_error(measurement_error),.result(measurements));
  always_ff @(posedge clk_adc)if(rst)measure_start<=1'b0;
    else measure_start<=arm;
endmodule
`default_nettype wire
