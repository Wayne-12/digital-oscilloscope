`default_nettype none
// Simulation only: 1ps quantization of ideal half-periods, never synthesized.
module ideal_clock (
  input wire logic [31:0] frequency_hz,
  output logic clk
);
  timeunit 1ns;
  timeprecision 1ps;
  realtime half_period_ns;
  initial begin
    clk = 1'b0;
    #1ps;
    forever begin
      assert (!$isunknown(frequency_hz) && frequency_hz > 32'd0)
        else $fatal(1, "TEST_FAIL invalid ideal-clock frequency");
      half_period_ns = 500000000.0 / real'(frequency_hz);
      #(half_period_ns) clk = 1'b1;
      #(half_period_ns) clk = 1'b0;
    end
  end
endmodule : ideal_clock
`default_nettype wire
