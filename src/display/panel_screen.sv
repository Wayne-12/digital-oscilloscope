`timescale 1ns/1ps
module panel_screen(
 input wire clk,reset,pixel_clk,pixel_reset,
 input wire frame_start,tap_valid,tap_otr,analysis_done,analysis_error,
 input wire [13:0] tap_index,trigger_index,input wire [11:0] tap_raw,
 input wire automatic_trigger,input scope_pkg::measurement_result_t measurements,
 input wire [767:0] spectrum,input wire [127:0] saturation,
 input wire bin_valid,input wire [8:0] bin_index,input wire [63:0] bin_power,
 input wire [31:0] inputs,milliseconds,backend_status,
 input wire [7:0] bus_addr,input wire [31:0] bus_wdata,input wire bus_write,
 output reg [31:0] bus_rdata,
 output reg hsync=1,vsync=1,output reg [3:0] red=0,green=0,blue=0);
 `include "panel_calibration.svh"
 `include "panel_small_font.svh"
 localparam HT=1312,VT=624;
 (* ram_style="block" *) reg [7:0] spectrum_ram[0:1023];
 (* ram_style="block" *) reg [9:0] text_ram[0:4095];
 (* rom_style="block" *) reg [15:0] font[0:16383];
 (* rom_style="block" *) reg [11:0] small_font[0:2047];
 (* rom_style="block" *) reg [1:0] knob_ticks[0:16383];
 initial $readmemh("knob_ticks.mem",knob_ticks);
 initial $readmemh("font.mem",font);
 initial $readmemh("small_font.mem",small_font);
 reg [10:0] x=0,y=0;
 wire boundary=x==HT-1 && y==VT-1;
 reg sample_front=0,front=0,valid=0,capturing=0,pending=0;
 reg req=0,ack=0;
 (* ASYNC_REG="TRUE" *) reg [1:0] req_sync=0,ack_sync=0;
 reg ui_req=0,ui_ack=0,ui_bank=0,ui_valid=0;
 (* ASYNC_REG="TRUE" *) reg [1:0] ui_req_sync=0,ui_ack_sync=0;
 (* DONT_TOUCH="TRUE" *) reg [31:0] saved_control=0,shown_control=0,saved_cursor=0,shown_cursor=0,saved_page=0,shown_page=0;
 (* DONT_TOUCH="TRUE" *) reg [16:0] saved_knob=0,shown_knob=0;
 reg [31:0] frames=0;
 reg [13:0] saved_trigger=8192,shown_trigger=8192;
 reg saved_cal=0,shown_cal=0;
 reg [31:0] metric[0:16];
 wire stats_done,stats_cal,stats_complete;wire signed [31:0] mean;
 wire [31:0] vpp,rms,otr_count;wire signed [15:0] min_mv,max_mv;
 panel_stats stats(.clk(clk),.reset(reset),.start(frame_start && !pending),
  .valid(tap_valid && capturing),.finish(analysis_done),.otr(tap_otr),.raw(tap_raw),
  .done(stats_done),.calibrated(stats_cal),.complete(stats_complete),
  .mean_mv(mean),.vpp_mv(vpp),.rms_mv(rms),.otr_count(otr_count),.minimum_mv(min_mv),.maximum_mv(max_mv));
 function automatic [7:0] log_height(input [63:0] power);
  integer k;begin log_height=0;for(k=0;k<64;k=k+1)if(power[k])log_height=k*4;end
 endfunction
 integer i;
 always @(posedge clk)begin
  if(bin_valid && capturing)spectrum_ram[{!sample_front,bin_index}]<=log_height(bin_power);
  if(bus_write && bus_addr==96 && ui_ack_sync[1]==ui_req)
   text_ram[{!ui_req,bus_wdata[20:10]}]<=bus_wdata[9:0];
  if(reset)begin
   sample_front<=0;capturing<=0;pending<=0;req<=0;ack_sync<=0;frames<=0;
   ui_req<=0;ui_ack_sync<=0;saved_control<=0;saved_cursor<=0;saved_page<=0;
   saved_trigger<=8192;saved_cal<=0;saved_knob<=0;
   for(i=0;i<17;i=i+1)metric[i]<=0;
  end else begin
   ack_sync<={ack_sync[0],ack};ui_ack_sync<={ui_ack_sync[0],ui_ack};
   if(frame_start && !pending)capturing<=1;
   if(stats_done && capturing)begin
    capturing<=0;pending<=1;req<=!req;saved_trigger<=trigger_index;saved_cal<=stats_cal;
    metric[0]<=vpp;metric[1]<=measurements.frequency_hz;metric[2]<=rms;metric[3]<=mean;
    metric[4]<={25'd0,automatic_trigger,analysis_error,stats_complete,stats_cal,measurements.duty_valid,measurements.period_valid,measurements.stats_valid};
    metric[5]<=saturation[95:64];metric[6]<=otr_count;
    metric[7]<=spectrum[159:128];metric[8]<=spectrum[191:160];
    metric[9]<=spectrum[351:320];metric[10]<=spectrum[479:448];metric[11]<=spectrum[607:576];metric[12]<=spectrum[735:704];
    metric[13]<=spectrum[15:0];metric[14]<=measurements.duty_ppm;
    metric[15]<={{16{min_mv[15]}},min_mv};metric[16]<={{16{max_mv[15]}},max_mv};
   end
   if(pending && ack_sync[1]==req)begin pending<=0;sample_front<=!sample_front;frames<=frames+1'b1;end
   if(bus_write && ui_ack_sync[1]==ui_req)begin
    case(bus_addr)
     36:saved_control<=bus_wdata;
     104:saved_cursor<=bus_wdata;
     108:saved_page<=bus_wdata;
     136:saved_knob<=bus_wdata[16:0];
     100:ui_req<=!ui_req;
     default:begin end
    endcase
   end
  end
 end
 always_comb begin
  bus_rdata=0;
  case(bus_addr)
   28:bus_rdata=inputs;32:bus_rdata=backend_status;36:bus_rdata=saved_control;
   40:bus_rdata=milliseconds;44:bus_rdata=frames;
   100:bus_rdata={31'd0,ui_ack_sync[1]!=ui_req};
   default:if(bus_addr>=48 && bus_addr<=92)bus_rdata=metric[(bus_addr-48)>>2];
    else if(bus_addr>=112 && bus_addr<=128)bus_rdata=metric[12+((bus_addr-112)>>2)];
  endcase
 end
 always @(posedge pixel_clk)begin
  if(pixel_reset)begin
   x<=0;y<=0;front<=0;valid<=0;req_sync<=0;ack<=0;ui_req_sync<=0;ui_ack<=0;ui_bank<=0;ui_valid<=0;
   shown_control<=0;shown_cursor<=0;shown_page<=0;shown_trigger<=8192;shown_cal<=0;shown_knob<=0;
  end else begin
   req_sync<={req_sync[0],req};ui_req_sync<={ui_req_sync[0],ui_req};
   if(x==HT-1)begin x<=0;if(y==VT-1)y<=0;else y<=y+1'b1;end else x<=x+1'b1;
   if(boundary)begin
    if(req_sync[1]!=ack)begin front<=!front;valid<=1;ack<=req_sync[1];shown_trigger<=saved_trigger;shown_cal<=saved_cal;end
    if(ui_req_sync[1]!=ui_ack)begin
     ui_bank<=ui_req_sync[1];ui_ack<=ui_req_sync[1];ui_valid<=1;
     shown_control<=saved_control;shown_cursor<=saved_cursor;shown_page<=saved_page;shown_knob<=saved_knob;
    end
   end
  end
 end
 integer shift,start_index,address,span;
 reg [2:0] stretch_phase=0;
 reg [8:0] bin_offset=0;
 reg [13:0] full_offset=0;
 // Rational horizontal positions, without a wide divider in the BRAM path.
 // floor(pixel*4/5) for 512 FFT bins; floor(pixel*128/5) for 16K samples.
 always @(posedge pixel_clk)begin
  if(pixel_reset || x<32 || x>=672)begin stretch_phase<=0;bin_offset<=0;full_offset<=0;end
  else begin
   stretch_phase<=stretch_phase==4?0:stretch_phase+1'b1;
   if(stretch_phase!=0)bin_offset<=bin_offset+1'b1;
   full_offset<=full_offset+((stretch_phase==0 || stretch_phase==2)?14'd25:14'd26);
  end
 end
 always_comb begin
  case(shown_control[4:2])0:shift=0;1:shift=0;2:shift=2;3:shift=4;default:shift=5;endcase
  // Zoom needs the next endpoint too, including at the last visible column.
  span=shown_control[4:2]==0?161:shown_control[4:2]>=4?16384:(640<<shift);
  start_index=$signed({1'b0,shown_trigger})-span/2;
  if(start_index<0)start_index=0;
  if(start_index>16384-span)start_index=16384-span;
  address=start_index;
  if(shown_control[4:2]==0)begin
   // Prime sample A in the four pixels before the plot, then read sample B
   // for each visible interval. One synchronous BRAM port is sufficient.
   if(x>=28 && x<672)address=start_index+((x-28)>>2);
  end else if(x>=32 && x<672)begin
   // Ten divisions across the larger plot; the full-record view spans
   // exactly 16384 samples, with 25.6 sample intervals per pixel.
   address=start_index+(shown_control[4:2]>=4?{18'd0,full_offset}:((x-32)<<shift));
  end
 end
 // Synchronous memory -> voltage -> scaled coordinate -> font -> RGB.
 wire [11:0] sample;reg [7:0] bin=0;reg [15:0] font_row=0;reg [9:0] character=32;
 panel_wave_memory wave_memory(.write_clk(clk),.read_clk(pixel_clk),.write_enable(tap_valid && capturing),
  .write_address({!sample_front,tap_index}),.read_address({front,address[13:0]}),.write_data(tap_raw),.read_data(sample));
 reg [10:0] px0=0,py0=0,px1=0,py1=0,px2=0,py2=0,ix=0,iy=0,px=0,py=0;
 reg signed [15:0] mv=0;
 reg signed [19:0] scale_q4=0;
 wire signed [20:0] mv_q4={mv,5'b00000};
 wire signed [20:0] scaled_mv_q4=mv_q4/21'sd7;
 wire signed [19:0] interpolated_q4;
 panel_interpolator interpolation(.clk(pixel_clk),.reset(pixel_reset),
  .enable(shown_control[4:2]==0),.phase(px2[1:0]),.next_value(scale_q4),.value(interpolated_q4));
 reg [9:0] char1=32,char2=32,char3=32,char4=32;reg [7:0] bin1=0,bin2=0,bin3=0,bin4=0;
 reg [10:0] text_address;
 reg [3:0] compact_phase=0;
 reg [4:0] compact_column=0,compact_source_row,compact_glyph_row;
 reg compact_line,compact_area;
 wire readout_area=x>=704 && x<992 && (((shown_page==0 || shown_page==3 || shown_page==4) && y>=112 && y<392) || (shown_page==2 && y>=432 && y<456));
 reg [4:0] small_pipe=0;
 reg [4:0] glyph_rows[0:4];reg [3:0] glyph_columns[0:4];
 reg [11:0] small_font_row=0;reg small_selected=0;
 integer font_stage;
 always @(posedge pixel_clk)begin
  if(pixel_reset || x<720 || x>=960)begin compact_phase<=0;compact_column<=0;end
  else if(compact_phase==11)begin compact_phase<=0;compact_column<=compact_column+1'b1;end
  else compact_phase<=compact_phase+1'b1;
 end
 always_comb begin
  compact_line=1;compact_source_row=6;compact_glyph_row=0;
  if(y>=132 && y<156)begin compact_source_row=6;compact_glyph_row=y-132;end
  else if(y>=204 && y<228)begin compact_source_row=9;compact_glyph_row=y-204;end
  else if(y>=276 && y<300)begin compact_source_row=12;compact_glyph_row=y-276;end
  else if(y>=348 && y<372)begin compact_source_row=15;compact_glyph_row=y-348;end
  else if(shown_page==2 && y>=432 && y<456)begin compact_source_row=18;compact_glyph_row=y-432;end
  else compact_line=0;
  compact_area=readout_area && compact_line && x>=720 && x<960;
  text_address=(y/24)*64+(x>>4);
  // Cell zero is the reserved blank cell. Suppress the normal large text
  // in measurement cards, then map the compact line to its source cells.
  if(readout_area)text_address=compact_area?(compact_source_row*64+44+compact_column):11'd0;
 end
 wire [8:0] spectrum_address=(x>=32 && x<672)?bin_offset:9'd0;
 reg [3:0] font_column=0;
 reg [11:0] bg=0,fg=0,bg_delay=0,fg_delay=0;
 reg hs_delay=1,vs_delay=1;
 integer gain_shift;
 reg signed [14:0] wave_y_q4=4544,previous_y_q4=4544;
 reg signed [14:0] low_y_q4,high_y_q4;
 reg signed [16:0] coverage;
 reg signed [15:0] coverage_low,coverage_high;
 wire signed [15:0] row_center_q4=$signed({1'b0,py,4'b0000});
 wire signed [20:0] unbounded_y_q4=21'sd4544-($signed(interpolated_q4)>>>gain_shift);
 reg [11:0] trace_color;
 reg trace;integer cx1,cx2,cy1,cy2;
 reg signed [8:0] knob_x,knob_y;
 reg signed [10:0] knob_sum;
 wire [10:0] tick_x=ix>=832?ix-832:832-ix;
 wire [10:0] tick_y=iy>=288?iy-288:288-iy;
 reg [1:0] tick_pixel=0;
 reg signed [7:0] pointer_x,pointer_y;
 reg signed [18:0] knob_square,knob_cross,knob_dot;
 always @(posedge pixel_clk)begin
  bin<=spectrum_ram[{front,spectrum_address}];
  character<=text_ram[{ui_bank,text_address}];px0<=x;py0<=y;
  small_pipe<={small_pipe[3:0],compact_area};
  glyph_rows[0]<=compact_area?compact_glyph_row:5'(y%24);
  glyph_columns[0]<=compact_area?compact_phase:x[3:0];
  for(font_stage=1;font_stage<5;font_stage=font_stage+1)begin
   glyph_rows[font_stage]<=glyph_rows[font_stage-1];glyph_columns[font_stage]<=glyph_columns[font_stage-1];
  end
  mv<=to_mv(sample,shown_cal);char1<=character;bin1<=bin;px1<=px0;py1<=py0;
  scale_q4<=scaled_mv_q4;char2<=char1;bin2<=bin1;px2<=px1;py2<=py1;
  char3<=char2;bin3<=bin2;ix<=px2;iy<=py2;
  // Keep gain/clipping in a separate stage from pixel coverage and shading.
  wave_y_q4<=unbounded_y_q4<2320?15'sd2320:unbounded_y_q4>6752?15'sd6752:unbounded_y_q4;
  char4<=char3;bin4<=bin3;px<=ix;py<=iy;
  tick_pixel<=knob_ticks[{tick_y[6:0],tick_x[6:0]}];
 end
 always_comb begin
  case(shown_control[7:6])0:gain_shift=4;1:gain_shift=2;2:gain_shift=1;default:gain_shift=0;endcase
  low_y_q4=wave_y_q4;high_y_q4=wave_y_q4;
  if(px!=32)begin
   if(previous_y_q4<low_y_q4)low_y_q4=previous_y_q4;
   if(previous_y_q4>high_y_q4)high_y_q4=previous_y_q4;
  end
  // Preserve 1/16-pixel precision through scaling. Partial coverage shades
  // the two boundary pixels instead of rounding every point to a hard step.
  coverage_low=low_y_q4-16'sd8;if(coverage_low<(row_center_q4-16'sd8))coverage_low=row_center_q4-16'sd8;
  coverage_high=high_y_q4+16'sd8;if(coverage_high>(row_center_q4+16'sd8))coverage_high=row_center_q4+16'sd8;
  coverage=coverage_high-coverage_low;
  trace_color=12'hfe5;
  if(coverage>0 && coverage<16)trace_color={4'(coverage),4'((coverage*14)>>4),4'(1+((coverage*4)>>4))};
  cx1=32+shown_cursor[9:0];cx2=32+shown_cursor[25:16];
  cy1=144+shown_control[16:8];cy2=144+shown_control[25:17];
  bg=12'h112;fg=12'hcde;trace=0;
  knob_x=$signed({1'b0,px})-832;knob_y=$signed({1'b0,py})-288;
  pointer_x=shown_knob[7:0];pointer_y=shown_knob[15:8];
  knob_square=knob_x*knob_x+knob_y*knob_y;
  knob_sum=knob_x+knob_y;
  knob_cross=knob_x*pointer_y-knob_y*pointer_x;
  knob_dot=knob_x*pointer_x+knob_y*pointer_y;
  if(py<56)bg=12'h124;
  if(px>=32 && px<992 && py>=64 && py<104)begin
   bg=12'h123;if(px==32 || px==991 || py==64 || py==103)bg=12'h345;
  end
  if((shown_page==0 || shown_page==3 || shown_page==4) && px>=704 && px<992 && py>=112 && py<392)begin
   if((py-112)%72<64)bg=12'h123;
  end
  if((shown_page==0 || shown_page==3 || shown_page==4) && px>=32 && px<=672 && py>=144 && py<=424)begin
   bg=12'h001;
   if(((px-32)%64==0 && py[2:0]==0) || ((py-144)%40==0 && px[2:0]==0))bg=12'h334;
   if(py==284 || px==352)bg=12'h556;
   if(px==32 || px==672 || py==144 || py==424)bg=12'h556;
   if(valid && px<672 && py>144 && py<424)begin
    if(shown_page==4)trace=(py>=423-bin4 && py<=423);
    else trace=coverage>0;
   end
   if(trace)bg=shown_page==4?12'h6bf:trace_color;
   if(shown_page==3 && (px==cx1 || px==cx2 || py==cy1 || py==cy2))bg=12'h9cf;
  end
  if(py>=552)fg=12'h9bc;
  if(shown_page==0 && px>=704 && px<992 && py>=448 && py<536)begin
   bg=shown_control[30]?12'h245:12'h123;
   if(px==704 || px==991 || py==448 || py==535)bg=shown_control[30]?12'h9bc:12'h456;
  end
  if(shown_page==3 && py>=448 && py<536 &&
     ((px>=32 && px<504) || (px>=520 && px<992)))begin
   bg=12'h123;
   if(px==32 || px==503 || px==520 || px==991 || py==448 || py==535)bg=12'h456;
  end
  if(shown_page==4 && px>=32 && px<992 && py>=448 && py<536)begin
   bg=12'h123;
   if(px==32 || px==991 || py==448 || py==535)bg=12'h456;
   if(py>=496 && py<532 && ((px>=112 && px<248) || (px>=352 && px<488) ||
      (px>=592 && px<728) || (px>=832 && px<968)))begin
    bg=12'h112;
    if(py==496 || py==531 || px==112 || px==247 || px==352 || px==487 ||
       px==592 || px==727 || px==832 || px==967)bg=12'h456;
   end
  end
  if(shown_page==5 && px>=64 && px<320)begin
   if(py>=208 && py<248)begin
    bg=shown_control[26]?12'h245:12'h123;
    if(px==64 || px==319 || py==208 || py==247)bg=shown_control[26]?12'h9bc:12'h456;
   end
   if(py>=256 && py<296)begin
    case(shown_control[28:27])
     1:bg=12'h173;
     2:bg=12'h811;
     3:bg=12'h234;
     default:bg=12'h123;
    endcase
    if(px==64 || px==319 || py==256 || py==295)
     bg=shown_control[28:27]==1?12'h5b7:shown_control[28:27]==2?12'hc66:12'h456;
   end
  end
  // Offset shadow, bevel rings and directional face lighting give depth.
  // Reuse the radius squared; the shadow needs only shifts/adds.
  if(shown_page==2 && px>=720 && px<=944 && py>=176 && py<=400)begin
   // Match the indicator sweep: 135 degrees through the top to 405 degrees.
   // Both endpoint marks are included; the bottom 90-degree sector is empty.
   if(knob_y<=knob_x || knob_y<=-knob_x)begin
    if(tick_pixel==1)bg=12'h456;
    if(tick_pixel==2)bg=12'h89a;
   end
   if(knob_square-12*knob_x-14*knob_y+85<=6724)bg=12'h001;
   if(knob_square<=6724)bg=12'h123;
   if(knob_square<=6400)bg=knob_sum<0?12'h678:12'h234;
   if(knob_square<6084)bg=12'h4bd;
   if(knob_square<5625)bg=12'h123;
   if(knob_square<5184)bg=12'h234;
   // Filled triangle: tip at radius 64, base at radius 40, half-width 9.
   // Dot/cross coordinates rotate the entire triangle with the indicator.
   if(shown_knob[16] && knob_square<4900 && knob_dot>=2560 && knob_dot<=4096 &&
      knob_cross*8>=(knob_dot-4096)*3 && knob_cross*8<=(4096-knob_dot)*3)bg=12'h456;
   if(knob_square<16)bg=12'h345;
  end
  if(ui_valid && char4[9])begin bg=12'h245;fg=12'hffe;end
  if(px>=1024 || py>=600)begin bg=0;fg=0;end
 end
 always @(posedge pixel_clk)begin
  font_row<=font[{char4[8:0],glyph_rows[4]}];font_column<=glyph_columns[4];
  small_font_row<=small_font[{small_glyph(char4[8:0]),glyph_rows[4]}];small_selected<=small_pipe[4];
  bg_delay<=bg;fg_delay<=fg;hs_delay<=!(px>=1072 && px<1168);vs_delay<=!(py>=603 && py<613);
  if(px>=32 && px<672)previous_y_q4<=wave_y_q4;
  hsync<=hs_delay;vsync<=vs_delay;
  {red,green,blue}<=(ui_valid && (small_selected?small_font_row[11-font_column]:font_row[15-font_column])) ? fg_delay:bg_delay;
  if(pixel_reset)begin hsync<=1;vsync<=1;{red,green,blue}<=0;end
 end
endmodule
