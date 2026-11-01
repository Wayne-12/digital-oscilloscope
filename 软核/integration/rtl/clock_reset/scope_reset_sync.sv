`default_nettype none
module scope_reset_sync #(
  parameter bit FALLING_EDGE = 1'b0
) (
  input wire logic clk,
  input wire logic arst,
  output wire logic rst
);
  timeunit 1ns;
  timeprecision 1ps;
  // Safety exception to synchronous-only reset: asynchronous assertion works
  // even when a source clock disappears; release requires two local edges.
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [1:0] release_ff;
  generate
    if (FALLING_EDGE) begin : g_falling
      always_ff @(negedge clk or posedge arst) begin
        if (arst) release_ff <= 2'b11;
        else release_ff <= {release_ff[0], 1'b0};
      end
    end else begin : g_rising
      always_ff @(posedge clk or posedge arst) begin
        if (arst) release_ff <= 2'b11;
        else release_ff <= {release_ff[0], 1'b0};
      end
    end
  endgenerate
  assign rst = release_ff[1];
endmodule : scope_reset_sync
`default_nettype wire
