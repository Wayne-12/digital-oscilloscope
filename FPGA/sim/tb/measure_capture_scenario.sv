`default_nettype none
module measure_capture_scenario(input wire logic run,output logic done);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  logic ca=0,cs=0;
  always #20ns ca=~ca;
  always #5ns cs=~cs;
  logic ra,rs,en,arm,sv,otr,rd,release_frame;
  adc_raw_t raw;
  sample_timestamp_t ts;
  trigger_config_t config_in,armed_config;
  capture_state_t state;
  wire logic single_done,capture_error,busy,frame_ready,read_valid;
  bram_addr_t wp,index_in;
  capture_metadata_t metadata;
  sample_word_t word_out;
  adc_sample_t signed_out;
  sample_timestamp_t timestamp_out;
  bram_capture #(.USE_EXTENDED_TRIGGER(1'b1)) capture_dut(.clk_adc(ca),.rst_adc(ra),.module_enable(en),.arm(arm),
    .cfg_mode(CAP_SINGLE),.cfg_rising(1'b1),.cfg_threshold(13'sd0),.cfg_hysteresis(13'd8),
    .cfg_pre_samples(15'd16),.cfg_auto_timeout(32'd100),.cfg_trigger(config_in),
    .sample_valid(sv),.sample_raw(raw),.sample_otr(otr),.sample_timestamp(ts),.capture_state(state),
    .single_done(single_done),.capture_error(capture_error),.busy(busy),.write_pointer(wp),
    .clk_sys(cs),.rst_sys(rs),.read_request(rd),.frame_release(release_frame),.read_index(index_in),
    .frame_ready(frame_ready),.read_valid(read_valid),.frame_metadata(metadata),
    .read_word(word_out),.read_signed(signed_out),.read_timestamp(timestamp_out));
  logic start,mv;
  adc_sample_t mx;
  sample_timestamp_t mt;
  wire logic ready,mbusy,mdone,mvalid,merror;
  measurement_result_t result;
  measurement_core measure_dut(.clk(cs),.rst(rs),.start(start),.frame_length(18'd16384),
    .sample_rate_hz(32'd25000000),.threshold(13'sd0),.hysteresis(13'd8),.sample_valid(mv),
    .sample_signed(mx),.sample_timestamp(mt),.sample_ready(ready),.busy(mbusy),.measurement_done(mdone),
    .measurement_valid(mvalid),.measurement_error(merror),.result(result));
  integer values[0:16499],otrs[0:16499];
  string vd,ed,td;
  integer f,e,csv,mcsv,ncases,cid,n,ti,k,th,h,wl,wh,wmin,wmax,amp,obs,rc;
  integer ecid,enpoints,emin,emax,emean,ep2p,erms,ep,ef,eduty,ee,ev,waits;
  logic signed [63:0] esum;
  logic [63:0] ess,eper;
  initial begin
    done=0;ra=1;rs=1;en=0;arm=0;sv=0;otr=0;rd=0;release_frame=0;
    raw=12'd2047;ts=0;config_in='0;index_in=0;start=0;mv=0;mx=0;mt=0;
    wait(run);
    assert($value$plusargs("VECTOR_DIR=%s",vd) && $value$plusargs("EXPECTED_DIR=%s",ed) && $value$plusargs("TRACE_DIR=%s",td))else $fatal(1,"TEST_FAIL integration dirs");
    f=$fopen({vd,"/integration.txt"},"r");e=$fopen({ed,"/integration.txt"},"r");
    csv=$fopen({td,"/integration_points.csv"},"w");mcsv=$fopen({td,"/integration_measure.csv"},"w");
    assert(f && e && csv && mcsv)else $fatal(1,"TEST_FAIL integration files");
    $fdisplay(csv,"case_id,index,word,signed,timestamp");
    $fdisplay(mcsv,"case_id,count,minimum,maximum,mean,peak_to_peak,rms,sum,square_sum,period_count,period_q16,frequency_hz,duty_ppm,error,valid");
    rc=$fscanf(f,"%d",ncases);assert(rc==1 && ncases==9)else $fatal(1,"TEST_FAIL integration count");
    // The capture wrapper must reject invalid extended configurations at arm.
    for(integer bad=0;bad<4;bad++)begin
      @(negedge ca);ra=1;rs=1;en=0;arm=0;sv=0;config_in='0;
      repeat(3)@(negedge ca);
      ra=0;rs=0;en=1;arm=1;
      case(bad)
        0: config_in.kind=trigger_type_t'(4'd15);
        1: begin config_in.kind=TRIG_WINDOW_ENTER;config_in.window_low=13'sd100;config_in.window_high=-13'sd100;end
        2: begin config_in.kind=TRIG_POS_WIDTH;config_in.width_min=0;config_in.width_max=7;end
        3: begin config_in.kind=TRIG_UNDER_AMPLITUDE;config_in.observation_samples=1;end
      endcase
      @(posedge ca);#1ps;
      assert(state==CAP_IDLE && capture_error && !busy && wp==14'd0)
        else $fatal(1,"TEST_FAIL invalid extended arm bad=%0d",bad);
    end
    $display("MEASURE_CAPTURE_CONFIG_PASS invalid_arms=4 errors=0");
    for(integer c=0;c<ncases;c++)begin
      rc=$fscanf(f,"%d %d %d %d %d %d %d %d %d %d %d %d",cid,n,ti,k,th,h,wl,wh,wmin,wmax,amp,obs);
      assert(rc==12)else $fatal(1,"TEST_FAIL integration header");
      for(integer i=0;i<n;i++)begin
        rc=$fscanf(f,"%d %d",values[i],otrs[i]);assert(rc==2)else $fatal(1,"TEST_FAIL integration row");
      end
      rc=$fscanf(e,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d",ecid,enpoints,emin,emax,emean,ep2p,erms,esum,ess,ep,eper,ef,eduty,ee,ev);
      assert(rc==15 && ecid==cid)else $fatal(1,"TEST_FAIL integration oracle");
      @(negedge ca);ra=1;en=0;sv=0;arm=0;rs=1;rd=0;release_frame=0;start=0;mv=0;
      repeat(3)@(negedge ca);
      ra=0;rs=0;en=1;arm=1;
      config_in.kind=trigger_type_t'(4'(k));config_in.threshold=13'(th);config_in.hysteresis=13'(h);
      config_in.window_low=13'(wl);config_in.window_high=13'(wh);config_in.width_min=32'(wmin);config_in.width_max=32'(wmax);
      config_in.amplitude_limit=14'(amp);config_in.observation_samples=15'(obs);
      armed_config=config_in;
      @(negedge ca);arm=0;
      for(integer i=0;i<n;i++)begin
        if(i==5)config_in='1; // Must not change the already-armed trigger.
        sv=1;raw=12'(2047-values[i]);otr=1'(otrs[i]);ts=64'(i);
        @(posedge ca);#1ps;
        assert(!capture_error)else $fatal(1,"TEST_FAIL integration capture error");
        if(i==ti)assert(state==CAP_POST)else $fatal(1,"TEST_FAIL integration trigger time kind=%0d expected=%0d state=%0d",k,ti,state);
        @(negedge ca);
      end
      sv=0;en=0;waits=0;
      while(!frame_ready && waits<20)begin @(posedge cs);#1ps;waits++;end
      assert(frame_ready && single_done && metadata.trigger_index==14'd16 &&
        metadata.trigger_timestamp==64'(ti) && metadata.first_timestamp==64'(ti-16) &&
        metadata.last_timestamp==64'(ti+16367) && metadata.extended_trigger && metadata.trigger_config===armed_config)
        else $fatal(1,"TEST_FAIL integration metadata kind=%0d got trigger=%0d expected=%0d",k,metadata.trigger_timestamp,ti);
      @(negedge cs);start=1;@(negedge cs);start=0;
      for(integer j=0;j<16384;j++)begin
        @(negedge cs);rd=1;index_in=14'(j);
        @(posedge cs);#1ps;
        assert(read_valid && word_out===16'((otrs[ti-16+j]<<15)|(2047-values[ti-16+j])) &&
          signed_out===13'(values[ti-16+j]) && timestamp_out==64'(ti-16+j))
          else $fatal(1,"TEST_FAIL integration point kind=%0d index=%0d",k,j);
        $fdisplay(csv,"%0d,%0d,%0d,%0d,%0d",cid,j,word_out,signed_out,timestamp_out);
        @(negedge cs);rd=0;mv=1;mx=signed_out;mt=timestamp_out;
        assert(ready)else $fatal(1,"TEST_FAIL integration measure ready");
        @(posedge cs);#1ps;@(negedge cs);mv=0;
      end
      waits=0;while(!mdone && waits<400)begin @(posedge cs);#1ps;waits++;end
      assert(mdone && !merror && result.stats_valid && result.sample_count==15'd16384 &&
        result.minimum===13'(emin) && result.maximum===13'(emax) && result.mean===13'(emean) &&
        result.peak_to_peak==14'(ep2p) && result.rms==14'(erms) && result.sum===esum && result.square_sum===ess &&
        result.period_count==15'(ep) && result.period_q16==eper && result.frequency_hz==32'(ef) &&
        result.duty_ppm==32'(eduty) && mvalid===1'(ev))else $fatal(1,"TEST_FAIL integration measurement kind=%0d",k);
      $fdisplay(mcsv,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cid,
        result.sample_count,result.minimum,result.maximum,result.mean,result.peak_to_peak,result.rms,result.sum,result.square_sum,
        result.period_count,result.period_q16,result.frequency_hz,result.duty_ppm,merror,mvalid);
      $display("MEASURE_CAPTURE_PASS kind=%0d trigger_timestamp=%0d points=16384 errors=0",k,ti);
    end
    $fclose(f);$fclose(e);$fclose(csv);$fclose(mcsv);done=1;
  end
endmodule
`default_nettype wire
