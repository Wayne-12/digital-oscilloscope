`default_nettype none
module dds_scenario #(parameter int unsigned RATE_HZ=25_000_000)(output logic done);
  timeunit 1ns; timeprecision 1ps;
  logic clk, rst, enable;
  scope_pkg::dds_wave_t waveform;
  logic [31:0] inc, offset_phase, sample_phase;
  logic [15:0] amplitude;
  logic signed [17:0] dc_offset;
  logic [13:0] code, input_code, converted;
  logic valid, input_valid, dac_valid;
  integer unsigned edges;
  wire bus_enable=enable && !rst;
  ideal_clock clock_source(.frequency_hz(RATE_HZ),.clk(clk));
  dds_core dut(.clk_dac(clk),.rst(rst),.enable(enable),.waveform(waveform),
    .phase_inc(inc),.phase_offset(offset_phase),.amplitude(amplitude),.dc_offset(dc_offset),
    .dac_code(code),.sample_phase(sample_phase),.sample_valid(valid));
  ad9767_model converter(.rst(rst),.bus_enable(bus_enable),.aclk(clk),.wr1(clk),
    .bclk(1'b0),.wr2(1'b0),.da(code),.input_code(input_code),.dac_code(converted),
    .input_valid(input_valid),.dac_valid(dac_valid),.accepted_edges(edges));
  integer sf,ef,mf,tf,count,cases,seed,rv;
  integer r,e,w,a,o,expected_code,expected_valid,cid;
  logic [31:0] ftw,po,expected_phase;
  logic [13:0] previous_input;
  bit previous_valid;
  integer checked,active_checked,reset_checked,prime_checked;
  integer case_counts[0:17];
  string vd,ed,td;
  initial begin
    done=0;rst=1;enable=0;waveform=scope_pkg::DDS_DC;
    inc=0;offset_phase=0;amplitude=0;dc_offset=0;
    checked=0;active_checked=0;reset_checked=0;prime_checked=0;
    previous_input=14'd8192;previous_valid=0;
    foreach(case_counts[i])case_counts[i]=0;
    if(!$value$plusargs("VECTOR_DIR=%s",vd)||!$value$plusargs("EXPECTED_DIR=%s",ed))
      $fatal(1,"TEST_FAIL DDS missing vector directories");
    if(!$value$plusargs("TRACE_DIR=%s",td))td=".";
    mf=$fopen({vd,"/meta.txt"},"r"); sf=$fopen({vd,"/stimulus.txt"},"r");
    ef=$fopen({ed,"/expected.txt"},"r");
    tf=$fopen($sformatf("%s/dds_r%0d.csv",td,RATE_HZ),"w");
    assert(mf!=0&&sf!=0&&ef!=0&&tf!=0)else $fatal(1,"TEST_FAIL DDS file open");
    rv=$fscanf(mf,"%d %d %d",count,cases,seed);
    assert(rv==3 && cases==18 && count>100000)else $fatal(1,"TEST_FAIL DDS metadata");
    $fwrite(tf,"cycle,case_id,code,phase,valid,input_latch,dac_latch,dac_valid,time_ps\n");
    @(posedge clk);
    for(integer i=0;i<count;i++)begin
      rv=$fscanf(sf,"%d %d %d %d %d %h %h",r,e,w,a,o,ftw,po);
      assert(rv==7)else $fatal(1,"TEST_FAIL DDS truncated stimulus");
      rv=$fscanf(ef,"%d %h %d %d",expected_code,expected_phase,expected_valid,cid);
      assert(rv==4 && cid>=0 && cid<18)else $fatal(1,"TEST_FAIL DDS truncated oracle");
      // Change controls 2 ns after a rising edge, outside the hold window.
      #2ns;
      rst=(r!=0);enable=(e!=0);waveform=scope_pkg::dds_wave_t'(2'(w));
      amplitude=16'(a);dc_offset=18'(o);inc=ftw;offset_phase=po;
      if(r!=0)begin
        // Synchronous reset must not change the DDS output between falling edges.
        automatic logic [13:0] held=code;
        #1ps; assert(code===held)else $fatal(1,"TEST_FAIL DDS asynchronous reset behavior");
      end
      @(negedge clk); #2ps;
      assert(code===14'(expected_code) && sample_phase===expected_phase && valid===1'(expected_valid))
        else $fatal(1,"TEST_FAIL DDS scoreboard rate=%0d cycle=%0d case=%0d got=%0d phase=%h expected=%0d phase=%h",RATE_HZ,i,cid,code,sample_phase,expected_code,expected_phase);
      checked++;case_counts[cid]++;
      if(valid)active_checked++;
      if(r!=0||e==0)begin
        reset_checked++;
        assert(code===14'd8192 && !valid)else $fatal(1,"TEST_FAIL DDS safe code");
      end
      if(e!=0&&r==0&&!valid)prime_checked++;
      @(posedge clk); #2ps;
      if(e!=0&&r==0)begin
        assert(input_valid && input_code===14'(expected_code))
          else $fatal(1,"TEST_FAIL AD9767 input latch scoreboard");
        assert(dac_valid===previous_valid && converted===previous_input)
          else $fatal(1,"TEST_FAIL AD9767 double buffer scoreboard");
        previous_input=14'(expected_code);previous_valid=1;
      end else begin
        assert(!input_valid&&!dac_valid&&converted===14'd8192)
          else $fatal(1,"TEST_FAIL AD9767 reset flush");
        previous_input=14'd8192;previous_valid=0;
      end
      $fwrite(tf,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",i,cid,code,sample_phase,valid,input_code,converted,dac_valid,longint'($realtime*1000.0));
    end
    foreach(case_counts[i]) assert(case_counts[i]>0)else $fatal(1,"TEST_FAIL DDS uncovered case");
    assert(prime_checked>20 && reset_checked>50 && active_checked>100000)
      else $fatal(1,"TEST_FAIL DDS coverage missing");
    assert(converter.setup_checks>100000 && converter.hold_checks>10000 && converter.phase_checks>100000)
      else $fatal(1,"TEST_FAIL DAC timing checks vacuous");
    $display("DAC_TIMING_PASS rate=%0d setup_checks=%0d hold_checks=%0d phase_checks=%0d min_setup_ns=%0.3f min_hold_ns=%0.3f errors=0",RATE_HZ,converter.setup_checks,converter.hold_checks,converter.phase_checks,converter.minimum_setup,converter.minimum_hold);
    $fclose(sf);$fclose(ef);$fclose(mf);$fclose(tf);
    $display("DDS_CASE_PASS rate=%0d cases=18 cycles=%0d active=%0d safe=%0d first_mid=%0d seed=%0d errors=0",RATE_HZ,checked,active_checked,reset_checked,prime_checked,seed);
    done=1;
  end
endmodule
`default_nettype wire
