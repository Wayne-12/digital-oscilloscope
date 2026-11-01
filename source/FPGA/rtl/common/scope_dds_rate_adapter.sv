`default_nettype none
// The UART command's tuning word is defined at 25 MSPS. Recompute the same
// nominal output frequency for the selected DAC sample rate. Nearest integer,
// ties upward for an unsigned frequency word; 64-bit product has 8 guard bits.
module scope_dds_rate_adapter #(
  parameter int unsigned DAC_RATE_HZ=25000000
)(input wire logic [31:0] phase_inc_25m, output logic [31:0] phase_inc_actual);
  timeunit 1ns;timeprecision 1ps;
  logic [63:0] numerator, quotient;
  always_comb begin
    numerator={32'd0,phase_inc_25m}*64'd25000000+64'(DAC_RATE_HZ/2);
    quotient=numerator/64'(DAC_RATE_HZ);
    phase_inc_actual=quotient[31:0];
  end
  // synthesis translate_off
  initial assert(DAC_RATE_HZ==10000000||DAC_RATE_HZ==25000000||DAC_RATE_HZ==50000000||DAC_RATE_HZ==65000000)
    else $fatal(1,"DDS_RATE_CONFIG");
  // synthesis translate_on
endmodule
`default_nettype wire
