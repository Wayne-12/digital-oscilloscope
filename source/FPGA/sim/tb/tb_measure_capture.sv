`default_nettype none
module tb_measure_capture;
  timeunit 1ns;timeprecision 1ps;
  logic run=0;wire done;
  measure_capture_scenario scenario(.run(run),.done(done));
  initial begin #1ns;run=1;wait(done);$display("TEST_PASS tb_measure_capture errors=0");$finish;end
  initial begin #100ms;$fatal(1,"MEASURE_CAPTURE_WATCHDOG");end
endmodule
`default_nettype wire
