`default_nettype none
package fft_window_pkg;
  timeunit 1ns;timeprecision 1ps;
  localparam logic [31:0] HANN_SUM_Q16=32'd33554432;
  localparam logic [63:0] HANN_SQUARE_SUM_Q32=64'd1649267045280;
endpackage
`default_nettype wire
