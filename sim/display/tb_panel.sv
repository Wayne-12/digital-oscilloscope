`timescale 1ns/1ps
module tb_panel;
 reg clk=0,pixel_clk=0;always #20 clk=~clk;always #10.204 pixel_clk=~pixel_clk;
 reg reset=1,start=0,tap=0,finish=0,otr=0;
 reg [13:0] index=0;reg [11:0] raw=2048;
 reg [13:0] trigger=8192;
 reg [7:0] address=0;reg [31:0] wdata=0;reg write=0;
 wire [31:0] rdata;wire hs,vs;wire [3:0] r,g,b;
 scope_pkg::measurement_result_t measurements;
 reg [767:0] spectrum=0;
 wire interpolation_done;
 tb_interpolator interpolation_test(.done(interpolation_done));
 panel_screen dut(.clk(clk),.reset(reset),.pixel_clk(pixel_clk),.pixel_reset(reset),
 .frame_start(start),.tap_valid(tap),.tap_otr(otr),.analysis_done(finish),.analysis_error(1'b0),
 .tap_index(index),.tap_raw(raw),.trigger_index(trigger),.automatic_trigger(1'b0),
 .measurements(measurements),.spectrum(spectrum),.saturation(128'd0),
 .bin_valid(1'b0),.bin_index(9'd0),.bin_power(64'd0),.inputs(32'd0),.milliseconds(32'd0),.backend_status(32'd5),
 .bus_addr(address),.bus_wdata(wdata),.bus_write(write),.bus_rdata(rdata),
 .hsync(hs),.vsync(vs),.red(r),.green(g),.blue(b));
 task bus(input [7:0] a,input [31:0] v);
 begin @(negedge clk);address=a;wdata=v;write=1;@(negedge clk);write=0;end endtask
 task record(input integer value,input integer one_outside);
 integer i;begin
  @(negedge clk);start=1;finish=0;@(negedge clk);start=0;
  for(i=0;i<16384;i=i+1)begin
   index=i;raw=one_outside==2 ? (1920+(i%16)*16) : (one_outside && i==14000)?3000:value;tap=1;otr=i==100;
   @(negedge clk);tap=0;@(negedge clk);
  end
  otr=0;finish=1;repeat(30)@(negedge clk);
 end endtask
 integer i,expected;reg [11:0] old_pixel;reg [15:0] page[0:1599];
 initial begin
  measurements='0;measurements.stats_valid=1;measurements.period_valid=1;measurements.frequency_hz=1000000;
  $readmemh("page_0.mem",page);
  repeat(10)@(negedge clk);reset=0;
  for(i=0;i<1600;i=i+1)bus(96,(i<<10)|page[i]);
  bus(36,32'hc1);bus(104,(384<<16)|128);bus(108,0);bus(100,1);
  record(2054,0);
  wait(dut.frames==1);@(negedge clk);
  address=64;#1;if(!(rdata&8))$fatal(1,"calibrated frame flag");
  address=60;#1;if($signed(rdata)<-2 || $signed(rdata)>2)$fatal(1,"calibrated DC mean %d",$signed(rdata));
  address=72;#1;if(rdata!=1)$fatal(1,"OTR count");
  if(dut.front!=1 || !dut.valid)$fatal(1,"frame bank swap");
  repeat(100)@(negedge clk);if(dut.frames!=1)$fatal(1,"frozen frame changed");
  wait(dut.px==896 && dut.py==139);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h123)$fatal(1,"compact value-unit gap %h",{r,g,b});
  wait(dut.px==902 && dut.py==139);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'hcde)$fatal(1,"compact kHz glyph alignment %h",{r,g,b});
  wait(dut.px==704 && dut.py==448);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"autoscale button border %h",{r,g,b});
  wait(dut.px==704 && dut.py==535);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"autoscale two-row height %h",{r,g,b});
  wait(dut.px==704 && dut.py==536);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"autoscale bottom boundary %h",{r,g,b});
  record(2054,1);
  wait(dut.frames==2);@(negedge clk);
  address=64;#1;if(rdata&8)$fatal(1,"out-of-range frame must use nominal mV");
  address=48;#1;if(rdata<2300 || rdata>2320)$fatal(1,"nominal Vpp %d",rdata);
  if(dut.front!=0)$fatal(1,"second frame bank swap");
  wait(dut.px==1100 && dut.py==100);repeat(3)@(negedge pixel_clk);
  if(hs!==0 || {r,g,b}!==0)$fatal(1,"sync/blanking");
  $readmemh("page_2.mem",page);
  for(i=0;i<1600;i=i+1)bus(96,(i<<10)|page[i]);
  bus(108,2);bus(136,32'h1c000);bus(100,1);wait(dut.ui_ack==0);
  if(dut.shown_knob!=17'h1c000)$fatal(1,"knob update at frame boundary");
  wait(dut.px==832 && dut.py==180);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h89a)$fatal(1,"knob top scale tick %h",{r,g,b});
  wait(dut.px==832 && dut.py==210);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h678)$fatal(1,"knob upper bevel highlight %h",{r,g,b});
  wait(dut.px==792 && dut.py==240);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h234)$fatal(1,"knob solid face %h",{r,g,b});
  wait(dut.px==832 && dut.py==240);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"vertical knob pointer %h",{r,g,b});
  wait(dut.px==836 && dut.py==240);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"filled triangle interior %h",{r,g,b});
  wait(dut.px==840 && dut.py==240);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h234)$fatal(1,"triangle exterior %h",{r,g,b});
  wait(dut.px==724 && dut.py==288);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h89a)$fatal(1,"knob left scale tick %h",{r,g,b});
  wait(dut.px==940 && dut.py==288);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h89a)$fatal(1,"knob right scale tick %h",{r,g,b});
  wait(dut.px==872 && dut.py==336);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h234)$fatal(1,"knob uniform face %h",{r,g,b});
  wait(dut.px==760 && dut.py==360);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h89a)$fatal(1,"knob start scale tick %h",{r,g,b});
  wait(dut.px==904 && dut.py==360);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h89a)$fatal(1,"knob end scale tick %h",{r,g,b});
  wait(dut.px==889 && dut.py==370);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"tick outside knob sweep %h",{r,g,b});
  wait(dut.px==832 && dut.py==374);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h001)$fatal(1,"knob offset shadow %h",{r,g,b});
  wait(dut.px==832 && dut.py==396);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"knob bottom scale gap %h",{r,g,b});
  wait(dut.px==913 && dut.py==444);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'hcde)$fatal(1,"single-line loopback mV glyph %h",{r,g,b});
  wait(dut.px==997 && dut.py==445);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"duplicate full-size unit V %h",{r,g,b});
  for(i=0;i<1600;i=i+1)bus(96,(i<<10)|32);
  bus(136,32'h10040);bus(100,1);wait(dut.ui_ack==1);
  wait(dut.px==880 && dut.py==288);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"horizontal knob pointer %h",{r,g,b});
  for(i=0;i<1600;i=i+1)bus(96,(i<<10)|32);
  bus(108,0);bus(100,1);
  record(0,2);wait(dut.frames==3);
  // Independent known-ramp values: raw 1920 -> 322mV, 1936 -> 283mV.
  // At 140mV/div these endpoints are 1472 and 1293 in pixel Q4.
  wait(dut.px==32 && dut.py==200);#1;
  for(i=0;i<4;i=i+1)begin
   case(i)0:expected=1472;1:expected=1427;2:expected=1382;default:expected=1337;endcase
   if($signed(dut.wave_y_q4)!==(4544-expected))$fatal(1,"display phase %d expected Y %d got %d",i,4544-expected,$signed(dut.wave_y_q4));
   @(posedge pixel_clk);#1;
  end
  // The last pixel of the interpolated segment is only partly covered.
  wait(dut.px==33 && dut.py==195);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'hdb4)$fatal(1,"antialiased boundary %h",{r,g,b});
  wait(dut.px==33 && dut.py==196);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h001)$fatal(1,"trace leaked beyond interpolation boundary %h",{r,g,b});
  trigger=16383;record(2054,0);wait(dut.frames==4);
  wait(dut.x==671 && dut.y==10);#1;
  if(dut.start_index!=16223 || dut.address!=16383)$fatal(1,"right endpoint address wrap");
  trigger=0;record(2054,0);wait(dut.frames==5);
  wait(dut.x==671 && dut.y==10);#1;
  if(dut.start_index!=0 || dut.address!=160)$fatal(1,"left endpoint address wrap");
  for(i=0;i<1600;i=i+1)bus(96,(i<<10)|32);
  bus(36,32'hd1);bus(100,1);wait(dut.ui_ack==1);
  wait(dut.x==671 && dut.y==10);#1;
  if(dut.start_index!=0 || dut.address!=16358 || dut.spectrum_address!=511)$fatal(1,"expanded full-record/FFT mapping");
  if(dut.frames!=5)$fatal(1,"display rescale altered frozen record");
  bus(36,32'hd1|(120<<8)|(200<<17));bus(108,3);bus(100,1);wait(dut.ui_ack==0);
  wait(dut.px==160 && dut.py==200);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h9cf)$fatal(1,"first time cursor light blue %h",{r,g,b});
  wait(dut.px==416 && dut.py==200);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h9cf)$fatal(1,"second time cursor light blue %h",{r,g,b});
  wait(dut.px==100 && dut.py==264);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h9cf)$fatal(1,"first voltage cursor light blue %h",{r,g,b});
  wait(dut.px==160 && dut.py==264);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h9cf)$fatal(1,"cursor intersection light blue %h",{r,g,b});
  wait(dut.px==100 && dut.py==344);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h9cf)$fatal(1,"second voltage cursor light blue %h",{r,g,b});
  wait(dut.px==32 && dut.py==448);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"cursor time group border %h",{r,g,b});
  wait(dut.px==512 && dut.py==448);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"cursor group spacing %h",{r,g,b});
  wait(dut.px==520 && dut.py==448);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"cursor voltage group border %h",{r,g,b});
  wait(dut.px==991 && dut.py==535);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"cursor group bottom border %h",{r,g,b});
  bus(108,4);bus(100,1);wait(dut.ui_ack==1);
  wait(dut.px==32 && dut.py==448);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"spectrum group border %h",{r,g,b});
  wait(dut.px==112 && dut.py==496);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"H2 value box border %h",{r,g,b});
  wait(dut.px==120 && dut.py==500);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"harmonic value box interior %h",{r,g,b});
  wait(dut.px==352 && dut.py==500);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"H3 value box border %h",{r,g,b});
  wait(dut.px==592 && dut.py==500);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"H4 value box border %h",{r,g,b});
  wait(dut.px==832 && dut.py==500);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"H5 value box border %h",{r,g,b});
  $readmemh("page_5.mem",page);
  for(i=0;i<1600;i=i+1)bus(96,(i<<10)|page[i]);
  bus(108,5);bus(36,0);bus(100,1);wait(dut.ui_ack==0);
  wait(dut.px==64 && dut.py==208);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h456)$fatal(1,"selftest start border %h",{r,g,b});
  wait(dut.px==96 && dut.py==220);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h123)$fatal(1,"selftest start interior %h",{r,g,b});
  wait(dut.px==96 && dut.py==280);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h123)$fatal(1,"selftest pending neutral %h",{r,g,b});
  wait(dut.px==338 && dut.py==371);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'hcde)$fatal(1,"selftest placeholder dash %h",{r,g,b});
  wait(dut.px==343 && dut.py==371);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h112)$fatal(1,"selftest placeholder centered gap %h",{r,g,b});
  bus(36,(1<<27)|(1<<26));bus(100,1);wait(dut.ui_ack==1);
  wait(dut.px==64 && dut.py==208);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h9bc)$fatal(1,"selftest selected border %h",{r,g,b});
  wait(dut.px==96 && dut.py==220);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h245)$fatal(1,"selftest selected interior %h",{r,g,b});
  wait(dut.px==96 && dut.py==280);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h173)$fatal(1,"selftest passed green %h",{r,g,b});
  bus(36,2<<27);bus(100,1);wait(dut.ui_ack==0);
  wait(dut.px==96 && dut.py==280);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h811)$fatal(1,"selftest failed red %h",{r,g,b});
  bus(36,3<<27);bus(100,1);wait(dut.ui_ack==1);
  wait(dut.px==96 && dut.py==280);repeat(3)@(negedge pixel_clk);
  if({r,g,b}!==12'h234)$fatal(1,"selftest running neutral %h",{r,g,b});
  if(!interpolation_done)$fatal(1,"interpolation unit tests incomplete");
  $display("PANEL_RTL_TEST_PASS");$finish;
 end
 initial begin #300000000;$fatal(1,"watchdog");end
endmodule
