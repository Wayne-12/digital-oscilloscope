`default_nettype none
module tb_loopback;
  timeunit 1ns;timeprecision 1ps;
  wire clk;
  wire [25:0] done;
  ideal_clock source_clock(.frequency_hz(32'd25000000),.clk(clk));
  for(genvar p=0;p<13;p++)begin:profiles
    loopback_scenario #(.PROFILE(p),.T_CO_NS(3.5)) early(.clk(clk),.done(done[p*2]));
    loopback_scenario #(.PROFILE(p),.T_CO_NS(7.0)) late(.clk(clk),.done(done[p*2+1]));
  end
  initial begin wait(&done);$display("TEST_PASS tb_loopback profiles=13 delay_endpoints=2 errors=0");$finish;end
  initial begin #30ms;$fatal(1,"TEST_FAIL loopback watchdog");end
endmodule
`default_nettype wire
