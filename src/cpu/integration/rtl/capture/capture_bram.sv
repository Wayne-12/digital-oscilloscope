`default_nettype none
// Simple dual-port inferred BRAM, independent write/read clocks.
// No reset on RAM contents/output register: only fully initialized frozen
// frames are readable and the enclosing valid register has synchronous reset.
module capture_bram (
  input wire logic write_clk, write_enable,
  input wire scope_pkg::bram_addr_t write_address,
  input wire scope_pkg::sample_word_t write_word,
  input wire logic read_clk, read_enable,
  input wire scope_pkg::bram_addr_t read_address,
  output scope_pkg::sample_word_t read_word
);
  timeunit 1ns;timeprecision 1ps;
  (* ram_style="block" *) logic [15:0] memory[0:16383];
  always @(posedge write_clk)
    if(write_enable)memory[write_address]<=write_word;
  always @(posedge read_clk)
    if(read_enable)read_word<=memory[read_address];
endmodule
`default_nettype wire
