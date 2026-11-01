`default_nettype none
// Canonical unit entry; reuses the existing self-checking scenario and watchdog.
module tb_fft;
  timeunit 1ns;timeprecision 1ps;
  tb_spectrum scenario();
endmodule
`default_nettype wire
