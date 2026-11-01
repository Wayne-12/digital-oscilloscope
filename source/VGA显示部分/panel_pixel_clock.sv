`timescale 1ns/1ps
module panel_pixel_clock(input wire clk25,reset,output wire clk49,output wire locked);
 wire feedback,feedback_clk,pixel_raw;
 // Buffered sample clock: 25 / 2 * 49 = 612.5 MHz VCO; /12.5 = 49 MHz.
 MMCME2_BASE #(.CLKIN1_PERIOD(40.0),.DIVCLK_DIVIDE(2),
  .CLKFBOUT_MULT_F(49.0),.CLKOUT0_DIVIDE_F(12.5),.STARTUP_WAIT("FALSE")) mmcm(
  .CLKIN1(clk25),.CLKFBIN(feedback_clk),.CLKFBOUT(feedback),
  .CLKOUT0(pixel_raw),.LOCKED(locked),.RST(reset),.PWRDWN(1'b0));
 BUFG feedback_buffer(.I(feedback),.O(feedback_clk));
 BUFG pixel_buffer(.I(pixel_raw),.O(clk49));
endmodule
