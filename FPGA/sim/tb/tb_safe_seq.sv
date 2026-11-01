`default_nettype none
// Canonical unit entry; reuses the existing self-checking scenario and watchdog.
module tb_safe_seq;
  timeunit 1ns;timeprecision 1ps;
  tb_safe scenario();
endmodule
`default_nettype wire
