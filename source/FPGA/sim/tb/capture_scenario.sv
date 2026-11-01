`default_nettype none
module capture_scenario #(
  parameter int unsigned SID=0,ADC_RATE=25000000,SYS_RATE=100000000
)(output logic done);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  wire ca,cs;
  ideal_clock adc_clock(.frequency_hz(ADC_RATE),.clk(ca));
  ideal_clock sys_clock(.frequency_hz(SYS_RATE),.clk(cs));
  logic ra,rs,module_enable,arm,sv,otr,rdreq,release_frame,cfg_rising;
  adc_raw_t raw;
  sample_timestamp_t ts,read_ts;
  capture_mode_t cfg_mode;
  adc_sample_t cfg_threshold;
  logic [12:0] cfg_hyst;
  logic [14:0] cfg_pre;
  logic [31:0] cfg_timeout;
  capture_state_t state;
  wire single_done,capture_error,busy,ready,rvalid;
  bram_addr_t wp,rindex;
  capture_metadata_t metadata;
  sample_word_t rword;
  adc_sample_t rsigned;
  bram_capture dut(.clk_adc(ca),.rst_adc(ra),.module_enable(module_enable),.arm(arm),
    .cfg_mode(cfg_mode),.cfg_rising(cfg_rising),.cfg_threshold(cfg_threshold),.cfg_hysteresis(cfg_hyst),.cfg_trigger(trigger_config_t'('0)),
    .cfg_pre_samples(cfg_pre),.cfg_auto_timeout(cfg_timeout),.sample_valid(sv),.sample_raw(raw),
    .sample_otr(otr),.sample_timestamp(ts),.capture_state(state),.single_done(single_done),
    .capture_error(capture_error),.busy(busy),.write_pointer(wp),.clk_sys(cs),.rst_sys(rs),
    .read_request(rdreq),.frame_release(release_frame),.read_index(rindex),.frame_ready(ready),
    .read_valid(rvalid),.frame_metadata(metadata),.read_word(rword),.read_signed(rsigned),.read_timestamp(read_ts));
  integer writes,compared,frames_seen,rereads,aux_tests,aux_compared;
  integer mf,cf,hf,tf,mtf,rv,case_count,expected_frames,seed,rate_adc,rate_sys;
  integer cid,mode_i,pre,rise,threshold_i,hyst_i,timeout_i,flags,frames_i;
  integer length,target,start_addr,trig_addr,end_ptr,automatic_i;
  logic [63:0] first_ts,trig_ts,last_ts;
  string vd,ed,td,name;
  initial begin writes=0;compared=0;frames_seen=0;rereads=0;aux_tests=0;aux_compared=0;end
  always @(posedge ca)begin
    if(!ra)begin
      assert(!$isunknown({state,wp,single_done,capture_error}))else $fatal(1,"TEST_FAIL unknown capture control sid=%0d",SID);
      if(busy && sv && module_enable)assert(!$isunknown({raw,otr,ts}))else $fatal(1,"TEST_FAIL unknown input transaction");
      if(dut.ram_write_enable)writes++;
      if(ready || state==CAP_SINGLE_HOLD)assert(!dut.ram_write_enable)else $fatal(1,"TEST_FAIL frozen/single write sid=%0d",SID);
    end
  end
  always @(posedge cs)begin
    if(!rs && dut.ram_read_enable)
      assert(state==CAP_FROZEN && ready)else $fatal(1,"TEST_FAIL read ownership sid=%0d",SID);
  end
  task automatic reset_all;
    module_enable=0;arm=0;sv=0;rdreq=0;release_frame=0;ra=1;rs=1;
    repeat(4)@(posedge ca);repeat(4)@(posedge cs);#2ps;
    ra=0;rs=0;repeat(3)@(posedge ca);repeat(3)@(posedge cs);#2ps;
    assert(state==CAP_IDLE && !ready && !rvalid && !single_done)else $fatal(1,"TEST_FAIL capture reset sid=%0d",SID);
  endtask
  task automatic config_original;
    cfg_mode=capture_mode_t'(2'(mode_i));cfg_rising=1'(rise);cfg_threshold=13'(threshold_i);
    cfg_hyst=13'(hyst_i);cfg_pre=15'(pre);cfg_timeout=32'(timeout_i);
  endtask
  task automatic pulse_arm;
    @(negedge ca);module_enable=1;arm=1;sv=0;
    @(posedge ca);#2ps;assert(state==CAP_ARMED && !capture_error && !single_done)else $fatal(1,"TEST_FAIL arm sid=%0d",SID);
    @(negedge ca);arm=0;
  endtask
  task automatic await_frame;
    for(integer k=0;k<20 && !ready;k++)begin @(posedge cs);#2ps;end
    assert(ready)else $fatal(1,"TEST_FAIL CDC frame deadline sid=%0d",SID);
  endtask
  task automatic check_metadata;
    assert(metadata.start_address===14'(start_addr) && metadata.trigger_address===14'(trig_addr) &&
      metadata.trigger_index===14'(pre) && metadata.frame_length===15'd16384 && metadata.pre_samples===15'(pre) &&
      metadata.post_samples===15'(16383-pre) && metadata.first_timestamp===first_ts &&
      metadata.trigger_timestamp===trig_ts && metadata.last_timestamp===last_ts &&
      metadata.automatic_trigger===1'(automatic_i) && metadata.mode===capture_mode_t'(2'(mode_i)) &&
      metadata.rising===1'(rise) && metadata.threshold===13'(threshold_i) && metadata.hysteresis===13'(hyst_i))
      else $fatal(1,"TEST_FAIL frame metadata sid=%0d case=%0d start=%0d/%0d trigger=%0d/%0d",SID,cid,metadata.start_address,start_addr,metadata.trigger_address,trig_addr);
    assert(wp===14'(end_ptr))else $fatal(1,"TEST_FAIL final pointer sid=%0d",SID);
  endtask
  task automatic feed_frame(input integer f);
    integer fd,nread,before_writes;
    logic [11:0] next_raw;integer next_otr;logic [63:0] next_ts;
    fd=$fopen($sformatf("%s/s%0d_c%0d_f%0d_stim.txt",vd,SID,cid,f),"r");
    assert(fd)else $fatal(1,"TEST_FAIL stimulus open");before_writes=writes;
    for(integer n=0;n<length;n++)begin
      nread=$fscanf(fd,"%h %d %h",next_raw,next_otr,next_ts);assert(nread==3)else $fatal(1,"TEST_FAIL truncated source");
      if((flags&16)!=0 && n%17==5)begin
        automatic bram_addr_t held=wp;
        @(negedge ca);sv=0;@(posedge ca);#2ps;
        assert(wp===held)else $fatal(1,"TEST_FAIL valid bubble wrote RAM");
      end
      @(negedge ca);sv=1;raw=next_raw;otr=1'(next_otr);ts=next_ts;
      if((flags&4)!=0 && n==10)begin cfg_pre=15'd16384;cfg_threshold=13'sd2047;cfg_hyst=13'd8191;cfg_mode=CAP_AUTO;end
      @(posedge ca);#2ps;
      assert(wp===14'((n+1)%16384) && !capture_error)else $fatal(1,"TEST_FAIL write sequence sid=%0d case=%0d n=%0d",SID,cid,n);
      if(n<target)assert(state==CAP_ARMED)else $fatal(1,"TEST_FAIL early trigger sid=%0d case=%0d n=%0d target=%0d",SID,cid,n,target);
      else if(n<length-1)assert(state==CAP_POST)else $fatal(1,"TEST_FAIL post count sid=%0d case=%0d n=%0d",SID,cid,n);
      else assert(state==CAP_FROZEN)else $fatal(1,"TEST_FAIL freeze deadline sid=%0d case=%0d",SID,cid);
    end
    sv=0;$fclose(fd);
    assert(writes-before_writes==length && single_done===(mode_i==2))else $fatal(1,"TEST_FAIL captured count/single flag");
  endtask
  task automatic frozen_samples(input integer count);
    automatic bram_addr_t held=wp;
    for(integer n=0;n<count;n++)begin
      @(negedge ca);sv=1;raw=12'(n*19);otr=1'(n);ts=64'(n*3+567);
      @(posedge ca);#2ps;
      assert(!dut.ram_write_enable && wp===held && !capture_error)else $fatal(1,"TEST_FAIL frozen overwrite sid=%0d",SID);
    end
    sv=0;
  endtask
  task automatic read_frame(input integer f,input integer pass_number);
    integer fd,nread,expected_signed;logic [15:0] expected_word;logic [63:0] expected_ts;
    automatic capture_metadata_t held=metadata;
    fd=$fopen($sformatf("%s/s%0d_c%0d_f%0d_frame.txt",ed,SID,cid,f),"r");assert(fd)else $fatal(1,"TEST_FAIL frame oracle open");
    for(integer i=0;i<16384;i++)begin
      nread=$fscanf(fd,"%h %h %d",expected_word,expected_ts,expected_signed);assert(nread==3)else $fatal(1,"TEST_FAIL truncated frame oracle");
      if((i+seed)%19==0)begin
        @(negedge cs);rdreq=0;@(posedge cs);#2ps;assert(!rvalid)else $fatal(1,"TEST_FAIL read valid bubble");
      end
      @(negedge cs);rdreq=1;rindex=14'(i);
      @(posedge cs);#2ps;
      assert(ready && rvalid && rword===expected_word && read_ts===expected_ts && rsigned===13'(expected_signed) &&
        metadata===held && rword[14:12]===3'b000)
        else $fatal(1,"TEST_FAIL frame scoreboard sid=%0d case=%0d f=%0d pass=%0d index=%0d got=%h exp=%h ts=%0d/%0d",SID,cid,f,pass_number,i,rword,expected_word,read_ts,expected_ts);
      $fwrite(tf,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cid,f,pass_number,i,rword,rsigned,rword[15],read_ts);
      compared++;
    end
    @(negedge cs);rdreq=0;@(posedge cs);#2ps;assert(!rvalid)else $fatal(1,"TEST_FAIL stale read valid");
    $fclose(fd);if(pass_number!=0)rereads++;
  endtask
  task automatic release_and_wait(input bit repeating);
    if(!repeating)module_enable=0;
    @(negedge cs);release_frame=1;rdreq=1;rindex=0;
    @(posedge cs);#2ps;assert(!ready && !rvalid)else $fatal(1,"TEST_FAIL release/read cancellation");
    @(negedge cs);release_frame=0;rdreq=0;
    for(integer k=0;k<12 && state==CAP_FROZEN;k++)begin @(posedge ca);#2ps;end
    if(mode_i==2)assert(state==CAP_SINGLE_HOLD && single_done)else $fatal(1,"TEST_FAIL single release did not hold");
    else if(repeating)assert(state==CAP_ARMED)else $fatal(1,"TEST_FAIL normal/auto did not rearm");
    else assert(state==CAP_IDLE)else $fatal(1,"TEST_FAIL release did not idle");
  endtask
  task automatic put(input integer v,input logic [63:0] stamp);
    @(negedge ca);sv=1;raw=12'(2047-v);otr=stamp[0];ts=stamp;
    @(posedge ca);#2ps;
  endtask
  task automatic check_aborted(input bit expect_error);
    sv=0;repeat(8)@(posedge cs);#2ps;
    assert(state==CAP_IDLE && !ready && capture_error===expect_error)else $fatal(1,"TEST_FAIL abort state/error sid=%0d",SID);
    aux_tests++;
  endtask
  task automatic auxiliary;
    // Quiet normal mode and within-band jitter must never timeout or chatter.
    reset_all();cfg_mode=CAP_NORMAL;cfg_pre=0;cfg_rising=1;cfg_threshold=0;cfg_hyst=8;cfg_timeout=1;pulse_arm();
    put(-9,0);for(integer i=1;i<513;i++)put((i%15)-7,64'(i));
    assert(state==CAP_ARMED && !ready)else $fatal(1,"TEST_FAIL normal quiet/Schmitt noise");
    @(negedge ca);module_enable=0;@(posedge ca);#2ps;check_aborted(0);
    // Withdrawal before and after the trigger.
    reset_all();cfg_mode=CAP_SINGLE;cfg_pre=8192;pulse_arm();
    for(integer i=0;i<100;i++)put(-100,64'(i));
    @(negedge ca);module_enable=0;@(posedge ca);#2ps;check_aborted(0);
    reset_all();cfg_pre=0;pulse_arm();put(-9,0);put(9,1);assert(state==CAP_POST)else $fatal(1,"TEST_FAIL aux trigger");
    for(integer i=2;i<9;i++)put(i,64'(i));
    @(negedge ca);module_enable=0;@(posedge ca);#2ps;check_aborted(0);
    // Timestamp discontinuity must not create fictitious per-point timestamps.
    reset_all();cfg_mode=CAP_NORMAL;cfg_pre=8192;pulse_arm();put(-9,0);put(-9,2);check_aborted(1);
    reset_all();cfg_pre=0;pulse_arm();put(-9,0);put(9,1);put(0,3);check_aborted(1);
    if(SID==0)begin
      // Withdrawal wins over an edge crossing and over the final POST write.
      reset_all();cfg_mode=CAP_SINGLE;cfg_pre=0;pulse_arm();put(-9,0);
      @(negedge ca);sv=1;raw=12'(2047-9);ts=64'd1;module_enable=0;
      @(posedge ca);#2ps;check_aborted(0);
      reset_all();cfg_mode=CAP_SINGLE;cfg_pre=16382;pulse_arm();
      for(integer i=0;i<16383;i++)put(-9,64'(i));put(9,64'd16383);
      assert(state==CAP_POST && !single_done)else $fatal(1,"TEST_FAIL last POST setup");
      @(negedge ca);module_enable=0;ts=64'd16384;@(posedge ca);#2ps;check_aborted(0);
      reset_all();cfg_pre=0;pulse_arm();put(-9,0);put(9,1);reset_all();aux_tests++;
      // Invalid pre-count and auto timeout are rejected without RAM writes.
      cfg_pre=16384;cfg_mode=CAP_SINGLE;
      @(negedge ca);module_enable=1;arm=1;@(posedge ca);#2ps;assert(capture_error && state==CAP_IDLE)else $fatal(1,"TEST_FAIL invalid pre accepted");
      @(negedge ca);arm=0;cfg_pre=0;cfg_mode=CAP_AUTO;cfg_timeout=0;
      @(negedge ca);arm=1;@(posedge ca);#2ps;assert(capture_error && state==CAP_IDLE)else $fatal(1,"TEST_FAIL zero timeout accepted");
      @(negedge ca);arm=0;cfg_mode=capture_mode_t'(2'd3);cfg_timeout=1;
      @(negedge ca);arm=1;@(posedge ca);#2ps;assert(capture_error && state==CAP_IDLE)else $fatal(1,"TEST_FAIL invalid mode accepted");
      @(negedge ca);arm=0;aux_tests++;
      // Build a complete constant frame, withdraw enable while frozen, compare
      // every real BRAM word, then reset with a read in progress.
      reset_all();cfg_mode=CAP_AUTO;cfg_timeout=1;cfg_pre=16383;pulse_arm();
      for(integer i=0;i<16384;i++)put(0,64'(i));sv=0;await_frame();
      module_enable=0;
      for(integer i=0;i<16384;i++)begin
        @(negedge cs);rdreq=1;rindex=14'(i);@(posedge cs);#2ps;
        assert(ready && rvalid && rword==={1'(i),3'b000,12'd2047} && read_ts===64'(i) && rsigned===13'sd0)
          else $fatal(1,"TEST_FAIL frozen disable frame");aux_compared++;
      end
      reset_all();aux_tests++;
      reset_all();cfg_mode=CAP_AUTO;cfg_timeout=1;cfg_pre=16383;pulse_arm();
      for(integer i=0;i<16384;i++)put(0,64'(i));sv=0;await_frame();
      reset_all();aux_tests++;
    end
    $display("CAPTURE_AUX_PASS sid=%0d tests=%0d frame_points=%0d errors=0",SID,aux_tests,aux_compared);
  endtask
  initial begin
    done=0;ra=1;rs=1;module_enable=0;arm=0;sv=0;otr=0;raw=2047;ts=0;
    rdreq=0;release_frame=0;rindex=0;cfg_mode=CAP_SINGLE;cfg_rising=1;cfg_threshold=0;cfg_hyst=8;cfg_pre=0;cfg_timeout=1;
    if(!$value$plusargs("VECTOR_DIR=%s",vd)||!$value$plusargs("EXPECTED_DIR=%s",ed))$fatal(1,"TEST_FAIL capture vector paths");
    if(!$value$plusargs("TRACE_DIR=%s",td))td=".";
    mf=$fopen($sformatf("%s/meta_s%0d.txt",vd,SID),"r");cf=$fopen($sformatf("%s/cases_s%0d.txt",vd,SID),"r");
    hf=$fopen($sformatf("%s/frames_s%0d.txt",ed,SID),"r");
    tf=$fopen($sformatf("%s/capture_s%0d.csv",td,SID),"w");mtf=$fopen($sformatf("%s/capture_s%0d_metadata.csv",td,SID),"w");
    assert(mf&&cf&&hf&&tf&&mtf)else $fatal(1,"TEST_FAIL capture file open");
    rv=$fscanf(mf,"%d %d %d %d %d",case_count,expected_frames,seed,rate_adc,rate_sys);
    assert(rv==5 && rate_adc==integer'(ADC_RATE) && rate_sys==integer'(SYS_RATE))else $fatal(1,"TEST_FAIL capture metadata clock");
    $fwrite(tf,"case_id,frame,pass,index,word,signed,otr,timestamp\n");
    $fwrite(mtf,"case_id,frame,start_address,trigger_address,trigger_index,pre,post,first_timestamp,trigger_timestamp,last_timestamp,automatic,mode,rising,final_pointer\n");
    for(integer c=0;c<case_count;c++)begin
      rv=$fscanf(cf,"%d %s %d %d %d %d %d %d %d %d",cid,name,mode_i,pre,rise,threshold_i,hyst_i,timeout_i,flags,frames_i);
      assert(rv==10 && cid==c)else $fatal(1,"TEST_FAIL capture case header");
      reset_all();config_original();pulse_arm();
      for(integer f=0;f<frames_i;f++)begin
        rv=$fscanf(hf,"%d %d %d %d %d %h %h %h %d",length,target,start_addr,trig_addr,end_ptr,first_ts,trig_ts,last_ts,automatic_i);
        assert(rv==9)else $fatal(1,"TEST_FAIL capture frame header");
        feed_frame(f);await_frame();check_metadata();
        $fwrite(mtf,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cid,f,metadata.start_address,metadata.trigger_address,metadata.trigger_index,metadata.pre_samples,metadata.post_samples,metadata.first_timestamp,metadata.trigger_timestamp,metadata.last_timestamp,metadata.automatic_trigger,metadata.mode,metadata.rising,wp);
        fork
          frozen_samples((mode_i==2)?32785:1024);
          read_frame(f,0);
        join
        if(mode_i==2)begin read_frame(f,1);check_metadata();end
        frames_seen++;
        release_and_wait(f<frames_i-1);
        if(f<frames_i-1 && mode_i==2)begin
          frozen_samples(1024);config_original();pulse_arm();
        end
        $display("CAPTURE_FRAME_PASS sid=%0d case=%0d name=%s frame=%0d pre=%0d trigger_addr=%0d auto=%0d errors=0",SID,cid,name,f,pre,trig_addr,automatic_i);
      end
    end
    auxiliary();
    assert(frames_seen==expected_frames && compared>=expected_frames*16384)else $fatal(1,"TEST_FAIL capture frame coverage");
    $fclose(mf);$fclose(cf);$fclose(hf);$fclose(tf);$fclose(mtf);
    $display("CAPTURE_SCENARIO_PASS sid=%0d adc=%0d sys=%0d cases=%0d frames=%0d points=%0d rereads=%0d aux_points=%0d seed=%0d errors=0",SID,ADC_RATE,SYS_RATE,case_count,frames_seen,compared,rereads,aux_compared,seed);
    module_enable=0;sv=0;rdreq=0;done=1;
  end
endmodule
`default_nettype wire
