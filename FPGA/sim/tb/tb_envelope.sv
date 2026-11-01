`default_nettype none
// Canonical unit entry; reuses the existing self-checking scenario and watchdog.
module tb_envelope;
  timeunit 1ns;timeprecision 1ps;
  tb_multires scenario();
endmodule
`default_nettype wire
