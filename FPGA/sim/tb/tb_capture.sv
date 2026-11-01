`default_nettype none
module tb_capture;
  timeunit 1ns;timeprecision 1ps;
  wire [5:0] done;
  wire unit_clk;
  ideal_clock unit_clock(.frequency_hz(32'd100000000),.clk(unit_clk));
  trigger_scenario schmitt(.clk(unit_clk),.done(done[5]));
  capture_scenario #(.SID(0),.ADC_RATE(25000000)) main_test(.done(done[0]));
  capture_scenario #(.SID(1),.ADC_RATE(10000000)) r10(.done(done[1]));
  capture_scenario #(.SID(2),.ADC_RATE(50000000)) r50(.done(done[2]));
  capture_scenario #(.SID(3),.ADC_RATE(65000000)) r65(.done(done[3]));
  capture_scenario #(.SID(4),.ADC_RATE(65000000),.SYS_RATE(7000000)) slow_reader(.done(done[4]));
  initial begin wait(&done);$display("TEST_PASS tb_capture scenarios=5 errors=0");$finish;end
  initial begin #200ms;$fatal(1,"TEST_FAIL capture watchdog");end
endmodule
`default_nettype wire
