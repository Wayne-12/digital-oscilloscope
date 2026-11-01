`timescale 1ns/1ps
module tb_cdc_safety;
 import scope_pkg::*;
 reg clk=0,clock_running=1; always #20 if(clock_running)clk=~clk;
 reg arst=1,locked=0,enable=0;
 wire data_oe,dac_oe,adc_oe,capture,rst,qualified;
 wire [13:0] data; safe_state_t state;
 wire dac_forward,adc_forward,dac_pin,adc_pin;
 ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.SRTYPE("ASYNC"),.INIT(1'b0)) ddr_dac(
 .C(clk),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(!dac_oe),.S(1'b0),.Q(dac_forward));
 ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.SRTYPE("ASYNC"),.INIT(1'b0)) ddr_adc(
 .C(clk),.CE(1'b1),.D1(1'b1),.D2(1'b0),.R(!adc_oe),.S(1'b0),.Q(adc_forward));
 OBUFT dac_buffer(.I(dac_forward),.T(!dac_oe),.O(dac_pin));
 OBUFT adc_buffer(.I(adc_forward),.T(!adc_oe),.O(adc_pin));
 scope_core dut(.clk_sample(clk),.arst(arst),.clock_locked(locked),.module_enable(enable),
 .clock_restart(1'b0),.dac_data_oe(data_oe),.dac_clk_oe(dac_oe),.adc_clk_oe(adc_oe),
 .capture_enable(capture),.dac_data(data),.state(state),.core_rst(rst),.enable_qualified(qualified));
 realtime last_pos,last_neg;
 integer dac_edges=0,adc_edges=0,tests=0;
 always @(posedge clk) begin
  last_pos=$realtime;
  if(dac_oe)dac_edges=dac_edges+1;
  if(adc_oe)adc_edges=adc_edges+1;
 end
 always @(negedge clk) last_neg=$realtime;
 always @(negedge dac_oe) dac_edges=0;
 always @(negedge adc_oe) adc_edges=0;
 always @(posedge adc_oe) if($realtime>200 && dac_edges<16) $fatal(1,"ADC started before 16 DAC clocks");
 always @(posedge capture) begin
  if(adc_edges<256 || !adc_oe || !dac_oe || !data_oe) $fatal(1,"capture before warmup");
 end
 always @(capture) if($realtime>200 && $realtime!=last_pos && $realtime!=last_neg)
  $fatal(1,"ASYNC_INTERNAL_CAPTURE_ENABLE time=%t last_pos=%t",$realtime,last_pos);
 always @(negedge adc_oe) if($realtime>200 && !rst && capture) $fatal(1,"ADC stopped while capture enabled");
 task wait_run;
  integer n;
  begin
   n=0;
   while(capture!==1'b1 && n<400) begin @(posedge clk);#1;n=n+1;end
   if(capture!==1'b1)$fatal(1,"restart timeout");
   repeat(4)@(negedge clk);
  end
 endtask
 task short_withdraw(input integer phase_ns);
  integer n;
  begin
   @(posedge clk); #(phase_ns);enable=0;
   // A sub-cycle pulse must be captured by the safety qualifier.
   #3;enable=1;n=0;
   while(capture!==1'b0 && n<8)begin @(posedge clk);#1;n=n+1;end
   if(capture!==1'b0)$fatal(1,"short OFF pulse missed at phase=%0d",phase_ns);
   wait_run();tests=tests+1;
  end
 endtask
 integer phase;
 initial begin
  #97;locked=1;arst=0;#131;enable=1;wait_run();
  for(phase=1;phase<40;phase=phase+2)short_withdraw(phase);
  // Long OFF: capture, ADC clock, DAC clock, then data all stop.
  @(posedge clk);#9;enable=0;repeat(12)@(negedge clk);
  if(capture || adc_oe || dac_oe || data_oe)$fatal(1,"OFF did not reach high impedance");
  #13;enable=1;wait_run();tests=tests+1;
  // Clock loss: outputs must isolate even when the clock no longer advances.
  @(negedge clk);#7;clock_running=0;locked=0;#1;
  if(data_oe || dac_oe || adc_oe)$fatal(1,"lock loss did not isolate pins asynchronously");
  if(dac_pin!==1'bz || adc_pin!==1'bz)$fatal(1,"output buffers not isolated without clock");
  #400;clock_running=1;
  repeat(4)@(negedge clk);#11;locked=1;wait_run();tests=tests+1;
  @(posedge clk);#3;arst=1;#1;
  if(data_oe || dac_oe || adc_oe)$fatal(1,"reset did not isolate pins asynchronously");
  #6;arst=0;wait_run();tests=tests+1;
  $display("CDC_SAFETY_TEST_PASS cases=%0d, all sub-cycle OFF phases, ordered stop, reset, lock loss, full rewarmup",tests);
  $finish;
 end
 initial begin #1000000;$fatal(1,"watchdog");end
endmodule
