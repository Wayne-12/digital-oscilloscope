`default_nettype none
// Verification-only module model, including the board's inverted polarity.
// rst is a simulation flush control; the physical AD9226 has no such reset pin.
module ad9226_model #(
  parameter realtime T_CO_NS = 3.5,
  parameter int signed GAIN_Q16 = 65536,
  parameter int signed OFFSET_LSB = 0,
  parameter int unsigned NOISE_LSB = 0,
  parameter bit MISSING_CODE_ENABLE = 1'b0,
  parameter logic [11:0] MISSING_CODE = 12'd2048,
  parameter logic [11:0] MISSING_REPLACEMENT = 12'd2049
) (
  input wire logic adc_clk,
  input wire logic rst,
  input wire logic signed [31:0] ideal_sample,
  input wire logic [31:0] noise_seed,
  input wire logic force_otr_enable,
  input wire logic force_otr_value,
  output scope_pkg::adc_raw_t raw_code,
  output logic otr,
  output logic output_valid
);
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;
  typedef logic signed [63:0] math_t;
  adc_raw_t code_pipe[0:6];
  logic otr_pipe[0:6], valid_pipe[0:6];
  logic [31:0] noise_state;

  function automatic logic [31:0] advance_noise(input logic [31:0] state_value);
    logic [31:0] word_value;
    word_value = state_value ^ (state_value << 32'd13);
    word_value = word_value ^ (word_value >> 32'd17);
    return word_value ^ (word_value << 32'd5);
  endfunction

  initial begin
    assert (T_CO_NS >= 3.5 && T_CO_NS <= 7.0)
      else $fatal(1, "TEST_FAIL AD9226 T_CO_NS must be within [3.5,7.0]");
    assert (ADC_PIPELINE_CYCLES == 7 && GAIN_Q16 >= 0 && NOISE_LSB <= 4096)
      else $fatal(1, "TEST_FAIL AD9226 invalid pipeline/gain/noise configuration");
    assert (!MISSING_CODE_ENABLE || MISSING_CODE != MISSING_REPLACEMENT)
      else $fatal(1, "TEST_FAIL missing-code replacement must differ");
  end

  // A sample entering at edge n is presented after edge n+7 + T_CO_NS:
  // seven full ADC periods, rather than seven edges counted inclusively.
  always @(posedge adc_clk) begin : conversion
    math_t product_value, rounded_value, adjusted_value, noise_value, clipped_value;
    logic [31:0] noise_word;
    adc_raw_t encoded_value;
    logic over_range;
    if (rst) begin
      assert (!$isunknown(noise_seed)) else $fatal(1, "TEST_FAIL unknown noise seed");
      noise_state <= (noise_seed == 32'd0) ? 32'd1 : noise_seed;
      for (int unsigned stage = 0; stage < 7; stage++) begin
        code_pipe[stage] <= 12'd2047;
        otr_pipe[stage] <= 1'b0;
        valid_pipe[stage] <= 1'b0;
      end
      raw_code <= #(T_CO_NS) 12'd2047;
      otr <= #(T_CO_NS) 1'b0;
      output_valid <= #(T_CO_NS) 1'b0;
    end else begin
      assert (!$isunknown({ideal_sample,force_otr_enable,force_otr_value}))
        else $fatal(1, "TEST_FAIL unknown AD9226 input");
      product_value = math_t'(ideal_sample) * math_t'(GAIN_Q16);
      // Q16 gain, round to nearest integer, ties away from zero. Every
      // intermediate is explicitly signed 64-bit; offset/noise are in LSB.
      if (product_value >= 64'sd0)
        rounded_value = (product_value + 64'sd32768) / 64'sd65536;
      else rounded_value = -((-product_value + 64'sd32768) / 64'sd65536);
      noise_word = advance_noise(noise_state);
      noise_state <= noise_word;
      noise_value = math_t'(noise_word % (32'd2 * NOISE_LSB + 32'd1)) - math_t'(NOISE_LSB);
      adjusted_value = rounded_value + math_t'(OFFSET_LSB) + noise_value;
      over_range = (adjusted_value < -64'sd2048 || adjusted_value > 64'sd2047);
      if (adjusted_value < -64'sd2048) clipped_value = -64'sd2048;
      else if (adjusted_value > 64'sd2047) clipped_value = 64'sd2047;
      else clipped_value = adjusted_value;
      encoded_value = adc_raw_t'(64'sd2047 - clipped_value);
      // Missing code means a code-bin remap, not dropping a time sample.
      if (MISSING_CODE_ENABLE && encoded_value == MISSING_CODE)
        encoded_value = MISSING_REPLACEMENT;
      code_pipe[0] <= encoded_value;
      otr_pipe[0] <= force_otr_enable ? force_otr_value : over_range;
      valid_pipe[0] <= 1'b1;
      for (int unsigned stage = 1; stage < 7; stage++) begin
        code_pipe[stage] <= code_pipe[stage-1];
        otr_pipe[stage] <= otr_pipe[stage-1];
        valid_pipe[stage] <= valid_pipe[stage-1];
      end
      raw_code <= #(T_CO_NS) code_pipe[6];
      otr <= #(T_CO_NS) otr_pipe[6];
      output_valid <= #(T_CO_NS) valid_pipe[6];
    end
  end
endmodule : ad9226_model
`default_nettype wire
