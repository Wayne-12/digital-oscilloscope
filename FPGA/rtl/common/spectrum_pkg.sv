`default_nettype none
package spectrum_pkg;
  timeunit 1ns; timeprecision 1ps;
  localparam int unsigned FFT_N = 1024;
  localparam int unsigned FFT_INPUT_SHIFT = 3;
  typedef struct packed {
    logic [63:0] first_timestamp;
    logic [31:0] sample_rate;
    logic [17:0] source_first_index;
    logic hann;
    logic [31:0] window_sum_q16;
    logic [63:0] window_square_sum_q32;
  } spectrum_metadata_t;
  typedef struct packed {
    logic [10:0] index;
    logic signed [31:0] real_part;
    logic signed [31:0] imag_part;
    logic [63:0] power;
    logic last;
  } spectrum_bin_t;
  typedef struct packed {
    logic measurement_valid;
    logic clipped;
    logic [10:0] peak_bin;
    logic [31:0] frequency_hz;
    logic [31:0] amplitude_q16;
    logic [31:0] rms_q16;
    logic signed [31:0] dc_mean_q16;
    logic [63:0] peak_power;
    spectrum_metadata_t metadata;
  } spectrum_result_t;
endpackage
`default_nettype wire
