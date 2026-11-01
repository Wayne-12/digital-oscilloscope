`default_nettype none
// Temporary design top for project/simulator bring-up; not a board top.
module smoke_counter #(
  parameter int unsigned COUNTER_WIDTH = 8
) (
  input wire logic clk,
  input wire logic rst,
  output logic [COUNTER_WIDTH-1:0] count
);
  timeunit 1ns;
  timeprecision 1ps;
  typedef logic [COUNTER_WIDTH-1:0] count_t;

  // Active-high synchronous reset. No declaration/initial-state assignment.
  // Unsigned modulo-2**COUNTER_WIDTH arithmetic; no rounding or saturation.
  always_ff @(posedge clk) begin
    if (rst) begin
      count <= count_t'('0);
    end else begin
      count <= count + count_t'(1'b1);
    end
  end
endmodule : smoke_counter
`default_nettype wire
