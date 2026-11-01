`default_nettype none
module scope_protocol_core #(parameter int unsigned RX_TIMEOUT_CYCLES=100000,
  parameter bit LOOPBACK_BOOT_PRESET=1'b0,SUPPORT_MULTIRES=1'b0,SUPPORT_ANALYSIS=1'b0,SUPPORT_MODES=1'b0,SUPPORT_SATURATION=1'b0,SUPPORT_AWG=1'b0,
  parameter logic [31:0] FIRMWARE_BUILD=32'd0)(
  input wire [9:0] awg_play_index,
  output wire signed [15:0] awg_play_value,
  output wire awg_selected,
  input wire logic clk,rst,in_valid,out_ready,
  input wire logic [7:0] in_data,
  output wire logic in_ready,out_valid,
  output wire logic [7:0] out_data,
  input wire logic [31:0] uart_framing_errors,rx_overruns,
  input wire logic capture_busy,capture_ready,frame_available,backend_error,
  input wire logic [63:0] backend_timestamp,
  input wire logic [31:0] backend_rate,backend_trigger_index,backend_length,
  input wire scope_pkg::measurement_result_t measurements,
  input wire logic measurement_error,
  input wire logic [767:0] spectrum_bytes,
  input wire logic [127:0] saturation_bytes,
  output wire logic [1:0] diagnostic_mode,
  output wire logic single_pulse,stop_pulse,release_pulse,acquire_enable,
  output wire logic [17:0] record_length,pre_samples,
  output wire scope_pkg::capture_mode_t capture_mode,
  output wire logic [31:0] auto_timeout,
  output wire scope_pkg::trigger_config_t trigger_config,
  output wire scope_pkg::dds_wave_t dds_wave,
  output wire logic dds_enable,
  output wire logic [31:0] dds_phase_inc,dds_phase_offset,
  output wire logic [15:0] dds_amplitude,
  output wire logic signed [17:0] dds_dc_offset,
  output wire protocol_pkg::parser_errors_t parser_errors,
  output wire logic [31:0] good_frames,unknown_commands,command_errors,
  output protocol_pkg::frame_header_t last_request_header,
  output wire logic sample_request,
  output wire logic [17:0] sample_index,
  input wire logic sample_ready,sample_valid,
  input wire logic [15:0] sample_word
);
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;
  frame_header_t parsed,command_header,wave_header,tx_header,envelope_header;
  command_header_t decoded_command;
  assign decoded_command='{kind:parsed.kind,seq:parsed.seq,length:parsed.length,flags:parsed.flags};
  wire logic parsed_valid,parsed_ready,parsed_payload_valid,parsed_payload_ready;
  wire logic [7:0] parsed_payload;
  wire logic command_valid,command_ready,command_payload_valid,command_payload_ready,command_done;
  wire logic [7:0] command_payload,wave_payload;
  wire logic wave_request,wave_idle,wave_valid,wave_header_ready,wave_payload_valid,wave_payload_ready,wave_done;
  wire logic [31:0] wave_offset,wave_count;
  wire logic [15:0] wave_sequence;
  wire envelope_request,envelope_idle,envelope_valid,envelope_header_ready;
  wire envelope_payload_valid,envelope_payload_ready,envelope_done;
  wire [7:0] envelope_payload;
  wire [9:0] envelope_buckets;
  wire [15:0] envelope_sequence;
  wire wave_sample_request,envelope_sample_request;
  wire [17:0] wave_sample_index,envelope_sample_index;
  wire envelope_active=!envelope_idle;
  wire stream_idle=wave_idle && envelope_idle;
  wire logic tx_header_valid,tx_header_ready,tx_payload_valid,tx_payload_ready,tx_done;
  wire logic [7:0] tx_payload;
  logic locked,owner_command,owner_envelope;
  wire logic choose_command=command_valid;
  frame_rx #(.TIMEOUT_CYCLES(RX_TIMEOUT_CYCLES)) receiver(.clk(clk),.rst(rst),.in_valid(in_valid),.in_data(in_data),.in_ready(in_ready),
    .header_valid(parsed_valid),.header_ready(parsed_ready),.header(parsed),.payload_valid(parsed_payload_valid),
    .payload_ready(parsed_payload_ready),.payload_data(parsed_payload),.errors(parser_errors),.good_frames(good_frames));
  protocol_commands #(.LOOPBACK_BOOT_PRESET(LOOPBACK_BOOT_PRESET),
    .SUPPORT_MULTIRES(SUPPORT_MULTIRES),.SUPPORT_ANALYSIS(SUPPORT_ANALYSIS),.SUPPORT_MODES(SUPPORT_MODES),.SUPPORT_SATURATION(SUPPORT_SATURATION),.SUPPORT_AWG(SUPPORT_AWG),.FIRMWARE_BUILD(FIRMWARE_BUILD)) commands(.awg_play_index(awg_play_index),.awg_play_value(awg_play_value),.awg_selected(awg_selected),.clk(clk),.rst(rst),.header_valid(parsed_valid),.header(decoded_command),.header_ready(parsed_ready),
    .payload_valid(parsed_payload_valid),.payload_data(parsed_payload),.payload_ready(parsed_payload_ready),
    .response_valid(command_valid),.response_ready(command_ready),.response(command_header),.response_payload_valid(command_payload_valid),
    .response_payload(command_payload),.response_payload_ready(command_payload_ready),.response_done(command_done),
    .parser_errors(parser_errors),.good_frames(good_frames),.uart_framing_errors(uart_framing_errors),.rx_overruns(rx_overruns),
    .capture_busy(capture_busy),.capture_ready(capture_ready),.frame_available(frame_available),.backend_error(backend_error),
    .wave_ready(stream_idle),.backend_timestamp(backend_timestamp),.backend_rate(backend_rate),.backend_trigger_index(backend_trigger_index),
    .backend_length(backend_length),.measurements(measurements),.measurement_error(measurement_error),.spectrum_bytes(spectrum_bytes),.saturation_bytes(saturation_bytes),.diagnostic_mode(diagnostic_mode),
    .single_pulse(single_pulse),.stop_pulse(stop_pulse),.release_pulse(release_pulse),.acquire_enable(acquire_enable),
    .wave_request(wave_request),.wave_offset(wave_offset),.wave_count(wave_count),.wave_sequence(wave_sequence),
    .envelope_request(envelope_request),.envelope_buckets(envelope_buckets),.envelope_sequence(envelope_sequence),
    .record_length(record_length),.pre_samples(pre_samples),.capture_mode(capture_mode),.auto_timeout(auto_timeout),.trigger_config(trigger_config),.dds_wave(dds_wave),.dds_enable(dds_enable),
    .dds_phase_inc(dds_phase_inc),.dds_phase_offset(dds_phase_offset),.dds_amplitude(dds_amplitude),.dds_dc_offset(dds_dc_offset),
    .unknown_commands(unknown_commands),.command_errors(command_errors));
  protocol_wave_tx wave(.clk(clk),.rst(rst),.request(wave_request),.cancel(stop_pulse),.request_offset(wave_offset),.request_count(wave_count),
    .request_sequence(wave_sequence),.first_timestamp(backend_timestamp),.sample_rate(backend_rate),.trigger_index(backend_trigger_index),
    .record_length(backend_length),.request_ready(wave_idle),.header_valid(wave_valid),.header_ready(wave_header_ready),.header(wave_header),
    .payload_valid(wave_payload_valid),.payload_ready(wave_payload_ready),.payload_data(wave_payload),.packet_done(wave_done),
    .sample_request(wave_sample_request),.sample_index(wave_sample_index),.sample_ready(sample_ready && !envelope_active),
    .sample_valid(sample_valid && !envelope_active),.sample_word(sample_word));
  generate if(SUPPORT_MULTIRES)begin:g_envelope
    protocol_envelope_tx envelope(.clk(clk),.rst(rst),.request(envelope_request),.cancel(stop_pulse),
      .request_buckets(envelope_buckets),.request_sequence(envelope_sequence),
      .first_timestamp(backend_timestamp),.sample_rate(backend_rate),.trigger_index(backend_trigger_index),.record_length(backend_length),
      .request_ready(envelope_idle),.header_valid(envelope_valid),.header_ready(envelope_header_ready),.header(envelope_header),
      .payload_valid(envelope_payload_valid),.payload_ready(envelope_payload_ready),.payload_data(envelope_payload),.packet_done(envelope_done),
      .sample_request(envelope_sample_request),.sample_index(envelope_sample_index),.sample_ready(sample_ready && envelope_active),
      .sample_valid(sample_valid && envelope_active),.sample_word(sample_word));
  end else begin:g_no_envelope
    assign envelope_idle=1'b1;assign envelope_valid=1'b0;assign envelope_payload_valid=1'b0;
    assign envelope_payload=0;assign envelope_header='0;assign envelope_sample_request=1'b0;assign envelope_sample_index=0;
  end endgenerate
  assign sample_request=envelope_active?envelope_sample_request:wave_sample_request;
  assign sample_index=envelope_active?envelope_sample_index:wave_sample_index;
  assign tx_header_valid=!locked && (command_valid || wave_valid || envelope_valid);
  assign tx_header=choose_command?command_header:(envelope_valid?envelope_header:wave_header);
  assign command_ready=!locked && choose_command && tx_header_ready;
  assign wave_header_ready=!locked && !choose_command && !envelope_valid && tx_header_ready;
  assign envelope_header_ready=!locked && !choose_command && envelope_valid && tx_header_ready;
  assign tx_payload_valid=locked && (owner_command?command_payload_valid:(owner_envelope?envelope_payload_valid:wave_payload_valid));
  assign tx_payload=owner_command?command_payload:(owner_envelope?envelope_payload:wave_payload);
  assign command_payload_ready=locked && owner_command && tx_payload_ready;
  assign wave_payload_ready=locked && !owner_command && !owner_envelope && tx_payload_ready;
  assign envelope_payload_ready=locked && !owner_command && owner_envelope && tx_payload_ready;
  assign command_done=locked && owner_command && tx_done;
  assign wave_done=locked && !owner_command && !owner_envelope && tx_done;
  assign envelope_done=locked && !owner_command && owner_envelope && tx_done;
  frame_tx transmitter(.clk(clk),.rst(rst),.header_valid(tx_header_valid),.header_ready(tx_header_ready),.header(tx_header),
    .payload_valid(tx_payload_valid),.payload_ready(tx_payload_ready),.payload_data(tx_payload),
    .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),.done(tx_done));
  always_ff @(posedge clk)begin
    if(rst)last_request_header<='0;
    else if(parsed_valid && parsed_ready)last_request_header<=parsed;
  end
  always_ff @(posedge clk)begin
    if(rst)begin locked<=0;owner_command<=0;owner_envelope<=0;end
    else if(!locked && tx_header_valid && tx_header_ready)begin locked<=1;owner_command<=choose_command;owner_envelope<=envelope_valid && !choose_command;end
    else if(locked && tx_done)locked<=0;
  end
endmodule
`default_nettype wire
