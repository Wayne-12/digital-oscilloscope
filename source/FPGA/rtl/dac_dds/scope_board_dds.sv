`default_nettype none
// Physical-board DDS pipeline. Same integer rounding/saturation as dds_core;
// a stable configuration yields its code sequence delayed by three clocks.
module scope_board_dds(
  input wire clk_dac,rst,enable,
  input wire awg_selected,
  input wire signed [15:0] awg_play_value,
  output wire [9:0] awg_play_index,
  input wire scope_pkg::dds_wave_t waveform,
  input wire [31:0] phase_inc,phase_offset,
  input wire [15:0] amplitude,
  input wire signed [17:0] dc_offset,
  output logic [13:0] dac_code
);
  timeunit 1ns;timeprecision 1ps;
  logic [31:0] accumulator,phase;
  wire [31:0] awg_phase=accumulator+phase_offset;
  assign awg_play_index=awg_phase[31:22];
  wire signed [15:0] sine;
  logic signed [15:0] wave;
  logic [15:0] amplitude_pipe;
  logic signed [32:0] product;
  logic signed [17:0] scaled,offset_a,offset_b,offset_c;
  logic [3:0] valid;
  wire signed [19:0] biased=20'sd8192+{{2{scaled[17]}},scaled}+{{2{offset_c[17]}},offset_c};
  dds_sine_lut lut(.address(phase[31:22]),.value(sine));
  function automatic logic signed [15:0] triangle(input logic [9:0] address);
    logic signed [10:0] x;
    logic signed [26:0] numerator;
    logic [26:0] magnitude,rounded;
    if(address<10'd256)x=$signed({1'b0,address});
    else if(address<10'd768)x=11'sd512-$signed({1'b0,address});
    else x=$signed({1'b0,address})-11'sd1024;
    numerator=x*16'sd32767;
    magnitude=numerator<0?-numerator:numerator;
    rounded=(magnitude+27'd128)>>8;
    return numerator<0?-$signed(rounded[15:0]):$signed(rounded[15:0]);
  endfunction
  function automatic logic signed [17:0] normalize(input logic signed [32:0] p);
    logic [32:0] magnitude,n;
    logic [17:0] folded;
    logic [17:0] quotient;
    magnitude=p<0?-p:p;
    n=magnitude+33'd16383;
    // Exact division by 32767=2^15-1 within |p|<=32767*65535.
    // n=a*32768+b => floor(n/32767)=a+floor((a+b)/32767).
    folded={3'b0,n[14:0]}+n[32:15];
    quotient=n[32:15]+(folded>=18'd98301 ? 18'd3 :
      folded>=18'd65534 ? 18'd2 : folded>=18'd32767 ? 18'd1 : 18'd0);
    return p<0?-$signed(quotient):$signed(quotient);
  endfunction
  always_ff @(negedge clk_dac)begin
    if(rst||!enable)begin
      accumulator<=0;phase<=0;wave<=0;amplitude_pipe<=0;product<=0;
      scaled<=0;offset_a<=0;offset_b<=0;offset_c<=0;valid<=0;dac_code<=14'd8192;
    end else begin
      accumulator<=accumulator+phase_inc;phase<=accumulator+phase_offset;
      if(awg_selected===1'b1)wave<=awg_play_value;
      else case(waveform)
        scope_pkg::DDS_SINE:wave<=sine;
        scope_pkg::DDS_SQUARE:wave<=phase[31]?-16'sd32767:16'sd32767;
        scope_pkg::DDS_TRIANGLE:wave<=triangle(phase[31:22]);
        default:wave<=16'sd0;
      endcase
      amplitude_pipe<=amplitude;offset_a<=dc_offset;
      product<=wave*$signed({1'b0,amplitude_pipe});offset_b<=offset_a;
      scaled<=normalize(product);offset_c<=offset_b;
      valid<={valid[2:0],1'b1};
      if(!valid[3])dac_code<=14'd8192;
      else if(biased<0)dac_code<=0;
      else if(biased>20'sd16383)dac_code<=14'd16383;
      else dac_code<=biased[13:0];
    end
  end
endmodule
`default_nettype wire
