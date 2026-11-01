"""Generate immutable periodic Hann Q0.16 ROM and exact calibration constants."""
import argparse,math
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--fpga-root',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args()
n=1024;coeff=[math.floor(65536*(0.5-0.5*math.cos(2*math.pi*i/n))+0.5) for i in range(n)]
assert sum(coeff)==n*32768
pkg='''`default_nettype none
package fft_window_pkg;
  timeunit 1ns;timeprecision 1ps;
  localparam logic [31:0] HANN_SUM_Q16=32'd%d;
  localparam logic [63:0] HANN_SQUARE_SUM_Q32=64'd%d;
endpackage
`default_nettype wire
'''%(sum(coeff),sum(w*w for w in coeff))
rom='''`default_nettype none
module fft_hann_lut(input wire logic [9:0] address,output logic [16:0] coefficient);
  timeunit 1ns;timeprecision 1ps;
  always_comb begin
    case(address)
'''+''.join(f"      10'd{i}:coefficient=17'd{c};\n" for i,c in enumerate(coeff))+'''      default:coefficient=17'd0;
    endcase
  end
endmodule
`default_nettype wire
'''
(a.fpga_root/'rtl/common/fft_window_pkg.sv').write_text(pkg,encoding='utf8');(a.fpga_root/'rtl/measure/fft_hann_lut.sv').write_text(rom,encoding='utf8')
print('FFT_TABLES_PASS',sum(coeff),sum(w*w for w in coeff))
