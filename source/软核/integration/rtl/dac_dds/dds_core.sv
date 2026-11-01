`default_nettype none
module dds_core (
  input wire logic clk_dac,
  input wire logic rst,                 // Synchronous, active high, falling edge.
  input wire logic enable,              // Low forces midpoint and restarts phase.
  input wire scope_pkg::dds_wave_t waveform,
  input wire logic [31:0] phase_inc,
  input wire logic [31:0] phase_offset,
  input wire logic [15:0] amplitude,     // Unsigned peak amplitude in DAC LSBs.
  input wire logic signed [17:0] dc_offset, // Signed LSBs relative to 8192.
  output logic [13:0] dac_code,
  output logic [31:0] sample_phase,
  output logic sample_valid
);
  timeunit 1ns; timeprecision 1ps;
  logic [31:0] accumulator, effective_phase;
  logic primed;
  logic signed [15:0] sine_value;
  logic signed [63:0] wave_q15, triangle_numerator, product, scaled, biased;
  logic [13:0] next_code;
  dds_sine_lut sine_rom(.address(effective_phase[31:22]), .value(sine_value));
  function automatic logic signed [63:0] round_div(
    input logic signed [63:0] numerator, input logic signed [63:0] divisor);
    // Nearest integer; exact half cases round away from zero.
    if (numerator < 64'sd0) return -((-numerator + divisor/64'sd2)/divisor);
    return (numerator + divisor/64'sd2)/divisor;
  endfunction
  always_comb begin
    effective_phase = accumulator + phase_offset; // Explicit 32-bit modulo 2^32.
    triangle_numerator = 64'sd0;
    wave_q15 = 64'sd0;
    case (waveform)
      scope_pkg::DDS_SINE: wave_q15 = {{48{sine_value[15]}}, sine_value};
      scope_pkg::DDS_SQUARE: wave_q15 = effective_phase[31] ? -64'sd32767 : 64'sd32767;
      scope_pkg::DDS_TRIANGLE: begin
        if (effective_phase[31:22] < 10'd256)
          triangle_numerator = $signed({54'b0,effective_phase[31:22]});
        else if (effective_phase[31:22] < 10'd768)
          triangle_numerator = 64'sd512 - $signed({54'b0,effective_phase[31:22]});
        else
          triangle_numerator = $signed({54'b0,effective_phase[31:22]}) - 64'sd1024;
        wave_q15 = round_div(triangle_numerator * 64'sd32767, 64'sd256);
      end
      scope_pkg::DDS_DC: wave_q15 = 64'sd0;
      default: wave_q15 = 64'sd0;
    endcase
    product = wave_q15 * $signed({48'b0, amplitude});
    scaled = round_div(product,64'sd32767);
    biased = 64'sd8192 + {{46{dc_offset[17]}},dc_offset} + scaled;
    if (biased < 64'sd0) next_code = 14'd0;
    else if (biased > 64'sd16383) next_code = 14'd16383;
    else next_code = biased[13:0];
  end
  always_ff @(negedge clk_dac) begin
    if (rst || !enable) begin
      accumulator <= 32'd0;
      primed <= 1'b0;
      dac_code <= scope_pkg::DAC_MID_CODE;
      sample_phase <= 32'd0;
      sample_valid <= 1'b0;
    end else if (!primed) begin
      // One midpoint presentation before any configured waveform, even at nonzero phase.
      primed <= 1'b1;
      accumulator <= 32'd0;
      dac_code <= scope_pkg::DAC_MID_CODE;
      sample_phase <= 32'd0;
      sample_valid <= 1'b0;
    end else begin
      accumulator <= accumulator + phase_inc;
      dac_code <= next_code;
      sample_phase <= effective_phase;
      sample_valid <= 1'b1;
    end
  end
endmodule
`default_nettype wire
