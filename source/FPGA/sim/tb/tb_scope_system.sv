`default_nettype none
module tb_scope_system #(parameter integer CASE_ID=0);
  timeunit 1ns;timeprecision 1ps;
  tb_system_case #(.CASE_ID(CASE_ID)) scenario();
endmodule
`default_nettype wire
