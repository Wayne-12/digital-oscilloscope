`default_nettype none
module spectrum_isqrt (
  input wire clk, rst, start,
  input wire [63:0] radicand,
  output logic busy, done,
  output logic [32:0] rounded_root
);
  timeunit 1ns; timeprecision 1ps;
  logic [63:0] operand;
  logic [65:0] remainder;
  logic [31:0] root;
  logic [5:0] count;
  logic [65:0] candidate, trial, next_remainder;
  logic [31:0] next_root;
  always_comb begin
    candidate = (remainder << 2) | {64'd0,operand[63:62]};
    trial = ({34'd0,root} << 2) | 66'd1;
    if (candidate >= trial) begin
      next_remainder = candidate - trial; next_root = (root << 1) | 32'd1;
    end else begin next_remainder = candidate; next_root = root << 1; end
  end
  always_ff @(posedge clk) begin
    if (rst) begin
      operand <= 64'd0; remainder <= 66'd0; root <= 32'd0;
      count <= 6'd0; busy <= 1'b0; done <= 1'b0; rounded_root <= 33'd0;
    end else begin
      done <= 1'b0;
      if (start && !busy) begin
        operand <= radicand; remainder <= 66'd0; root <= 32'd0;
        count <= 6'd0; busy <= 1'b1;
      end else if (busy) begin
        operand <= operand << 2; remainder <= next_remainder; root <= next_root;
        if (count == 6'd31) begin
          // Nearest integer: x-r^2 > r is equivalent to sqrt(x) > r+0.5.
          rounded_root <= {1'b0,next_root} + ((next_remainder > {34'd0,next_root}) ? 33'd1 : 33'd0);
          busy <= 1'b0; done <= 1'b1;
        end else count <= count + 6'd1;
      end
    end
  end
endmodule
`default_nettype wire
