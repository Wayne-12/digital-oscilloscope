`default_nettype none
module loopback_scenario #(
  parameter int unsigned PROFILE=0,
  parameter realtime T_CO_NS=3.5
)(input wire logic clk,output logic done);
  timeunit 1ns;timeprecision 1ps;
  localparam int unsigned D=(PROFILE==2)?3:(PROFILE==10)?2:(PROFILE==11)?1:(PROFILE==12)?4:0;
  localparam int unsigned F=(PROFILE==2)?16384:(PROFILE==10)?32768:(PROFILE==11)?49152:(PROFILE==12)?65535:0;
  localparam int unsigned G=(PROFILE==3)?8192:(PROFILE==9)?32768:(PROFILE==10)?12288:16384;
  localparam bit INV=(PROFILE==1 || PROFILE==10);
  localparam int signed OFF=(PROFILE==3)?123:(PROFILE==10)?-37:0;
  localparam int unsigned NOISE=(PROFILE==4)?3:(PROFILE==10)?2:0;
  localparam bit CLIP=(PROFILE==5 || PROFILE==10);
  localparam int signed LO=(PROFILE==5)?-1000:-1750, HI=(PROFILE==5)?1000:1750;
  localparam int unsigned ALPHA=(PROFILE==6)?8192:(PROFILE==10)?32768:65536;
  localparam int signed H2=(PROFILE==7)?4096:(PROFILE==10)?2048:0;
  localparam int signed H3=(PROFILE==8)?4096:(PROFILE==10)?-1024:0;
  localparam int unsigned DEPTH=(PROFILE==0)?131072:16384;
  logic rst,enable,capture_enable,force_en,force_val,read_request;
  logic [16:0] read_address;
  logic [31:0] inc,po,noise_seed;
  logic [15:0] amp;
  logic signed [17:0] offset_code;
  scope_pkg::dds_wave_t mode;
  wire [13:0] dds_code,dac_input,dac_output;
  wire [31:0] dds_phase;
  wire dds_valid,di_valid,do_valid;
  integer unsigned dac_edges;
  wire signed [31:0] channel_sample;
  wire channel_valid,channel_clip,adc_fe,adc_fv;
  wire [11:0] adc_raw,cap_raw;
  wire adc_otr,adc_valid,cap_valid,cap_otr;
  wire signed [12:0] cap_signed,report_signed;
  wire [63:0] cap_ts,report_ts;
  wire [15:0] report_word;
  wire report_valid;
  integer unsigned stored;
  dds_core dds(.clk_dac(clk),.rst(rst),.enable(enable),.waveform(mode),.phase_inc(inc),
    .phase_offset(po),.amplitude(amp),.dc_offset(offset_code),.dac_code(dds_code),.sample_phase(dds_phase),.sample_valid(dds_valid));
  ad9767_model dac(.rst(rst),.bus_enable(enable),.aclk(clk),.wr1(clk),.bclk(1'b0),.wr2(1'b0),
    .da(dds_code),.input_code(dac_input),.dac_code(dac_output),.input_valid(di_valid),.dac_valid(do_valid),.accepted_edges(dac_edges));
  loopback_channel_model #(.DELAY_SAMPLES(D),.FRACTION_Q16(F),.GAIN_Q16(G),.INVERT(INV),
    .OFFSET_LSB(OFF),.NOISE_LSB(NOISE),.CLIP_ENABLE(CLIP),.CLIP_LOW(LO),.CLIP_HIGH(HI),
    .LPF_ALPHA_Q16(ALPHA),.EVEN_Q16(H2),.ODD_Q16(H3)) channel(
    .clk_sample(clk),.rst(rst),.dac_code(dac_output),.dac_valid(do_valid),.noise_seed(noise_seed),
    .force_otr_enable(force_en),.force_otr_value(force_val),.ideal_sample(channel_sample),
    .sample_valid(channel_valid),.channel_clipped(channel_clip),.adc_force_otr_enable(adc_fe),.adc_force_otr_value(adc_fv));
  ad9226_model #(.T_CO_NS(T_CO_NS)) adc(.adc_clk(clk),.rst(rst),.ideal_sample(channel_sample),
    .noise_seed(32'd1),.force_otr_enable(adc_fe),.force_otr_value(adc_fv),.raw_code(adc_raw),.otr(adc_otr),.output_valid(adc_valid));
  adc_capture capture(.clk_sample(clk),.rst(rst),.capture_enable(capture_enable),.adc_data(adc_raw),
    .adc_otr(adc_otr),.sample_valid(cap_valid),.sample_raw(cap_raw),.sample_signed(cap_signed),.sample_otr(cap_otr),.sample_timestamp(cap_ts));
  sample_record_readout_model #(.DEPTH(DEPTH)) sink(.clk(clk),.rst(rst),.sample_valid(cap_valid),
    .sample_raw(cap_raw),.sample_otr(cap_otr),.sample_timestamp(cap_ts),.read_request(read_request),
    .read_address(read_address),.report_valid(report_valid),.report_word(report_word),
    .report_timestamp(report_ts),.report_signed(report_signed),.stored_count(stored));
  integer mf,hf,sf,ef,tf,rf,rv,num_cases,seed,cid,length;
  integer sw,sa,so,sfe,sfv;
  logic [31:0] si,sp;
  integer edds,edv,edi,edo,edov,ech,echv,echclip,efe,efv,ear,eao,eav,ecv,ecr,ecs,eco;
  logic [31:0] eph;
  logic [63:0] ect;
  logic [11:0] old_adc_raw;
  logic old_adc_otr,old_adc_valid;
  logic [15:0] gold_words[0:DEPTH-1];
  integer total_cycles,total_captured,total_reported;
  integer captured_case;
  string vd,ed,td,name,key;
  initial begin
    done=0;rst=1;enable=0;capture_enable=0;force_en=0;force_val=0;
    read_request=0;read_address=0;inc=0;po=0;noise_seed=1;amp=0;offset_code=0;mode=scope_pkg::DDS_DC;
    total_cycles=0;total_captured=0;total_reported=0;
    if(!$value$plusargs("VECTOR_DIR=%s",vd)||!$value$plusargs("EXPECTED_DIR=%s",ed))$fatal(1,"TEST_FAIL missing loopback vectors");
    if(!$value$plusargs("TRACE_DIR=%s",td))td=".";
    key=$sformatf("loop_p%0d_d%0d",PROFILE,integer'(T_CO_NS*1000.0));
    mf=$fopen($sformatf("%s/meta_p%0d.txt",vd,PROFILE),"r");
    hf=$fopen($sformatf("%s/cases_p%0d.txt",vd,PROFILE),"r");
    sf=$fopen($sformatf("%s/stim_p%0d.txt",vd,PROFILE),"r");
    ef=$fopen($sformatf("%s/expected_p%0d.txt",ed,PROFILE),"r");
    tf=$fopen({td,"/",key,".csv"},"w");rf=$fopen({td,"/",key,"_report.csv"},"w");
    assert(mf&&hf&&sf&&ef&&tf&&rf)else $fatal(1,"TEST_FAIL loopback file open %s",key);
    rv=$fscanf(mf,"%d %d",num_cases,seed);
    assert(rv==2 && num_cases==((PROFILE==0)?15:14))else $fatal(1,"TEST_FAIL loopback metadata");
    $fwrite(tf,"case_id,cycle,dds_code,dac_output,channel,channel_valid,channel_clipped,adc_raw,adc_otr,cap_valid,raw,signed,otr,timestamp\n");
    $fwrite(rf,"case_id,address,word,signed,otr,timestamp\n");
    for(integer c=0;c<num_cases;c++)begin
      rv=$fscanf(hf,"%d %s %d %h",cid,name,length,noise_seed);
      assert(rv==4 && cid==c && length>128 && length<=DEPTH)else $fatal(1,"TEST_FAIL loopback case header");
      @(posedge clk);#2ns;rst=1;enable=0;capture_enable=0;read_request=0;
      repeat(2)@(posedge clk);
      #2ns;rst=0;enable=1;capture_enable=1;
      captured_case=0;old_adc_raw=12'd2047;old_adc_otr=0;old_adc_valid=0;
      for(integer n=0;n<length;n++)begin
        rv=$fscanf(sf,"%d %d %d %h %h %d %d",sw,sa,so,si,sp,sfe,sfv);
        assert(rv==7)else $fatal(1,"TEST_FAIL truncated loopback stimulus");
        rv=$fscanf(ef,"%d %h %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %h",edds,eph,edv,edi,edo,edov,ech,echv,echclip,efe,efv,ear,eao,eav,ecv,ecr,ecs,eco,ect);
        assert(rv==19)else $fatal(1,"TEST_FAIL truncated loopback oracle");
        mode=scope_pkg::dds_wave_t'(2'(sw));amp=16'(sa);offset_code=18'(so);inc=si;po=sp;
        force_en=1'(sfe);force_val=1'(sfv);
        @(negedge clk);#2ps;
        assert(dds_code===14'(edds) && dds_phase===eph && dds_valid===1'(edv))else $fatal(1,"TEST_FAIL loop DDS %s c=%0d n=%0d",key,c,n);
        assert(channel_sample===32'(ech) && channel_valid===1'(echv) && channel_clip===1'(echclip) && adc_fe===1'(efe) && adc_fv===1'(efv))
          else $fatal(1,"TEST_FAIL loop channel %s c=%0d n=%0d got=%0d exp=%0d",key,c,n,channel_sample,ech);
        @(posedge clk);#2ps;
        assert(dac_input===14'(edi) && dac_output===14'(edo) && do_valid===1'(edov))else $fatal(1,"TEST_FAIL loop DAC buffer %s",key);
        assert(adc_raw===old_adc_raw && adc_otr===old_adc_otr && adc_valid===old_adc_valid)else $fatal(1,"TEST_FAIL loop ADC early Tco %s",key);
        assert(cap_valid===1'(ecv) && cap_raw===12'(ecr) && cap_signed===13'(ecs) && cap_otr===1'(eco) && cap_ts===ect)
          else $fatal(1,"TEST_FAIL loop capture %s c=%0d n=%0d got raw=%0d signed=%0d otr=%b ts=%0d exp raw=%0d signed=%0d otr=%0d ts=%0d",key,c,n,cap_raw,cap_signed,cap_otr,cap_ts,ecr,ecs,eco,ect);
        if(ecv!=0)begin
          assert(ect==64'(captured_case))else $fatal(1,"TEST_FAIL loop capture timestamp gap");
          gold_words[captured_case]={1'(eco),3'b000,12'(ecr)};
          captured_case++;total_captured++;
        end
        #(T_CO_NS);#2ps;
        assert(adc_raw===12'(ear) && adc_otr===1'(eao) && adc_valid===1'(eav))else $fatal(1,"TEST_FAIL loop ADC latency/code/OTR %s",key);
        old_adc_raw=12'(ear);old_adc_otr=1'(eao);old_adc_valid=1'(eav);
        $fwrite(tf,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",c,n,dds_code,dac_output,channel_sample,channel_valid,channel_clip,adc_raw,adc_otr,cap_valid,cap_raw,cap_signed,cap_otr,cap_ts);
        total_cycles++;
      end
      capture_enable=0;enable=0;force_en=0;
      // The record cache samples the capture register on the following edge.
      repeat(2)@(posedge clk);#2ps;
      assert(stored==32'(captured_case) && captured_case==length-8)else $fatal(1,"TEST_FAIL loop storage count %s got=%0d exp=%0d",key,stored,captured_case);
      for(integer address=0;address<captured_case;address++)begin
        @(negedge clk);read_request=1;read_address=17'(address);
        @(posedge clk);#2ps;
        assert(report_valid && report_word===gold_words[address] && report_word[14:12]===3'b000 &&
          report_ts===64'(address) && report_signed===13'(2047-integer'({20'd0,gold_words[address][11:0]})))
          else $fatal(1,"TEST_FAIL loop record/report alignment %s case=%0d address=%0d",key,c,address);
        $fwrite(rf,"%0d,%0d,%0d,%0d,%0d,%0d\n",c,address,report_word,report_signed,report_word[15],report_ts);
        total_reported++;
      end
      @(negedge clk);read_request=0;
      @(posedge clk);#2ps;assert(!report_valid)else $fatal(1,"TEST_FAIL loop report valid stuck");
      $display("LOOP_TEST_PASS key=%s case=%0d name=%s captured=%0d reported=%0d errors=0",key,c,name,captured_case,captured_case);
    end
    assert(total_captured==total_reported && dac.setup_checks>10000)else $fatal(1,"TEST_FAIL loop coverage");
    $fclose(mf);$fclose(hf);$fclose(sf);$fclose(ef);$fclose(tf);$fclose(rf);
    $display("LOOP_CASE_PASS key=%s profile=%0d tco_ps=%0d cases=%0d cycles=%0d captured=%0d reported=%0d seed=%0d errors=0",key,PROFILE,integer'(T_CO_NS*1000.0),num_cases,total_cycles,total_captured,total_reported,seed);
    rst=1;enable=0;capture_enable=0;done=1;
  end
endmodule
`default_nettype wire
