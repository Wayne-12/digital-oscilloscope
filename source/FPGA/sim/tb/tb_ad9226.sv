`default_nettype none
module tb_ad9226;
  timeunit 1ns;
  timeprecision 1ps;
  wire [17:0] done;
  for (genvar rate = 0; rate < 4; rate++) begin : g_rate
    localparam int unsigned RATE = (rate == 0) ? 10000000 : ((rate == 1) ? 25000000 : ((rate == 2) ? 50000000 : 65000000));
    for (genvar delay_index = 0; delay_index < 2; delay_index++) begin : g_delay
      ad9226_scenario #(.RATE_HZ(RATE),.T_CO_NS((delay_index == 0) ? 3.5 : 7.0))
        scenario (.done(done[rate*2+delay_index]));
    end
  end
  for (genvar profile = 1; profile <= 4; profile++) begin : g_profile
    for (genvar delay_index = 0; delay_index < 2; delay_index++) begin : g_delay
      ad9226_scenario #(.PROFILE(profile),.T_CO_NS((delay_index == 0) ? 3.5 : 7.0))
        scenario (.done(done[8+(profile-1)*2+delay_index]));
    end
  end
  ad9226_scenario #(.T_CO_NS(3.5),.FORWARD_NS(0.1)) forward_min (.done(done[16]));
  ad9226_scenario #(.T_CO_NS(7.0),.FORWARD_NS(0.1)) forward_max (.done(done[17]));
  initial begin
    wait (&done);
    #10ns;
    $display("TEST_PASS tb_ad9226 cases=18 latency=7+1 random_per_case_at_least=10000 errors=0");
    $finish;
  end
  initial begin
    #20ms;
    $fatal(1,"TEST_FAIL tb_ad9226 watchdog done=%h",done);
  end
endmodule : tb_ad9226
`default_nettype wire
