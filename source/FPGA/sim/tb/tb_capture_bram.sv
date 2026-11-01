`default_nettype none
// Canonical unit entry; reuses the existing self-checking scenario and watchdog.
module tb_capture_bram;
  timeunit 1ns;timeprecision 1ps;
  tb_capture scenario();
endmodule
`default_nettype wire
