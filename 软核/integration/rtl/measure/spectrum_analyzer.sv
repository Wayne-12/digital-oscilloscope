`default_nettype none
module spectrum_analyzer (
  input wire clk, rst, module_enable, start,
  output wire start_ready,
  input wire cfg_hann,
  input wire [31:0] cfg_sample_rate,
  input wire [63:0] cfg_first_timestamp,
  input wire [17:0] cfg_source_first_index,
  input wire [31:0] cfg_threshold_q16,
  input wire sample_valid,
  output wire sample_ready,
  input wire signed [12:0] sample_signed,
  input wire sample_otr,
  input wire [63:0] sample_timestamp,
  input wire sample_last,
  output wire metadata_valid,
  input wire metadata_ready,
  output spectrum_pkg::spectrum_metadata_t metadata,
  output wire bin_valid,
  input wire bin_ready,
  output spectrum_pkg::spectrum_bin_t bin_data,
  output wire result_valid,
  input wire result_ready,
  output spectrum_pkg::spectrum_result_t result,
  output logic config_error, cancelled
);
  timeunit 1ns; timeprecision 1ps;
  import spectrum_pkg::*;
  typedef enum logic [3:0] {IDLE, START_FFT, STREAM, SQRT_AMP_START, SQRT_AMP_WAIT,
                            SQRT_RMS_START, SQRT_RMS_WAIT, REPORT} state_t;
  state_t state;
  logic meta_pending;
  logic [31:0] threshold_q16;
  logic [10:0] input_index, peak_index;
  logic [63:0] peak_power;
  logic clipped;
  logic signed [31:0] dc_value;
  logic [31:0] amplitude;
  wire fft_start_ready, fft_in_ready, fft_out_valid, fft_last;
  wire signed [31:0] fft_real, fft_imag;
  wire [10:0] fft_bin;
  wire fft_done, fft_cancelled, fft_error;
  wire [16:0] hann_coefficient;
  logic [16:0] coefficient;
  logic signed [15:0] shifted_sample, weighted_sample;
  logic signed [33:0] product, rounded;
  wire [53:0] real_square, imag_square;
  wire [63:0] current_power = {10'd0,real_square} + {10'd0,imag_square};
  wire positive_bin = metadata.hann ? (fft_bin >= 11'd2 && fft_bin <= 11'd510) :
                                             (fft_bin >= 11'd1 && fft_bin <= 11'd511);
  wire sqrt_busy, sqrt_done;
  wire [32:0] sqrt_root;
  logic [63:0] radicand;
  wire sqrt_start = state == SQRT_AMP_START || state == SQRT_RMS_START;
  logic [63:0] frequency_product;
  assign start_ready = module_enable && !rst && state == IDLE && fft_start_ready;
  assign sample_ready = state == STREAM && fft_in_ready;
  assign metadata_valid = module_enable && !rst && meta_pending;
  assign bin_valid = module_enable && !rst && !meta_pending && state == STREAM && fft_out_valid;
  assign result_valid = module_enable && !rst && state == REPORT;
  assign real_square = $signed(fft_real[26:0]) * $signed(fft_real[26:0]);
  assign imag_square = $signed(fft_imag[26:0]) * $signed(fft_imag[26:0]);
  always_comb begin
    coefficient = metadata.hann ? hann_coefficient : 17'd65536;
    shifted_sample = $signed({sample_signed,3'b000});
    product = shifted_sample * $signed({1'b0,coefficient});
    if (product < 34'sd0) rounded = -(((-product) + 34'sd32768) >>> 16);
    else rounded = (product + 34'sd32768) >>> 16;
    weighted_sample = rounded[15:0];
    bin_data.index = fft_bin; bin_data.real_part = fft_real; bin_data.imag_part = fft_imag;
    bin_data.power = current_power; bin_data.last = fft_last;
    if (state == SQRT_RMS_START || state == SQRT_RMS_WAIT)
      radicand = metadata.hann ? peak_power << 9 : peak_power << 7;
    else radicand = metadata.hann ? peak_power << 10 : peak_power << 8;
    frequency_product = {53'd0,peak_index} * {32'd0,metadata.sample_rate} + 64'd512;
  end
  fft_hann_lut hann_lut (.address(input_index[9:0]), .coefficient(hann_coefficient));
  fft_ip_wrapper wrapper (
    .clk(clk),.rst(rst),.module_enable(module_enable),.start(state == START_FFT),
    .start_ready(fft_start_ready),.cfg_inverse(1'b0),
    .in_valid(state == STREAM && sample_valid),.in_ready(fft_in_ready),
    .in_real(weighted_sample),.in_imag(16'sd0),.in_last(sample_last),
    .out_valid(fft_out_valid),.out_ready(state == STREAM && !meta_pending && bin_ready),
    .out_real(fft_real),.out_imag(fft_imag),.out_bin(fft_bin),.out_last(fft_last),
    .done(fft_done),.cancelled(fft_cancelled),.protocol_error(fft_error)
  );
  spectrum_isqrt square_root(.clk(clk),.rst(rst || !module_enable),.start(sqrt_start),
    .radicand(radicand),.busy(sqrt_busy),.done(sqrt_done),.rounded_root(sqrt_root));
  always_ff @(posedge clk) begin
    if (rst) begin
      state <= IDLE; meta_pending <= 1'b0; metadata <= '0; threshold_q16 <= 32'd0;
      input_index <= 11'd0; peak_index <= 11'd0; peak_power <= 64'd0;
      clipped <= 1'b0; dc_value <= 32'sd0; amplitude <= 32'd0; result <= '0;
      config_error <= 1'b0; cancelled <= 1'b0;
    end else begin
      config_error <= 1'b0; cancelled <= 1'b0;
      if (!module_enable) begin
        cancelled <= state != IDLE; state <= IDLE; meta_pending <= 1'b0; result <= '0;
        input_index <= 11'd0; peak_power <= 64'd0; peak_index <= 11'd0;
        clipped <= 1'b0; dc_value <= 32'sd0; amplitude <= 32'd0;
      end else begin
        if (metadata_valid && metadata_ready) meta_pending <= 1'b0;
        case (state)
          IDLE: if (start && start_ready) begin
            if (cfg_sample_rate == 32'd0 || cfg_source_first_index > 18'd130048) config_error <= 1'b1;
            else begin
              metadata.first_timestamp <= cfg_first_timestamp; metadata.sample_rate <= cfg_sample_rate;
              metadata.source_first_index <= cfg_source_first_index; metadata.hann <= cfg_hann;
              metadata.window_sum_q16 <= cfg_hann ? fft_window_pkg::HANN_SUM_Q16 : 32'd67108864;
              metadata.window_square_sum_q32 <= cfg_hann ? fft_window_pkg::HANN_SQUARE_SUM_Q32 : 64'd4398046511104;
              threshold_q16 <= cfg_threshold_q16; meta_pending <= 1'b1;
              input_index <= 11'd0; peak_index <= 11'd0; peak_power <= 64'd0;
              clipped <= 1'b0; dc_value <= 32'sd0; result <= '0; state <= START_FFT;
            end
          end
          START_FFT: if (fft_start_ready) state <= STREAM;
          STREAM: begin
            if (sample_valid && sample_ready) begin
              input_index <= input_index + 11'd1; clipped <= clipped || sample_otr;
            end
            if (bin_valid && bin_ready) begin
              if (fft_bin == 11'd0) dc_value <= metadata.hann ? fft_real <<< 4 : fft_real <<< 3;
              if (positive_bin && current_power > peak_power) begin peak_power <= current_power; peak_index <= fft_bin; end
              if (fft_last) state <= SQRT_AMP_START;
            end
          end
          SQRT_AMP_START: state <= SQRT_AMP_WAIT;
          SQRT_AMP_WAIT: if (sqrt_done) begin amplitude <= sqrt_root[31:0]; state <= SQRT_RMS_START; end
          SQRT_RMS_START: state <= SQRT_RMS_WAIT;
          SQRT_RMS_WAIT: if (sqrt_done) begin
            result.metadata <= metadata; result.clipped <= clipped;
            result.dc_mean_q16 <= dc_value; result.peak_power <= peak_power;
            result.measurement_valid <= peak_power != 64'd0 && amplitude >= threshold_q16;
            if (peak_power != 64'd0 && amplitude >= threshold_q16) begin
              result.peak_bin <= peak_index; result.frequency_hz <= frequency_product[41:10];
              result.amplitude_q16 <= amplitude; result.rms_q16 <= sqrt_root[31:0];
            end else begin
              result.peak_bin <= 11'd0; result.frequency_hz <= 32'd0;
              result.amplitude_q16 <= 32'd0; result.rms_q16 <= 32'd0;
            end
            state <= REPORT;
          end
          REPORT: if (result_ready) state <= IDLE;
          default: state <= IDLE;
        endcase
      end
    end
  end
`ifndef SYNTHESIS
  always_ff @(posedge clk) if (!rst && module_enable) begin
    assert(!fft_error) else $fatal(1,"SPECTRUM_FFT_PROTOCOL");
    if (sample_valid && sample_ready) begin
      assert(sample_last == (input_index == 11'd1023)) else $fatal(1,"SPECTRUM_INPUT_TLAST");
      assert(sample_timestamp == metadata.first_timestamp + {53'd0,input_index}) else $fatal(1,"SPECTRUM_TIMESTAMP");
      assert(rounded >= -34'sd32768 && rounded <= 34'sd32767) else $fatal(1,"SPECTRUM_WINDOW_RANGE");
    end
    if (sqrt_start) assert(peak_power[63:54] == 10'd0 && !sqrt_busy) else $fatal(1,"SPECTRUM_POWER_OVERFLOW");
    if (sqrt_done) assert(!sqrt_root[32]) else $fatal(1,"SPECTRUM_AMPLITUDE_OVERFLOW");
  end
`endif
endmodule
`default_nettype wire
