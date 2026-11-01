`default_nettype none
module trigger_scenario(input wire logic clk,output logic done);
  timeunit 1ns;timeprecision 1ps;
  logic rst,valid,rising;
  scope_pkg::adc_sample_t sample_value,threshold;
  logic [12:0] hysteresis;
  wire hit,qualified;
  trigger_edge dut(.clk(clk),.rst(rst),.enable(1'b1),.sample_valid(valid),.rising(rising),
    .sample_signed(sample_value),.threshold(threshold),.hysteresis(hysteresis),.trigger_hit(hit),.qualified(qualified));
  string vd,td;integer fd,tf,rv,total,clear_i,valid_i,dir_i,x,th,h,expected,hits;
  initial begin
    done=0;rst=1;valid=0;rising=1;sample_value=0;threshold=0;hysteresis=0;hits=0;
    if(!$value$plusargs("VECTOR_DIR=%s",vd))$fatal(1,"TEST_FAIL trigger vector path");
    if(!$value$plusargs("TRACE_DIR=%s",td))td=".";
    fd=$fopen({vd,"/trigger_unit.txt"},"r");tf=$fopen({td,"/capture_trigger.csv"},"w");
    assert(fd&&tf)else $fatal(1,"TEST_FAIL trigger files");
    rv=$fscanf(fd,"%d",total);assert(rv==1 && total==28672)else $fatal(1,"TEST_FAIL trigger count");
    $fwrite(tf,"cycle,reset,valid,rising,sample,threshold,hysteresis,hit\n");
    repeat(2)@(posedge clk);
    for(integer i=0;i<total;i++)begin
      rv=$fscanf(fd,"%d %d %d %d %d %d %d",clear_i,valid_i,dir_i,x,th,h,expected);
      assert(rv==7)else $fatal(1,"TEST_FAIL trigger truncated vector");
      @(negedge clk);rst=1'(clear_i);valid=1'(valid_i);rising=1'(dir_i);
      sample_value=13'(x);threshold=13'(th);hysteresis=13'(h);
      #2ps;assert(hit===1'(expected))else $fatal(1,"TEST_FAIL hysteresis cycle=%0d value=%0d got=%b expected=%0d",i,x,hit,expected);
      $fwrite(tf,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",i,clear_i,valid_i,dir_i,x,th,h,hit);
      hits+=expected;@(posedge clk);#2ps;
    end
    assert(hits>20)else $fatal(1,"TEST_FAIL trigger vacuous coverage");
    $fclose(fd);$fclose(tf);$display("TRIGGER_UNIT_PASS checks=%0d hits=%0d errors=0",total,hits);done=1;
  end
endmodule
`default_nettype wire
