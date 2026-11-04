`default_nettype none
// First physical-board baseline: 25 MSPS, 16K BRAM, UART v1 at 115200 8N1.
// All protocol, trigger and memory controls share clk_sample. No model is used.
module scope_cpu_vga_top #(
  parameter int unsigned ENABLE_DEBOUNCE_CYCLES=25000,
  parameter int unsigned UART_BAUD=921600,
  parameter logic [31:0] FIRMWARE_BUILD=32'hAF311031
)(
  input wire sys_clk_100, reset_n, module_switch,
  input wire fpga_uart_rx_n5,
  output wire fpga_uart_tx_t4,
  input wire [11:0] adc_data,
  input wire adc_otr,
  output wire [13:0] dac_da,
  output wire dac_aclk, dac_wr1, adc_clk,
  output wire [3:0] status_led,
 input wire [4:0] vga_switches,panel_buttons,
 output wire vga_hsync,vga_vsync,
 output wire [3:0] vga_r,vga_g,vga_b
);
  timeunit 1ns; timeprecision 1ps;
  import scope_pkg::*;
  wire clk_sample, clock_locked, rst;
  wire emergency=!reset_n || !clock_locked;
  scope_clk_wiz clock_wizard(.clk_in1(sys_clk_100),.reset(!reset_n),
    .clk_out1(clk_sample),.locked(clock_locked));
  scope_reset_sync reset_sync(.clk(clk_sample),.arst(emergency),.rst(rst));

  // A switch left ON during configuration cannot start external outputs.
  // Require a debounced OFF observation, then a debounced ON transition.
  (* ASYNC_REG="TRUE",SHREG_EXTRACT="NO" *) logic switch_meta,switch_sync;
  localparam int CW=$clog2(ENABLE_DEBOUNCE_CYCLES+1);
  logic [CW-1:0] stable_count;
  logic switch_previous, switch_filtered, off_seen;
  always_ff @(posedge clk_sample or posedge emergency) begin
    if(emergency)begin switch_meta<=1'b1;switch_sync<=1'b1;end
    else begin switch_meta<=module_switch;switch_sync<=switch_meta;end
  end
  always_ff @(posedge clk_sample) begin
    if(rst)begin
      stable_count<='0;switch_previous<=1'b1;switch_filtered<=1'b0;off_seen<=1'b0;
    end else if(switch_sync!=switch_previous)begin
      switch_previous<=switch_sync;stable_count<='0;
    end else if(stable_count<CW'(ENABLE_DEBOUNCE_CYCLES))begin
      stable_count<=stable_count+1'b1;
    end else begin
      switch_filtered<=switch_sync;
      if(!switch_sync)off_seen<=1'b1;
    end
  end
  wire manual_enable=off_seen && switch_filtered && module_switch;
  wire dac_data_oe,dac_clk_oe,adc_clk_oe,safe_capture,core_rst;
  safe_state_t safe_state;
  scope_core safety(.clk_sample(clk_sample),.arst(!reset_n),.clock_locked(clock_locked),
    .module_enable(manual_enable),.clock_restart(1'b0),.dac_data_oe(dac_data_oe),
    .dac_clk_oe(dac_clk_oe),.adc_clk_oe(adc_clk_oe),.capture_enable(safe_capture),
    .dac_data(),.state(safe_state),.core_rst(core_rst),.enable_qualified());

  wire single_pulse,stop_pulse,release_pulse,acquire_enable;
  wire [17:0] record_length,pre_samples;
  trigger_config_t trigger_config;
  capture_mode_t selected_capture_mode;
  wire [31:0] auto_timeout;
  dds_wave_t dds_wave;
  wire dds_enable;
  wire [31:0] dds_phase_inc,dds_phase_offset,good_frames;
  wire [15:0] dds_amplitude;
  wire signed [17:0] dds_dc_offset;
  wire [13:0] dds_code;
  wire [9:0] awg_play_index;
  wire signed [15:0] awg_play_value;
  wire awg_selected;
  scope_board_dds dds(.clk_dac(clk_sample),.rst(core_rst),
    .enable(dds_enable && safe_state==RUN),.waveform(dds_wave),
    .phase_inc(dds_phase_inc),.phase_offset(dds_phase_offset),
    .amplitude(dds_amplitude),.dc_offset(dds_dc_offset),
    .dac_code(dds_code),.awg_selected(awg_selected),.awg_play_index(awg_play_index),.awg_play_value(awg_play_value));
  wire [13:0] dac_code=(safe_state==RUN)?dds_code:DAC_MID_CODE;
  wire forwarded_dac,forwarded_wr1,forwarded_adc;
  // OEs already include the asynchronous-assert/synchronous-release reset.
  // Do not reintroduce raw reset_n/MMCM LOCKED at ODDR reset pins.
  wire dac_forward_reset=!dac_clk_oe;
  wire adc_forward_reset=!adc_clk_oe;
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.SRTYPE("ASYNC"),.INIT(1'b0)) dac_oddr(
    .C(clk_sample),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(dac_forward_reset),.S(1'b0),.Q(forwarded_dac));
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.SRTYPE("ASYNC"),.INIT(1'b0)) wr1_oddr(
    .C(clk_sample),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(dac_forward_reset),.S(1'b0),.Q(forwarded_wr1));
  ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.SRTYPE("ASYNC"),.INIT(1'b0)) adc_oddr(
    .C(clk_sample),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(adc_forward_reset),.S(1'b0),.Q(forwarded_adc));
  for(genvar i=0;i<14;i++)begin:g_dac
    OBUFT buffer(.I(dac_code[i]),.T(!dac_data_oe),.O(dac_da[i]));
  end
  OBUFT dac_clock_buffer(.I(forwarded_dac),.T(!dac_clk_oe),.O(dac_aclk));
  OBUFT wr_clock_buffer(.I(forwarded_wr1),.T(!dac_clk_oe),.O(dac_wr1));
  OBUFT adc_clock_buffer(.I(forwarded_adc),.T(!adc_clk_oe),.O(adc_clk));

  wire live_valid,live_otr;
  adc_raw_t live_raw;
  sample_timestamp_t live_timestamp;
  adc_capture input_capture(.clk_sample(clk_sample),.rst(rst),.capture_enable(safe_capture),
    .adc_data(adc_data),.adc_otr(adc_otr),.sample_valid(live_valid),
    .sample_raw(live_raw),.sample_signed(),.sample_otr(live_otr),.sample_timestamp(live_timestamp));
  capture_state_t capture_state;
  capture_metadata_t metadata;
  wire cap_busy,cap_error,frame_available,raw_frame_available,sample_request,sample_ready,sample_valid;
  wire analysis_done,analysis_request,analysis_read_valid,analysis_error;
  wire [13:0] analysis_index;
  wire [767:0] spectrum_bytes;
  wire [127:0] saturation_bytes;
  wire [1:0] diagnostic_mode;
  logic frame_diagnostic;
  always_ff @(posedge clk_sample)begin
    if(rst)frame_diagnostic<=0;
    else if(single_pulse)frame_diagnostic<=|diagnostic_mode;
  end
  // Diagnostic injection changes only capture-memory input, never DAC pins.
  // Normal operation is selected at reset and every STOP. Every injected
  // record is marked in its frozen saturation summary.
  wire [3:0] diagnostic_phase=live_timestamp[3:0];
  wire [11:0] diagnostic_raw=(diagnostic_mode==2)?12'd4095:
    (diagnostic_mode==3)?12'd2047:
    (diagnostic_phase==0 || diagnostic_phase==1 || diagnostic_phase==2 || diagnostic_phase==15)?12'd0:
    (diagnostic_phase==7)?12'd4095:12'd2047;
  wire [11:0] memory_raw=(diagnostic_mode!=0 && acquire_enable)?diagnostic_raw:live_raw;
  measurement_result_t measurements;
  wire analysis_active=raw_frame_available && !analysis_done;
  assign frame_available=raw_frame_available && analysis_done;
  wire [17:0] sample_index;
  wire [15:0] sample_word;
  // Cancel only an active acquisition. Frozen records remain immutable until
  // the protocol's release handshake. CAP_SINGLE requires an actual trigger.
  wire memory_enable=safe_capture && acquire_enable && !stop_pulse;
  wire capture_ready=safe_capture && !raw_frame_available && !cap_busy &&
    (capture_state==CAP_IDLE || capture_state==CAP_SINGLE_HOLD);
  assign sample_ready=frame_available && !cap_busy && !release_pulse;
  bram_capture #(.USE_EXTENDED_TRIGGER(1'b1)) memory(
    .clk_adc(clk_sample),.rst_adc(rst),.module_enable(memory_enable),.arm(single_pulse),
    .cfg_mode(selected_capture_mode),.cfg_rising(trigger_config.kind!=TRIG_FALL),
    .cfg_threshold(trigger_config.threshold),.cfg_hysteresis(trigger_config.hysteresis),
    .cfg_pre_samples(pre_samples[14:0]),.cfg_auto_timeout(auto_timeout),.cfg_trigger(trigger_config),
    .sample_valid(live_valid),.sample_raw(memory_raw),.sample_otr(live_otr),.sample_timestamp(live_timestamp),
    .capture_state(capture_state),.single_done(),.capture_error(cap_error),.busy(cap_busy),.write_pointer(),
    .clk_sys(clk_sample),.rst_sys(rst),.read_request(analysis_active?analysis_request:(sample_request && sample_ready)),
    .frame_release(release_pulse),.read_index(analysis_active?analysis_index:sample_index[13:0]),
    .frame_ready(raw_frame_available),.read_valid(analysis_read_valid),.frame_metadata(metadata),
    .read_word(sample_word),.read_signed(),.read_timestamp());
  assign sample_valid=analysis_read_valid && !analysis_active;
  wire bin_valid; wire [8:0] bin_index; wire [63:0] bin_power;
  panel_analysis analysis(.display_bin_valid(bin_valid),.display_bin_index(bin_index),.display_bin_power(bin_power),.clk(clk_sample),.rst(rst || release_pulse),.frame_ready(raw_frame_available),.frame_diagnostic(frame_diagnostic),
    .first_timestamp(metadata.first_timestamp),.threshold(metadata.threshold),.hysteresis(metadata.hysteresis),
    .read_request(analysis_request),.read_index(analysis_index),.read_valid(analysis_read_valid),.read_word(sample_word),
    .done(analysis_done),.measurements(measurements),.measurement_error(analysis_error),.spectrum_bytes(spectrum_bytes),.saturation_bytes(saturation_bytes));
  wire [31:0] panel_rdata,panel_wdata;
  wire [7:0] panel_addr; wire panel_write;
  scope_cpu_endpoint #(.CLOCK_HZ(25000000),.BAUD(UART_BAUD),
    .LOOPBACK_BOOT_PRESET(1'b1),.SUPPORT_MULTIRES(1'b1),.SUPPORT_ANALYSIS(1'b1),.SUPPORT_MODES(1'b1),.SUPPORT_SATURATION(1'b1),.SUPPORT_AWG(1'b1),.FIRMWARE_BUILD(FIRMWARE_BUILD)) uart(
    .panel_rdata(panel_rdata),.panel_addr(panel_addr),.panel_wdata(panel_wdata),.panel_write(panel_write),
    .awg_play_index(awg_play_index),.awg_play_value(awg_play_value),.awg_selected(awg_selected),
    .clk(clk_sample),.rst(rst),.uart_rx_pin(fpga_uart_rx_n5),.uart_tx_pin(fpga_uart_tx_t4),
    .uart_framing_errors(),.rx_overruns(),.false_starts(),.tx_stall_cycles(),
    .capture_busy(cap_busy || analysis_active),.capture_ready(capture_ready),.frame_available(frame_available),.backend_error(cap_error),
    .backend_timestamp(metadata.first_timestamp),.backend_rate(32'd25000000),
    .backend_trigger_index({18'd0,metadata.trigger_index}),.backend_length(32'd16384),
    .measurements(measurements),.measurement_error(analysis_error),.spectrum_bytes(spectrum_bytes),.saturation_bytes(saturation_bytes),.diagnostic_mode(diagnostic_mode),
    .single_pulse(single_pulse),.stop_pulse(stop_pulse),.release_pulse(release_pulse),.acquire_enable(acquire_enable),
    .record_length(record_length),.pre_samples(pre_samples),.capture_mode(selected_capture_mode),.auto_timeout(auto_timeout),.trigger_config(trigger_config),
    .dds_wave(dds_wave),.dds_enable(dds_enable),.dds_phase_inc(dds_phase_inc),.dds_phase_offset(dds_phase_offset),
    .dds_amplitude(dds_amplitude),.dds_dc_offset(dds_dc_offset),.parser_errors(),
    .good_frames(good_frames),.unknown_commands(),.command_errors(),.last_request_header(),
    .sample_request(sample_request),.sample_index(sample_index),.sample_ready(sample_ready),
    .sample_valid(sample_valid),.sample_word(sample_word));
  assign status_led={good_frames[0],frame_available,safe_capture,clock_locked};

 wire pixel_clk,pixel_locked,pixel_rst;
 panel_pixel_clock video_clock(.clk25(clk_sample),.reset(rst),.clk49(pixel_clk),.locked(pixel_locked));
 scope_reset_sync video_reset(.clk(pixel_clk),.arst(emergency || !pixel_locked),.rst(pixel_rst));
 wire [9:0] panel_filtered; wire [31:0] milliseconds;
 panel_inputs inputs_unit(.clk(clk_sample),.reset(rst),.pins({vga_switches,panel_buttons}),
   .filtered(panel_filtered),.milliseconds(milliseconds));
 reg previous_frame=0,tap_finished=0;
 always @(posedge clk_sample) begin
  if(rst)begin previous_frame<=0;tap_finished<=0;end
  else begin
   previous_frame<=raw_frame_available;
   if(!raw_frame_available)tap_finished<=0;
   else if(analysis_active && analysis_read_valid && analysis_index==16383)tap_finished<=1;
  end
 end
 panel_screen screen(.clk(clk_sample),.reset(rst),.pixel_clk(pixel_clk),.pixel_reset(pixel_rst),
  .frame_start(raw_frame_available && !previous_frame),
  .tap_valid(analysis_active && analysis_read_valid && !tap_finished),
  .tap_index(analysis_index),.tap_raw(sample_word[11:0]),.tap_otr(sample_word[15]),
  .analysis_done(analysis_done),.analysis_error(analysis_error),
  .trigger_index(metadata.trigger_index),.automatic_trigger(metadata.automatic_trigger),
  .measurements(measurements),.spectrum(spectrum_bytes),.saturation(saturation_bytes),
  .bin_valid(bin_valid),.bin_index(bin_index),.bin_power(bin_power),
  .inputs({19'd0,panel_filtered[9:5],3'd0,panel_filtered[4:0]}),.milliseconds(milliseconds),
  .backend_status({28'd0,acquire_enable,safe_capture,(cap_busy || analysis_active),frame_available}),
  .bus_addr(panel_addr),.bus_wdata(panel_wdata),.bus_write(panel_write),.bus_rdata(panel_rdata),
  .hsync(vga_hsync),.vsync(vga_vsync),.red(vga_r),.green(vga_g),.blue(vga_b));

endmodule
`default_nettype wire
