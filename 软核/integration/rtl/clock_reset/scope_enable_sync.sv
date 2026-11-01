`default_nettype none
module scope_enable_sync (
  input wire logic clk,
  input wire logic rst,
  input wire logic module_enable,
  output wire logic enable_qualified
);
  timeunit 1ns;
  timeprecision 1ps;
  wire logic clear_request;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [1:0] enable_ff;
  // Removing enable clears qualification asynchronously, so even a short low
  // pulse cannot be missed. Assertion requires two falling-edge samples.
  assign clear_request = rst || !module_enable;
  always_ff @(negedge clk or posedge clear_request) begin
    if (clear_request) enable_ff <= 2'b00;
    else enable_ff <= {enable_ff[0], 1'b1};
  end
  assign enable_qualified = enable_ff[1];
endmodule : scope_enable_sync
`default_nettype wire
