`default_nettype none
// Canonical unit entry; reuses the existing self-checking scenario and watchdog.
module tb_dds_dac;
  timeunit 1ns;timeprecision 1ps;
  tb_dds scenario();
endmodule
`default_nettype wire
