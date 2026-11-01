`default_nettype none
module scope_cpu_endpoint #(parameter int unsigned CLOCK_HZ=100000000,BAUD=115200,FIFO_ADDR_BITS=8,RX_TIMEOUT_CYCLES=100000,
  parameter bit LOOPBACK_BOOT_PRESET=1'b0,SUPPORT_MULTIRES=1'b0,SUPPORT_ANALYSIS=1'b0,SUPPORT_MODES=1'b0,SUPPORT_SATURATION=1'b0,SUPPORT_AWG=1'b0,
  parameter logic [31:0] FIRMWARE_BUILD=32'd0)(
  input wire [9:0] awg_play_index,
  output wire signed [15:0] awg_play_value,
  output wire awg_selected,
  input wire logic clk,rst,uart_rx_pin,
  output wire logic uart_tx_pin,
  output wire logic [31:0] uart_framing_errors,rx_overruns,false_starts,tx_stall_cycles,
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
  output wire protocol_pkg::frame_header_t last_request_header,
  output wire logic sample_request,
  output wire logic [17:0] sample_index,
  input wire logic sample_ready,sample_valid,
  input wire logic [15:0] sample_word
);
  timeunit 1ns;timeprecision 1ps;
  wire logic rx_byte_valid,rx_byte_ready,tx_byte_valid,tx_byte_ready;
  wire logic [7:0] rx_byte,tx_byte;

  wire host_valid,host_ready,response_valid,response_ready;
  wire [7:0] host_data,response_data;
  wire io_strobe,io_read,io_write,io_ready;
  wire [31:0] io_address,io_wdata,io_rdata;
  wire [3:0] io_be;
  scope_microblaze cpu(.Clk(clk),.Reset(rst),
    .IO_addr_strobe(io_strobe),.IO_read_strobe(io_read),.IO_write_strobe(io_write),
    .IO_address(io_address),.IO_byte_enable(io_be),.IO_write_data(io_wdata),
    .IO_read_data(io_rdata),.IO_ready(io_ready));
  scope_cpu_mailbox mailbox(.clk(clk),.rst(rst),
    .io_strobe(io_strobe),.io_read(io_read),.io_write(io_write),.io_ready(io_ready),
    .io_address(io_address),.io_wdata(io_wdata),.io_rdata(io_rdata),.io_be(io_be),
    .host_valid(host_valid),.host_ready(host_ready),.host_data(host_data),
    .response_valid(response_valid),.response_ready(response_ready),.response_data(response_data),
    .backend_valid(tx_byte_valid),.backend_ready(tx_byte_ready),.backend_data(tx_byte),
    .request_valid(rx_byte_valid),.request_ready(rx_byte_ready),.request_data(rx_byte));
  uart_transport #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD),.FIFO_ADDR_BITS(10)) transport(
    .clk(clk),.rst(rst),.rx(uart_rx_pin),.tx(uart_tx_pin),
    .tx_valid(response_valid),.tx_ready(response_ready),.tx_data(response_data),
    .rx_valid(host_valid),.rx_ready(host_ready),.rx_data(host_data),
    .rx_overruns(rx_overruns),.tx_stall_cycles(tx_stall_cycles),
    .framing_errors(uart_framing_errors),.false_starts(false_starts));
  scope_protocol_core #(.RX_TIMEOUT_CYCLES(RX_TIMEOUT_CYCLES),
    .LOOPBACK_BOOT_PRESET(LOOPBACK_BOOT_PRESET),.SUPPORT_MULTIRES(SUPPORT_MULTIRES),.SUPPORT_ANALYSIS(SUPPORT_ANALYSIS),.SUPPORT_MODES(SUPPORT_MODES),.SUPPORT_SATURATION(SUPPORT_SATURATION),.SUPPORT_AWG(SUPPORT_AWG),.FIRMWARE_BUILD(FIRMWARE_BUILD)) protocol(.*,
    .in_valid(rx_byte_valid),.in_ready(rx_byte_ready),.in_data(rx_byte),
    .out_valid(tx_byte_valid),.out_ready(tx_byte_ready),.out_data(tx_byte));
endmodule
`default_nettype wire
