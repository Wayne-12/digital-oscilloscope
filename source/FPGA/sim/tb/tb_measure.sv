`default_nettype none
module tb_measure;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  logic clk=1'b0;
  always #5ns clk=~clk;
  logic mrst,mstart,mvalid;
  logic [17:0] length;
  logic [31:0] rate;
  adc_sample_t mx,threshold;
  logic [12:0] hyst;
  sample_timestamp_t mt;
  wire logic ready,busy,done,valid,error_flag;
  measurement_result_t result;
  measurement_core measure_dut(.clk(clk),.rst(mrst),.start(mstart),.frame_length(length),
    .sample_rate_hz(rate),.threshold(threshold),.hysteresis(hyst),.sample_valid(mvalid),
    .sample_signed(mx),.sample_timestamp(mt),.sample_ready(ready),.busy(busy),
    .measurement_done(done),.measurement_valid(valid),.measurement_error(error_flag),.result(result));
  string vd,ed,td;
  integer stage,seed,checks;
  always @(posedge clk)begin
    if(!mrst)begin
      assert(!done || (!busy && !ready))else $fatal(1,"TEST_FAIL done/busy protocol");
      assert(!ready || (busy && !result.stats_valid))else $fatal(1,"TEST_FAIL ready/result protocol");
      if(measure_dut.state==measure_dut.DIV_START)
        assert(!measure_dut.divider_busy && measure_dut.denominator!=64'd0)
          else $fatal(1,"TEST_FAIL divider request protocol");
    end
  end
  task automatic compare_measure(input integer cid,input integer n,input integer emin,emax,emean,ep2p,erms,
      input logic signed [63:0] esum,input logic [63:0] ess,input integer ep,
      input logic [63:0] eperiod,input integer efreq,eduty,eerr,ev);
    assert(result.stats_valid && result.sample_count===18'(n) &&
      result.minimum===13'(emin) && result.maximum===13'(emax) && result.mean===13'(emean) &&
      result.peak_to_peak===14'(ep2p) && result.rms===14'(erms) && result.sum===esum && result.square_sum===ess &&
      result.period_count===18'(ep) && result.period_q16===eperiod && result.frequency_hz===32'(efreq) &&
      result.duty_ppm===32'(eduty) && error_flag===1'(eerr) && valid===1'(ev) &&
      result.period_valid===1'(ev) && result.duty_valid===1'(ev))else
      $fatal(1,"TEST_FAIL measurement case=%0d got min=%0d max=%0d mean=%0d rms=%0d sum=%0d ss=%0d periods=%0d period=%0d freq=%0d duty=%0d err=%b valid=%b expected n=%0d min=%0d max=%0d mean=%0d rms=%0d sum=%0d ss=%0d periods=%0d period=%0d freq=%0d duty=%0d err=%0d valid=%0d",
        cid,result.minimum,result.maximum,result.mean,result.rms,result.sum,result.square_sum,result.period_count,result.period_q16,result.frequency_hz,result.duty_ppm,error_flag,valid,n,emin,emax,emean,erms,esum,ess,ep,eperiod,efreq,eduty,eerr,ev);
    assert(valid || (result.frequency_hz==32'd0 && result.period_q16==64'd0 && result.duty_ppm==32'd0))
      else $fatal(1,"TEST_FAIL invalid frequency not zero");
    checks++;
  endtask
  task automatic measurements(input integer s);
    integer f,e,csv,cases,cid,n,rate_i,th,h,bubbles,rc,x,ecid,en,emin,emax,emean,ep2p,erms,ep,efreq,eduty,eerr,ev,waits;
    logic signed [63:0] esum;
    logic [63:0] ts,ess,eperiod;
    measurement_result_t held;
    string name;
    f=$fopen($sformatf("%s/measure_stage%0d.txt",vd,s),"r");
    e=$fopen($sformatf("%s/measure_stage%0d.txt",ed,s),"r");
    csv=$fopen($sformatf("%s/measure_stage%0d.csv",td,s),"w");
    assert(f && e && csv)else $fatal(1,"TEST_FAIL measurement files");
    $fdisplay(csv,"case_id,count,minimum,maximum,mean,peak_to_peak,rms,sum,square_sum,period_count,period_q16,frequency_hz,duty_ppm,error,valid");
    rc=$fscanf(f,"%d",cases);assert(rc==1)else $fatal(1,"TEST_FAIL measure count");
    for(integer c=0;c<cases;c++)begin
      rc=$fscanf(f,"%d %s %d %d %d %d %d",cid,name,n,rate_i,th,h,bubbles);
      assert(rc==7)else $fatal(1,"TEST_FAIL measure header");
      rc=$fscanf(e,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d",ecid,en,emin,emax,emean,ep2p,erms,esum,ess,ep,eperiod,efreq,eduty,eerr,ev);
      assert(rc==15 && ecid==cid && en==n)else $fatal(1,"TEST_FAIL measure oracle");
      @(negedge clk);mrst=0;mstart=1;length=18'(n);rate=32'(rate_i);threshold=13'(th);hyst=13'(h);mvalid=0;
      @(posedge clk);#1ps;assert(ready && busy)else $fatal(1,"TEST_FAIL measure not ready");
      @(negedge clk);mstart=0;length=0;rate=0;threshold=13'sd4095;hyst=13'd8191; // Must use latched config.
      for(integer i=0;i<n;i++)begin
        rc=$fscanf(f,"%d %d",x,ts);assert(rc==2)else $fatal(1,"TEST_FAIL measure row");
        if(bubbles && i%17==3)begin
          mvalid=0;@(posedge clk);#1ps;assert(ready && !done)else $fatal(1,"TEST_FAIL bubble");@(negedge clk);
        end
        mvalid=1;mx=13'(x);mt=ts;mstart=i==1; // Busy start pulses must be ignored.
        @(posedge clk);#1ps;
        assert(measure_dut.square_sum<=64'(n)*64'd16777216 && measure_dut.sum_reg>=-64'(n)*64'sd4096 &&
          measure_dut.sum_reg<=64'(n)*64'sd4095)else $fatal(1,"TEST_FAIL accumulator bound");
        @(negedge clk);
      end
      mvalid=0;mstart=0;waits=0;
      while(!done && waits<400)begin @(posedge clk);#1ps;waits++;end
      assert(done && !busy && waits<=350)else $fatal(1,"TEST_FAIL measure finalization timeout");
      compare_measure(cid,n,emin,emax,emean,ep2p,erms,esum,ess,ep,eperiod,efreq,eduty,eerr,ev);
      $fdisplay(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
        cid,result.sample_count,result.minimum,result.maximum,result.mean,result.peak_to_peak,result.rms,result.sum,result.square_sum,
        result.period_count,result.period_q16,result.frequency_hz,result.duty_ppm,error_flag,valid);
      held=result;
      repeat(3)begin @(posedge clk);#1ps;assert(result===held && !done)else $fatal(1,"TEST_FAIL result not held");end
    end
    $fclose(f);$fclose(e);$fclose(csv);
    $display("FEATURE_PASS stage=%0d measurement_cases=%0d errors=0",s,cases);
  endtask
  task automatic reset_phase(input integer target,op);
    integer guard;
    @(negedge clk);mrst=0;mstart=1;length=18'd4;rate=32'd25000000;threshold=0;hyst=8;mvalid=0;
    @(negedge clk);mstart=0;
    if(target!=1)begin
      for(integer i=0;i<4;i++)begin
        mvalid=1;mx=i%2==0?-13'sd100:13'sd100;mt=64'(i);
        @(negedge clk);
      end
      mvalid=0;
    end
    guard=0;
    while((integer'(measure_dut.state)!=target || (op>=0 && integer'(measure_dut.operation)!=op)) && guard<400)begin
      @(negedge clk);guard++;
    end
    assert(guard<400)else $fatal(1,"TEST_FAIL reset target not reached state=%0d operation=%0d",target,op);
    mrst=1;@(posedge clk);#1ps;
    assert(!busy && !done && !valid && !error_flag && result=='0 && !measure_dut.divider_busy)
      else $fatal(1,"TEST_FAIL reset abort state=%0d operation=%0d",target,op);
    @(negedge clk);mrst=0;
    repeat(80)begin @(posedge clk);#1ps;
      assert(!busy && !done && !valid && result=='0)else $fatal(1,"TEST_FAIL stale divider completion");
    end
    $display("MEASURE_RESET_PASS state=%0d operation=%0d errors=0",target,op);
  endtask
  task automatic protocol_checks;
    for(integer i=0;i<3;i++)begin
      @(negedge clk);mstart=1;length=i==0?18'd0:(i==1?18'd16385:18'd4);rate=i==2?32'd0:32'd25000000;
      @(posedge clk);#1ps;
      assert(done && error_flag && !busy && !valid && result=='0)else $fatal(1,"TEST_FAIL invalid config");
      @(negedge clk);mstart=0;
      @(posedge clk);#1ps;
    end
    reset_phase(1,-1); // ACQUIRE
    for(integer op=0;op<5;op++)begin reset_phase(2,op);reset_phase(3,op);end
    reset_phase(4,-1); // SQRT
    reset_phase(5,-1); // FINISH, before publishing any valid result.
    $display("MEASURE_PROTOCOL_PASS invalid_configs=3 reset_aborts=13 errors=0");
  endtask
  initial begin
    mrst=1;mstart=0;mvalid=0;
    length=0;rate=0;mx=0;mt=0;threshold=0;hyst=0;checks=0;stage=0;seed=20261020;
    assert($value$plusargs("VECTOR_DIR=%s",vd) && $value$plusargs("EXPECTED_DIR=%s",ed) && $value$plusargs("TRACE_DIR=%s",td))else $fatal(1,"TEST_FAIL directories");
    if($value$plusargs("STAGE=%d",stage))begin end
    if($value$plusargs("SEED=%d",seed))begin end
    repeat(3)@(posedge clk);
    for(integer s=5;s<=7;s++)if(stage==0 || stage==s)begin
      measurements(s);
    end
    if(stage==0 || stage==7)begin
      protocol_checks();
    end
    $display("TEST_PASS tb_measure stage=%0d seed=%0d checks=%0d errors=0",stage,seed,checks);$finish;
  end
  initial begin #100ms;$fatal(1,"TEST_FAIL tb_measure watchdog");end
endmodule
`default_nettype wire
