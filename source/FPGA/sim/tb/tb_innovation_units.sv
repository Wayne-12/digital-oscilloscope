`default_nettype none
module tb_innovation_units;
  timeunit 1ns;timeprecision 1ps;
  import innovation_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,en=1,start=0,pv=0;logic [5:0] n;logic [31:0] nom;
  logic signed [13:0] px;logic signed [31:0] py;
  wire ready,pr,fd,fv,fe;wire signed [31:0] gain,offset,corr;
  relative_calibrator fit_dut(.clk(clk),.rst(rst),.module_enable(en),.start(start),.cfg_points(n),.cfg_nominal_gain_q20(nom),.start_ready(ready),.point_ready(pr),
    .point_valid(pv),.point_x(px),.point_mean_q16(py),.done(fd),.fit_valid(fv),.fit_error(fe),.gain_q20(gain),.offset_q16(offset),.correction_q20(corr));
  logic av=0,ar=0,cv;wire ai,ao;logic [15:0] word;logic [63:0] ts;logic signed [31:0] off,cor;wire [15:0] ow;wire [63:0] ot;wire signed [31:0] display_value;wire corrected,sat;
  calibration_apply apply_dut(.clk(clk),.rst(rst),.module_enable(en),.in_valid(av),.in_ready(ai),.in_raw_word(word),.in_timestamp(ts),.calibration_valid(cv),.correction_q20(cor),.offset_q16(off),
    .out_valid(ao),.out_ready(ar),.out_raw_word(ow),.out_timestamp(ot),.display_q16(display_value),.corrected(corrected),.saturated(sat));
  logic hv=0,hr=0;wire hi,ho;health_fingerprint_t base,current;health_limits_t limits;wire [6:0] alarms;health_class_t kind;
  health_compare health_dut(.clk(clk),.rst(rst),.module_enable(en),.in_valid(hv),.in_ready(hi),.baseline(base),.current(current),.limits(limits),.out_valid(ho),.out_ready(hr),.alarms(alarms),.classification(kind));
  string vectors;integer f,p,rc,cid,cnt,nomi,validi,g,b,c,x,y,expected,sati,mask,ki,fit_count=0,apply_count=0,health_count=0;
  initial begin #10ms;$fatal(1,"INNOVATION_UNIT_WATCHDOG");end
  initial begin
    n=0;nom=0;px=0;py=0;word=0;ts=0;cv=0;off=0;cor=0;base='0;current='0;limits='0;
    limits.zero_limit_q16=262144;limits.gain_limit_q20=10486;limits.noise_rise_limit_q16=262144;limits.compression_limit_ppm=50000;limits.harmonic_limit_ppm=100;
    if(!$value$plusargs("VECTOR_DIR=%s",vectors))$fatal(1,"UNIT_PATH");repeat(6)@(negedge clk);rst=0;
    f=$fopen({vectors,"/fit_cases.txt"},"r");assert(f)else $fatal(1,"UNIT_FIT_OPEN");
    while(!$feof(f))begin
      rc=$fscanf(f,"%d %d %d %d %d %d %d\n",cid,cnt,nomi,validi,g,b,c);assert(rc==7&&cid==fit_count)else $fatal(1,"UNIT_FIT_HEADER");
      wait(ready);n=6'(cnt);nom=32'(nomi);start=1;@(negedge clk);start=0;
      if(cnt>=2&&cnt<=32&&nomi!=0)begin
        p=$fopen($sformatf("%s/fit_%0d.txt",vectors,cid),"r");assert(p)else $fatal(1,"UNIT_FIT_POINTS");
        for(integer j=0;j<cnt;j++)begin rc=$fscanf(p,"%d %d\n",x,y);assert(rc==2)else $fatal(1,"UNIT_FIT_FORMAT");wait(pr);px=14'(x);py=32'(y);pv=1;@(negedge clk);pv=0;@(negedge clk);end $fclose(p);
      end
      wait(fd);@(negedge clk);assert(fv==1'(validi)&&fe==!1'(validi))else $fatal(1,"UNIT_FIT_STATUS case=%0d",cid);
      if(validi)assert(gain==32'(g)&&offset==32'(b)&&corr==32'(c))else $fatal(1,"UNIT_FIT_RESULT case=%0d got=%0d,%0d,%0d gold=%0d,%0d,%0d",cid,gain,offset,corr,g,b,c);
      fit_count++;
    end $fclose(f);
    f=$fopen({vectors,"/apply.txt"},"r");assert(f)else $fatal(1,"UNIT_APPLY_OPEN");
    while(!$feof(f))begin
      rc=$fscanf(f,"%d %h %h %d %d %d %d %d\n",cid,word,ts,validi,b,c,expected,sati);assert(rc==8&&cid==apply_count)else $fatal(1,"UNIT_APPLY_FORMAT");
      off=32'(b);cor=32'(c);cv=1'(validi);av=1;wait(ai);@(negedge clk);av=0;
      repeat(3)begin @(negedge clk);assert(ao&&ow==word&&ot==ts&&display_value==32'(expected)&&corrected==1'(validi)&&sat==1'(sati))else $fatal(1,"UNIT_APPLY_SCOREBOARD");end
      ar=1;@(negedge clk);ar=0;apply_count++;
    end $fclose(f);
    f=$fopen({vectors,"/health.txt"},"r");assert(f)else $fatal(1,"UNIT_HEALTH_OPEN");
    while(!$feof(f))begin
      rc=$fscanf(f,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",cid,
        base.valid,base.gain_q20,base.offset_q16,base.zero_variance_q16,base.compression_loss_ppm,base.harmonic_power_ppm,base.otr_count,
        current.valid,current.gain_q20,current.offset_q16,current.zero_variance_q16,current.compression_loss_ppm,current.harmonic_power_ppm,current.otr_count,mask,ki);
      assert(rc==17&&cid==health_count)else $fatal(1,"UNIT_HEALTH_FORMAT");hv=1;wait(hi);@(negedge clk);hv=0;
      repeat(3)begin @(negedge clk);assert(ho&&alarms==7'(mask)&&kind==health_class_t'(4'(ki)))else $fatal(1,"UNIT_HEALTH_SCOREBOARD case=%0d",cid);end
      hr=1;@(negedge clk);hr=0;health_count++;
    end $fclose(f);
    // Reset and withdrawal during collection and division; recover on a valid fit.
    for(integer q=0;q<2;q++)begin
      wait(ready);n=2;nom=262144;start=1;@(negedge clk);start=0;
      px=-1;py=-16384;pv=1;@(negedge clk);px=1;py=16384;@(negedge clk);pv=0;
      repeat(q==0?2:20)@(negedge clk);if(q==0)en=0;else rst=1;repeat(4)@(negedge clk);en=1;rst=0;
      repeat(80)@(negedge clk);assert(ready&&!fv&&!fd)else $fatal(1,"UNIT_FIT_ABORT");
    end
    $display("TEST_PASS tb_innovation_units fit=%0d apply=%0d health=%0d aborts=2 errors=0",fit_count,apply_count,health_count);$finish;
  end
endmodule
`default_nettype wire
