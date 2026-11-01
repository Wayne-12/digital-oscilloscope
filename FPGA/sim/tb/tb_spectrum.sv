`default_nettype none
module tb_spectrum;
  timeunit 1ns;timeprecision 1ps;
  import spectrum_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst,enable,start,hann,svalid,slast,sotr,mready,bready,rready;
  wire start_ready,sready,mvalid,bvalid,rvalid,config_error,cancelled;
  logic [31:0] rate,threshold;
  logic [17:0] source_index;
  logic [63:0] first_ts,sts;
  logic signed [12:0] sample_value;
  spectrum_metadata_t meta;
  spectrum_bin_t bin_data;
  spectrum_result_t result;
  spectrum_analyzer dut(.clk(clk),.rst(rst),.module_enable(enable),.start(start),.start_ready(start_ready),
    .cfg_hann(hann),.cfg_sample_rate(rate),.cfg_first_timestamp(first_ts),.cfg_source_first_index(source_index),.cfg_threshold_q16(threshold),
    .sample_valid(svalid),.sample_ready(sready),.sample_signed(sample_value),.sample_otr(sotr),.sample_timestamp(sts),.sample_last(slast),
    .metadata_valid(mvalid),.metadata_ready(mready),.metadata(meta),.bin_valid(bvalid),.bin_ready(bready),.bin_data(bin_data),
    .result_valid(rvalid),.result_ready(rready),.result(result),.config_error(config_error),.cancelled(cancelled));
  integer samples[0:1023],otrs[0:1023],gr[0:1023],gi[0:1023],weighted[0:1023];
  logic [63:0] timestamps[0:1023];
  string vectors,expected,path;
  integer seed,unused,cf,f,cid,win,fs,src,eo,ev,ep,ef,ea,er,ed,rc,idx,a,b,sent,received,cycles,meta_count,amp_error,rms_error,bin_file,result_file,case_count;
  integer unsigned rng;
  logic [63:0] ts;
  logic accepted;
  logic signed [63:0] actual_r,actual_i;
  logic [63:0] p;
  spectrum_result_t held_result;
  spectrum_bin_t held_bin;
  spectrum_metadata_t held_meta;
  logic rs,bs,ms;
  function automatic integer unsigned random_next(input integer unsigned x);
    integer unsigned y;begin y=x^(x<<13);y=y^(y>>17);random_next=y^(y<<5);end
  endfunction
  initial begin #100ms;$fatal(1,"SPECTRUM_WATCHDOG");end
  initial begin
    rst=1;enable=1;start=0;hann=0;rate=0;threshold=32'd131072;source_index=0;first_ts=0;
    svalid=0;slast=0;sotr=0;sts=0;sample_value=0;mready=0;bready=0;rready=0;
    seed=20261020;unused=$value$plusargs("SEED=%d",seed);rng=32'(seed);
    if(!$value$plusargs("VECTOR_DIR=%s",vectors)||!$value$plusargs("EXPECTED_DIR=%s",expected))$fatal(1,"SPECTRUM_PATHS");
    bin_file=$fopen("spectrum_bins.csv","w");result_file=$fopen("spectrum_results.csv","w");
    $fdisplay(bin_file,"case_id,bin,real,imag,power");
    $fdisplay(result_file,"case_id,valid,peak_bin,frequency_hz,amplitude_q16,rms_q16,dc_mean_q16,clipped,peak_power");
    repeat(6)@(negedge clk);rst=0;
    cf=$fopen({vectors,"/spectrum_cases.txt"},"r");if(!cf)$fatal(1,"SPECTRUM_CASE_OPEN");case_count=0;
    while(!$feof(cf))begin
      rc=$fscanf(cf,"%d %d %d %d %h %d %d %d %d %d %d %d\n",cid,win,fs,src,ts,eo,ev,ep,ef,ea,er,ed);
      assert(rc==12)else $fatal(1,"SPECTRUM_CASE_FORMAT");
      f=$fopen($sformatf("%s/samples_%0d.txt",vectors,cid),"r");if(!f)$fatal(1,"SPECTRUM_INPUT_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d %d %h\n",idx,a,b,timestamps[n]);assert(rc==4&&idx==n)else $fatal(1,"SPECTRUM_INPUT_FORMAT");samples[n]=a;otrs[n]=b;end $fclose(f);
      f=$fopen($sformatf("%s/fft_%0d.txt",expected,cid),"r");if(!f)$fatal(1,"SPECTRUM_GOLD_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d %d\n",idx,a,b);assert(rc==3&&idx==n)else $fatal(1,"SPECTRUM_GOLD_FORMAT");gr[n]=a;gi[n]=b;end $fclose(f);
      f=$fopen($sformatf("%s/weighted_%0d.txt",expected,cid),"r");if(!f)$fatal(1,"SPECTRUM_WEIGHT_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d\n",idx,a);assert(rc==2&&idx==n)else $fatal(1,"SPECTRUM_WEIGHT_FORMAT");weighted[n]=a;end $fclose(f);
      while(!start_ready)@(negedge clk);
      hann=1'(win);rate=32'(fs);source_index=18'(src);first_ts=ts;start=1;@(negedge clk);start=0;
      sent=0;received=0;cycles=0;meta_count=0;rs=0;bs=0;ms=0;
      while(1)begin
        rng=random_next(rng);mready=rng[0];bready=rng[3:1]!=3'd0;rready=rng[6:4]!=3'd0;
        if(!svalid&&sent<1024&&rng[9:7]!=3'd0)begin svalid=1;sample_value=13'(samples[sent]);sotr=1'(otrs[sent]);sts=timestamps[sent];slast=(sent==1023);end
        @(posedge clk);
        assert(!config_error)else $fatal(1,"SPECTRUM_CONFIG_ERROR");
        if(rs)assert(rvalid&&result==held_result)else $fatal(1,"SPECTRUM_RESULT_STABILITY");
        if(bs)assert(bvalid&&bin_data==held_bin)else $fatal(1,"SPECTRUM_BIN_STABILITY");
        if(ms)assert(mvalid&&meta==held_meta)else $fatal(1,"SPECTRUM_META_STABILITY");
        rs=rvalid&&!rready;bs=bvalid&&!bready;ms=mvalid&&!mready;held_result=result;held_bin=bin_data;held_meta=meta;
        accepted=svalid&&sready;
        if(accepted)begin
          assert($signed(dut.weighted_sample)==weighted[sent])else $fatal(1,"SPECTRUM_WINDOW_MISMATCH case=%0d sample=%0d got=%0d expected=%0d",cid,sent,dut.weighted_sample,weighted[sent]);sent++;
        end
        if(mvalid&&mready)begin
          assert(meta.first_timestamp==ts&&meta.sample_rate==32'(fs)&&meta.source_first_index==18'(src)&&meta.hann==1'(win))else $fatal(1,"SPECTRUM_METADATA");meta_count++;
        end
        if(bvalid&&bready)begin
          assert(meta_count==1&&bin_data.index==11'(received)&&bin_data.last==(received==1023))else $fatal(1,"SPECTRUM_ORDER");
          assert(($signed(bin_data.real_part)-gr[received]<=128)&&($signed(bin_data.real_part)-gr[received]>=-128)&&
            ($signed(bin_data.imag_part)-gi[received]<=128)&&($signed(bin_data.imag_part)-gi[received]>=-128))
            else $fatal(1,"SPECTRUM_DFT_MISMATCH case=%0d bin=%0d got=%0d,%0d gold=%0d,%0d",cid,received,bin_data.real_part,bin_data.imag_part,gr[received],gi[received]);
          actual_r={{32{bin_data.real_part[31]}},bin_data.real_part};actual_i={{32{bin_data.imag_part[31]}},bin_data.imag_part};
          p=64'(actual_r*actual_r+actual_i*actual_i);assert(bin_data.power==p)else $fatal(1,"SPECTRUM_POWER");
          $fdisplay(bin_file,"%0d,%0d,%0d,%0d,%0d",cid,received,bin_data.real_part,bin_data.imag_part,bin_data.power);received++;
        end
        if(rvalid&&rready)begin
          amp_error=32'(result.amplitude_q16)-ea;rms_error=32'(result.rms_q16)-er;
          assert(sent==1024&&received==1024&&result.measurement_valid==1'(ev)&&result.peak_bin==11'(ep)&&result.frequency_hz==32'(ef)&&result.clipped==1'(eo))
            else $fatal(1,"SPECTRUM_RESULT case=%0d valid=%0d/%0d bin=%0d/%0d freq=%0d/%0d otr=%0d/%0d",cid,result.measurement_valid,ev,result.peak_bin,ep,result.frequency_hz,ef,result.clipped,eo);
          assert(amp_error<=8192&&amp_error>=-8192&&rms_error<=8192&&rms_error>=-8192&&$signed(result.dc_mean_q16)==ed)
            else $fatal(1,"SPECTRUM_AMPLITUDE case=%0d amp=%0d/%0d rms=%0d/%0d dc=%0d/%0d",cid,result.amplitude_q16,ea,result.rms_q16,er,result.dc_mean_q16,ed);
          $fdisplay(result_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cid,result.measurement_valid,result.peak_bin,result.frequency_hz,result.amplitude_q16,result.rms_q16,result.dc_mean_q16,result.clipped,result.peak_power);
          break;
        end
        @(negedge clk);if(accepted)svalid=0;
        cycles++;assert(cycles<100000)else $fatal(1,"SPECTRUM_CASE_TIMEOUT");
      end
      @(negedge clk);svalid=0;mready=0;bready=0;rready=0;case_count++;
      $display("SPECTRUM_CASE_PASS case=%0d window=%0d peak=%0d valid=%0d bins=1024",cid,win,ep,ev);
    end
    $fclose(cf);$fclose(bin_file);$fclose(result_file);
    $display("TEST_PASS tb_spectrum seed=%0d cases=%0d bins=%0d errors=0",seed,case_count,case_count*1024);$finish;
  end
endmodule
`default_nettype wire
