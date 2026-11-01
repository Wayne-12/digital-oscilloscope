`default_nettype none
// Canonical unit entry; reuses the existing self-checking scenario and watchdog.
module tb_adc_capture;
  timeunit 1ns;timeprecision 1ps;
  tb_ad9226 scenario();
endmodule
`default_nettype wire
