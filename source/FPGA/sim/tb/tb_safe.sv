`default_nettype none
module tb_safe;
  timeunit 1ns;
  timeprecision 1ps;
  wire [3:0] done;
  wire clk100;
  logic reset100, reset_test_done;
  wire synchronized100;
  ideal_clock clock100 (.frequency_hz(32'd100000000), .clk(clk100));
  scope_reset_sync reset100_dut (.clk(clk100), .arst(reset100), .rst(synchronized100));
  safe_scenario #(.START_RATE_HZ(10000000)) test10 (.done(done[0]));
  safe_scenario #(.START_RATE_HZ(25000000)) test25 (.done(done[1]));
  safe_scenario #(.START_RATE_HZ(50000000)) test50 (.done(done[2]));
  safe_scenario #(.START_RATE_HZ(65000000)) test65 (.done(done[3]));

  initial begin
    reset_test_done = 1'b0;
    reset100 = 1'b1;
    repeat (3) @(posedge clk100);
    @(negedge clk100);
    reset100 = 1'b0;
    @(posedge clk100);
    #2ps;
    assert (synchronized100 === 1'b1) else $fatal(1, "TEST_FAIL 100 MHz reset released early");
    @(posedge clk100);
    #2ps;
    assert (synchronized100 === 1'b0) else $fatal(1, "TEST_FAIL 100 MHz reset released late");
    #1ns;
    reset100 = 1'b1;
    #2ps;
    assert (synchronized100 === 1'b1) else $fatal(1, "TEST_FAIL asynchronous reset assertion");
    reset_test_done = 1'b1;
    $display("TEST_CASE_PASS reset_100MHz_async_assert_sync_release");
  end
  initial begin
    wait ((done === 4'b1111) && reset_test_done);
    #10ns;
    $display("TEST_PASS tb_safe rates=10,25,50,65MHz states=10/10_each assertions_failed=0");
    $finish;
  end
  initial begin
    #5ms;
    $fatal(1, "TEST_FAIL tb_safe watchdog/deadlock timeout done=%b", done);
  end
endmodule : tb_safe
`default_nettype wire
