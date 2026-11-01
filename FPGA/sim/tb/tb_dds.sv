`default_nettype none
module tb_dds;
  timeunit 1ns; timeprecision 1ps;
  wire [4:0] done;
  dds_scenario #(.RATE_HZ(10_000_000)) r10(.done(done[0]));
  dds_scenario #(.RATE_HZ(25_000_000)) r25(.done(done[1]));
  dds_scenario #(.RATE_HZ(50_000_000)) r50(.done(done[2]));
  dds_scenario #(.RATE_HZ(65_000_000)) r65(.done(done[3]));
  dds_safe_scenario safety(.done(done[4]));
  initial begin
    wait(&done);$display("TEST_PASS tb_dds rates=4 cases_per_rate=18 safety=1 errors=0");$finish;
  end
  initial begin #40ms; $fatal(1,"TEST_FAIL DDS watchdog");end
endmodule
`default_nettype wire
