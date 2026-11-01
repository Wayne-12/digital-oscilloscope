`default_nettype none
module tb_spectrum_isqrt;
  timeunit 1ns;timeprecision 1ps;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,start=0;logic [63:0] radicand=0;
  wire busy,done;wire [32:0] rounded_root;
  spectrum_isqrt dut(.*);
  string vectors;integer f,rc,idx,count=0,cycles;
  logic [63:0] x;logic [32:0] expected;
  initial begin #1ms;$fatal(1,"ISQRT_WATCHDOG");end
  initial begin
    if(!$value$plusargs("VECTOR_DIR=%s",vectors))$fatal(1,"ISQRT_PATH");
    f=$fopen({vectors,"/isqrt.txt"},"r");if(!f)$fatal(1,"ISQRT_OPEN");
    repeat(6)@(negedge clk);rst=0;
    while(!$feof(f))begin
      rc=$fscanf(f,"%d %h %h\n",idx,x,expected);assert(rc==3&&idx==count)else $fatal(1,"ISQRT_FORMAT");
      radicand=x;start=1;@(negedge clk);start=0;cycles=0;
      while(!done)begin @(negedge clk);cycles++;assert(cycles<=32)else $fatal(1,"ISQRT_LATENCY");end
      assert(cycles==32&&rounded_root==expected&&!busy)else $fatal(1,"ISQRT_SCOREBOARD x=%h got=%h expected=%h cycles=%0d",x,rounded_root,expected,cycles);count++;
      @(negedge clk);
    end
    $fclose(f);$display("TEST_PASS tb_spectrum_isqrt cases=%0d errors=0",count);$finish;
  end
endmodule
`default_nettype wire
