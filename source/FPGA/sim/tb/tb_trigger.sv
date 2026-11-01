`default_nettype none
module tb_trigger;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic trst,ten,tvalid,totr;
  trigger_config_t tc;
  adc_sample_t tx;
  sample_timestamp_t tt;
  wire logic hit,ce,te;
  trigger_core trigger_dut(.clk(clk),.rst(trst),.enable(ten),.sample_valid(tvalid),
    .config_in(tc),.sample_signed(tx),.sample_otr(totr),.sample_timestamp(tt),
    .trigger_hit(hit),.config_error(ce),.timestamp_error(te));
  string vd,td; integer stage=0,seed=20261020,checks=0;
  task automatic triggers(input integer s);
    integer f,csv,cases,cid,n,k,th,h,wl,wh,wmin,wmax,amp,obs,bad;
    integer x,v,en,r,ot,eh,ee,rc,ehit_total;
    logic observed_hit;
    logic [63:0] ts;
    string name;
    f=$fopen($sformatf("%s/trigger_stage%0d.txt",vd,s),"r");
    csv=$fopen($sformatf("%s/trigger_stage%0d.csv",td,s),"w");
    assert(f && csv)else $fatal(1,"TEST_FAIL trigger files");
    $fdisplay(csv,"case_id,index,value,timestamp,valid,enable,reset,otr,hit,timestamp_error,config_error");
    rc=$fscanf(f,"%d",cases);assert(rc==1)else $fatal(1,"TEST_FAIL trigger count");
    ehit_total=0;
    for(integer c=0;c<cases;c++)begin
      rc=$fscanf(f,"%d %s %d %d %d %d %d %d %d %d %d %d %d",cid,name,n,k,th,h,wl,wh,wmin,wmax,amp,obs,bad);
      assert(rc==13)else $fatal(1,"TEST_FAIL trigger header stage=%0d case=%0d rc=%0d",s,c,rc);
      @(negedge clk);trst=1;ten=0;tvalid=0;
      tc.kind=trigger_type_t'(4'(k));tc.threshold=13'(th);tc.hysteresis=13'(h);
      tc.window_low=13'(wl);tc.window_high=13'(wh);tc.width_min=32'(wmin);tc.width_max=32'(wmax);
      tc.amplitude_limit=14'(amp);tc.observation_samples=15'(obs);
      @(posedge clk);#1ps;
      for(integer i=0;i<n;i++)begin
        rc=$fscanf(f,"%d %d %d %d %d %d %d %d",x,ts,v,en,r,ot,eh,ee);
        assert(rc==8)else $fatal(1,"TEST_FAIL trigger row");
        @(negedge clk);tx=13'(x);tt=ts;tvalid=1'(v);ten=1'(en);trst=1'(r);totr=1'(ot);
        #1ps;
        assert(hit===1'(eh) && ce===1'(bad))else
          $fatal(1,"TEST_FAIL trigger stage=%0d case=%0d %s i=%0d x=%0d hit=%b expected=%0d config_error=%b",s,cid,name,i,x,hit,eh,ce);
        assert(!hit || (ten && tvalid && !trst && !ce))else $fatal(1,"TEST_FAIL trigger qualifier");
        observed_hit=hit;
        @(posedge clk);#1ps;
        assert(te===1'(ee))else $fatal(1,"TEST_FAIL trigger timestamp stage=%0d case=%0d i=%0d",s,cid,i);
        $fdisplay(csv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cid,i,x,ts,v,en,r,ot,observed_hit,te,ce);
        ehit_total+=eh;checks++;
      end
    end
    @(negedge clk);ten=0;tvalid=0;trst=1;
    $fclose(f);$fclose(csv);
    $display("FEATURE_PASS stage=%0d trigger_cases=%0d hits=%0d errors=0",s,cases,ehit_total);
  endtask
  initial begin
    trst=1;ten=0;tvalid=0;totr=0;tc='0;tx=0;tt=0;
    assert($value$plusargs("VECTOR_DIR=%s",vd) && $value$plusargs("TRACE_DIR=%s",td))else $fatal(1,"TRIGGER_PATHS");
    if($value$plusargs("STAGE=%d",stage))begin end
    if($value$plusargs("SEED=%d",seed))begin end
    assert(stage>=0 && stage<=4)else $fatal(1,"TRIGGER_STAGE");
    for(integer s=1;s<=4;s++)if(stage==0 || stage==s)triggers(s);
    $display("TEST_PASS tb_trigger stage=%0d seed=%0d checks=%0d errors=0",stage,seed,checks);$finish;
  end
  initial begin #100ms;$fatal(1,"TRIGGER_WATCHDOG");end
endmodule
`default_nettype wire
