`timescale 1ns/1ps
// Keep the registered read port inside this hierarchy. It must remain a BRAM
// output register rather than being absorbed into downstream arithmetic.
(* keep_hierarchy="yes" *)
module panel_wave_memory(input wire write_clk,read_clk,write_enable,
 input wire [14:0] write_address,read_address,input wire [11:0] write_data,
 output reg [11:0] read_data);
 (* ram_style="block" *) reg [11:0] memory[0:32767];
 always @(posedge write_clk)if(write_enable)memory[write_address]<=write_data;
 always @(posedge read_clk)read_data<=memory[read_address];
endmodule
