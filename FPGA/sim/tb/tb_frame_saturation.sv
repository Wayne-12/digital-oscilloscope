`default_nettype none
module tb_frame_saturation;
  timeunit 1ns;timeprecision 1ps;
  logic clk=0,clear=1,accept=0;always #5ns clk=~clk;
  logic [11:0] raw_code=2047;
  wire [14:0] samples,saturated_samples,events;
  frame_saturation_counter dut(.*);
  int wanted_samples,wanted_events;bit previous,current;
  initial begin
    for(int pattern=0;pattern<7;pattern++)begin
      @(negedge clk);clear=1;accept=0;@(negedge clk);clear=0;
      wanted_samples=0;wanted_events=0;previous=0;
      for(int i=0;i<16384;i++)begin
        case(pattern)
          0:raw_code=2047;
          1:raw_code=0;
          2:raw_code=4095;
          3:raw_code=i[0]?12'd0:12'd1;
          4:raw_code=(i==0 || i==16383)?12'd4095:12'd4094;
          5:raw_code=(i>=7000 && i<11000)?12'd0:12'd2047;
          6:raw_code=(i%17<5)?12'd4095:12'd1;
        endcase
        current=(raw_code==0 || raw_code==4095);
        if(current)wanted_samples++;
        if(current && !previous)wanted_events++;
        previous=current;accept=1;@(negedge clk);
        if(i%37==0)begin accept=0;repeat(3)@(negedge clk);end
      end
      accept=1;raw_code=0;repeat(5)@(negedge clk);accept=0;
      assert(samples==16384 && saturated_samples==wanted_samples && events==wanted_events)
        else $fatal(1,"SATURATION_DIFFER pattern=%0d samples=%0d saturated=%0d/%0d events=%0d/%0d",
          pattern,samples,saturated_samples,wanted_samples,events,wanted_events);
    end
    $display("TEST_PASS tb_frame_saturation patterns=7 full_records=7 boundary_stalls_reset_overrun=PASS");$finish;
  end
  initial begin #5ms;$fatal(1,"SATURATION_WATCHDOG");end
endmodule
`default_nettype wire
