`default_nettype none
module tb_innovation_health;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import innovation_pkg::*;import spectrum_pkg::*;
  logic clk=0,adc_clk=0;always #5ns clk=~clk;always #50ns adc_clk=~adc_clk;
  logic rst=1,model_rst=1,enable=0,capture_enable=0,force_otr=0;
  dds_wave_t mode=DDS_DC;logic [15:0] amp=0;logic signed [17:0] dc=0;logic [31:0] noise_seed=1;
  wire [13:0] dds_code,dac_input,dac_code;wire [31:0] phase;wire dds_valid,dac_iv,dac_valid;integer unsigned accepted;
  dds_core dds(.clk_dac(adc_clk),.rst(model_rst),.enable(enable),.waveform(mode),.phase_inc(32'h01000000),.phase_offset(32'd0),.amplitude(amp),.dc_offset(dc),.dac_code(dds_code),.sample_phase(phase),.sample_valid(dds_valid));
  ad9767_model dac(.rst(model_rst),.bus_enable(enable),.aclk(adc_clk),.wr1(adc_clk),.bclk(1'b0),.wr2(1'b0),.da(dds_code),.input_code(dac_input),.dac_code(dac_code),.input_valid(dac_iv),.dac_valid(dac_valid),.accepted_edges(accepted));
  wire [11:0] raw[0:7];wire signed [12:0] signed_sample[0:7];wire [63:0] timestamp[0:7];wire [7:0] cap_valid,otr;
  logic fit_start=0,point_valid=0;logic signed [13:0] point_x=0;logic signed [31:0] point_y[0:7];
  wire [7:0] fit_ready,point_ready,fit_done,fit_valid,fit_error;
  wire signed [31:0] fitted_gain[0:7],fitted_offset[0:7],correction[0:7];
  for(genvar p=0;p<8;p++)begin:profiles
    localparam integer G=p==2?19661:p==6?12288:p==7?24576:16384;
    localparam integer OFF=p==1?32:p==6?-37:p==7?91:0;
    localparam integer NOISE=p==3?12:p==6?2:p==7?0:1;
    wire signed [31:0] channel_sample;wire channel_valid,channel_clip,fe,fv,av;wire [11:0] adc_raw;wire adc_otr;
    loopback_channel_model #(.GAIN_Q16(G),.INVERT(p==6),.OFFSET_LSB(OFF),.NOISE_LSB(NOISE),.CLIP_ENABLE(p==4),.CLIP_LOW(-700),.CLIP_HIGH(700),.ODD_Q16(p==5?16384:0)) channel(
      .clk_sample(adc_clk),.rst(model_rst),.dac_code(dac_code),.dac_valid(dac_valid),.noise_seed(noise_seed),.force_otr_enable(force_otr),.force_otr_value(1'b1),
      .ideal_sample(channel_sample),.sample_valid(channel_valid),.channel_clipped(channel_clip),.adc_force_otr_enable(fe),.adc_force_otr_value(fv));
    ad9226_model #(.T_CO_NS(p%2==0?3.5:7.0)) adc(.adc_clk(adc_clk),.rst(model_rst),.ideal_sample(channel_sample),.noise_seed(32'd1),.force_otr_enable(fe),.force_otr_value(fv),.raw_code(adc_raw),.otr(adc_otr),.output_valid(av));
    adc_capture capture(.clk_sample(adc_clk),.rst(model_rst),.capture_enable(capture_enable),.adc_data(adc_raw),.adc_otr(adc_otr),.sample_valid(cap_valid[p]),.sample_raw(raw[p]),.sample_signed(signed_sample[p]),.sample_otr(otr[p]),.sample_timestamp(timestamp[p]));
    relative_calibrator calibrator(.clk(clk),.rst(rst),.module_enable(1'b1),.start(fit_start),.cfg_points(6'd9),.cfg_nominal_gain_q20(32'd262144),.start_ready(fit_ready[p]),.point_ready(point_ready[p]),
      .point_valid(point_valid),.point_x(point_x),.point_mean_q16(point_y[p]),.done(fit_done[p]),.fit_valid(fit_valid[p]),.fit_error(fit_error[p]),.gain_q20(fitted_gain[p]),.offset_q16(fitted_offset[p]),.correction_q20(correction[p]));
  end
  logic fft_start=0,fft_sv=0,fft_sl=0,fft_otr=0;logic signed [12:0] fft_x=0;logic [63:0] fft_ts=0,fft_first=0;
  wire fft_ready,fft_sr,fmv,fbv,frv,fft_error,fft_cancel;
  spectrum_metadata_t fm;spectrum_bin_t fb;spectrum_result_t fr;
  spectrum_analyzer spectrum(.clk(clk),.rst(rst),.module_enable(1'b1),.start(fft_start),.start_ready(fft_ready),.cfg_hann(1'b0),.cfg_sample_rate(32'd10000000),.cfg_first_timestamp(fft_first),.cfg_source_first_index(18'd0),.cfg_threshold_q16(32'd131072),
    .sample_valid(fft_sv),.sample_ready(fft_sr),.sample_signed(fft_x),.sample_otr(fft_otr),.sample_timestamp(fft_ts),.sample_last(fft_sl),.metadata_valid(fmv),.metadata_ready(1'b1),.metadata(fm),
    .bin_valid(fbv),.bin_ready(1'b1),.bin_data(fb),.result_valid(frv),.result_ready(1'b1),.result(fr),.config_error(fft_error),.cancelled(fft_cancel));
  logic apply_valid=0;wire apply_ready,apply_out;logic [15:0] apply_word=0;logic [63:0] apply_ts=0;logic signed [31:0] apply_off=0,apply_corr=0;
  wire [15:0] out_word;wire [63:0] out_ts;wire signed [31:0] out_display;wire applied,saturated;
  calibration_apply display_branch(.clk(clk),.rst(rst),.module_enable(1'b1),.in_valid(apply_valid),.in_ready(apply_ready),.in_raw_word(apply_word),.in_timestamp(apply_ts),.calibration_valid(1'b1),.correction_q20(apply_corr),.offset_q16(apply_off),
    .out_valid(apply_out),.out_ready(1'b1),.out_raw_word(out_word),.out_timestamp(out_ts),.display_q16(out_display),.corrected(applied),.saturated(saturated));
  health_fingerprint_t fingerprints[0:7],base,current;health_limits_t limits;
  logic health_valid=0;wire health_ready,health_out;wire [6:0] alarms;health_class_t classification;
  health_compare monitor(.clk(clk),.rst(rst),.module_enable(1'b1),.in_valid(health_valid),.in_ready(health_ready),.baseline(base),.current(current),.limits(limits),.out_valid(health_out),.out_ready(1'b1),.alarms(alarms),.classification(classification));
  logic [15:0] saved[0:7][0:4095],forced[0:7][0:255];logic [63:0] saved_ts[0:7][0:4095],forced_ts[0:7][0:255];
  longint signed zero_sum[0:7],zero_square[0:7],sums[0:7],tmp,den,loss,expected_p2p;
  integer minimum[0:7],maximum[0:7],last_p2p[0:7],amp_list[0:5];
  logic [63:0] fundamental,second_power,third_power;
  integer seed=20261020,unused,trace_file,fit_file,feature_file,bin_file,apply_file,sent,bin_count,total_samples=0,corrected_samples=0;
  logic accepted_in;string vectors;
  function automatic longint signed round_div(input longint signed x,input longint signed d);return x<0 ? -((-x+d/2)/d):(x+d/2)/d;endfunction
  task automatic stimulus(input integer stage,input integer item,input integer length,input integer amplitude,input integer offset_code,input bit force_bit);
    @(posedge adc_clk);#2ns;model_rst=1;enable=0;capture_enable=0;force_otr=force_bit;
    repeat(4)@(posedge adc_clk);#2ns;
    mode=stage==2?DDS_SINE:DDS_DC;amp=16'(amplitude);dc=18'(offset_code);noise_seed=32'(seed)^(32'(stage)<<24)^(32'(item)*32'h9e3779b9);model_rst=0;enable=1;capture_enable=1;
    repeat(128)@(posedge adc_clk);
    for(integer p=0;p<8;p++)begin sums[p]=0;minimum[p]=2048;maximum[p]=-2049;end
    for(integer i=0;i<length;i++)begin
      @(posedge adc_clk);#2ps;
      for(integer p=0;p<8;p++)begin
        assert(cap_valid[p] && signed_sample[p]==adc_raw_to_signed(raw[p]))else $fatal(1,"HEALTH_RAW_SIGNED");
        sums[p]+=longint'(signed_sample[p]);if(signed_sample[p]<minimum[p])minimum[p]=integer'(signed_sample[p]);if(signed_sample[p]>maximum[p])maximum[p]=integer'(signed_sample[p]);
        if(stage==0)begin zero_sum[p]+=longint'(signed_sample[p]);zero_square[p]+=longint'(signed_sample[p])*longint'(signed_sample[p]);end
        if(stage==2&&item==5)begin saved[p][i]={otr[p],3'd0,raw[p]};saved_ts[p][i]=timestamp[p];end
        if(stage==3)begin forced[p][i]={otr[p],3'd0,raw[p]};forced_ts[p][i]=timestamp[p];assert(otr[p])else $fatal(1,"HEALTH_FORCED_OTR");end
        $fdisplay(trace_file,"%0d,%0d,%0d,%0d,%0d,%0d,%016x",p,stage,item,i,raw[p],otr[p],timestamp[p]);total_samples++;
      end
    end
  endtask
  initial begin #100ms;$fatal(1,"HEALTH_WATCHDOG");end
  initial begin
    unused=$value$plusargs("SEED=%d",seed);limits='0;base='0;current='0;
    limits.zero_limit_q16=262144;limits.gain_limit_q20=10486;limits.noise_rise_limit_q16=262144;limits.compression_limit_ppm=50000;limits.harmonic_limit_ppm=100;
    trace_file=$fopen("health_raw.csv","w");fit_file=$fopen("health_fits.csv","w");feature_file=$fopen("health_features.csv","w");bin_file=$fopen("health_fft.csv","w");apply_file=$fopen("health_display.csv","w");
    $fdisplay(trace_file,"profile,stage,item,index,raw,otr,timestamp");$fdisplay(fit_file,"profile,gain_q20,offset_q16,correction_q20");
    $fdisplay(feature_file,"profile,gain,offset,noise,compression,harmonic,otr,alarms,classification");$fdisplay(bin_file,"profile,bin,real,imag,power");$fdisplay(apply_file,"profile,kind,index,word,timestamp,display_q16");
    for(integer p=0;p<8;p++)begin zero_sum[p]=0;zero_square[p]=0;point_y[p]=0;fingerprints[p]='0;last_p2p[p]=0;end
    amp_list[0]=256;amp_list[1]=512;amp_list[2]=1024;amp_list[3]=2048;amp_list[4]=3072;amp_list[5]=4096;
    repeat(8)@(negedge clk);rst=0;
    for(integer f=0;f<4;f++)stimulus(0,f,256,0,0,0);
    wait(&fit_ready);@(negedge clk);fit_start=1;@(negedge clk);fit_start=0;
    for(integer level=0;level<9;level++)begin
      stimulus(1,level,2048,0,(level-4)*512,0);
      @(negedge clk);point_x=14'((level-4)*512);for(integer p=0;p<8;p++)point_y[p]=32'(round_div(sums[p]*65536,2048));
      wait(&point_ready);point_valid=1;@(negedge clk);point_valid=0;
    end
    wait(&fit_done);@(negedge clk);assert((&fit_valid)&&fit_error==0)else $fatal(1,"HEALTH_FIT_STATUS");
    for(integer p=0;p<8;p++)$fdisplay(fit_file,"%0d,%0d,%0d,%0d",p,fitted_gain[p],fitted_offset[p],correction[p]);
    for(integer a=0;a<6;a++)begin
      stimulus(2,a,4096,amp_list[a],0,0);
      for(integer p=0;p<8;p++)begin assert(maximum[p]-minimum[p]>=last_p2p[p])else $fatal(1,"HEALTH_AMPLITUDE_MONOTONIC");last_p2p[p]=maximum[p]-minimum[p];end
    end
    @(posedge adc_clk);#2ns;enable=0;capture_enable=0;model_rst=1;
    for(integer p=0;p<8;p++)begin
      wait(fft_ready);@(negedge clk);fft_first=saved_ts[p][0];fft_start=1;@(negedge clk);fft_start=0;sent=0;bin_count=0;fundamental=0;second_power=0;third_power=0;
      while(!frv)begin
        fft_sv=sent<1024;if(sent<1024)begin fft_x=adc_raw_to_signed(saved[p][sent][11:0]);fft_otr=saved[p][sent][15];fft_ts=saved_ts[p][sent];fft_sl=sent==1023;end
        @(posedge clk);accepted_in=fft_sv&&fft_sr;if(accepted_in)sent++;
        if(fbv)begin
          assert(fb.index==11'(bin_count))else $fatal(1,"HEALTH_FFT_ORDER");$fdisplay(bin_file,"%0d,%0d,%0d,%0d,%0d",p,bin_count,fb.real_part,fb.imag_part,fb.power);
          if(bin_count==4)fundamental=fb.power;if(bin_count==8)second_power=fb.power;if(bin_count==12)third_power=fb.power;bin_count++;
        end
        @(negedge clk);
      end
      fft_sv=0;assert(bin_count==1024&&fr.measurement_valid&&fr.peak_bin==11'd4&&!fft_error&&!fft_cancel&&fundamental!=0)else $fatal(1,"HEALTH_FFT_RESULT");
      fingerprints[p].valid=fit_valid[p];fingerprints[p].gain_q20=fitted_gain[p];fingerprints[p].offset_q16=fitted_offset[p];
      tmp=(1024*zero_square[p]-zero_sum[p]*zero_sum[p])*65536;fingerprints[p].zero_variance_q16=64'(round_div(tmp,1048576));
      expected_p2p=(fitted_gain[p]<0 ? -longint'(fitted_gain[p]):longint'(fitted_gain[p]))*8192;
      loss=expected_p2p-longint'(last_p2p[p])*1048576;
      fingerprints[p].compression_loss_ppm=loss>0 ?32'(round_div(loss*1000000,expected_p2p)):32'd0;
      fingerprints[p].harmonic_power_ppm=32'(((second_power+third_power)*64'd1000000+fundamental/2)/fundamental);
      for(integer i=0;i<4096;i++)if(saved[p][i][15])fingerprints[p].otr_count++;
    end
    // Snapshot learned baseline, then change exactly one channel parameter in profiles 1..5.
    for(integer p=0;p<8;p++)begin
      @(negedge clk);base=p==7?fingerprints[7]:fingerprints[0];current=fingerprints[p];health_valid=1;
      wait(health_ready);@(negedge clk);health_valid=0;assert(health_out)else $fatal(1,"HEALTH_MONITOR_VALID");
      assert(classification==health_class_t'(4'(p==7?0:p)))else $fatal(1,"HEALTH_CLASSIFICATION profile=%0d kind=%0d alarms=%h",p,classification,alarms);
      $fdisplay(feature_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",p,current.gain_q20,current.offset_q16,current.zero_variance_q16,current.compression_loss_ppm,current.harmonic_power_ppm,current.otr_count,alarms,classification);
    end
    stimulus(3,0,256,0,0,1);@(posedge adc_clk);#2ns;model_rst=1;enable=0;capture_enable=0;force_otr=0;
    for(integer p=0;p<8;p++)begin
      for(integer k=0;k<2;k++)begin
        for(integer i=0;i<(k==0?4096:256);i++)begin
          @(negedge clk);apply_word=k==0?saved[p][i]:forced[p][i];apply_ts=k==0?saved_ts[p][i]:forced_ts[p][i];apply_off=fitted_offset[p];apply_corr=correction[p];apply_valid=1;
          wait(apply_ready);@(negedge clk);apply_valid=0;
          assert(apply_out&&out_word==apply_word&&out_ts==apply_ts&&applied&&!saturated)else $fatal(1,"HEALTH_RAW_PRESERVATION");
          $fdisplay(apply_file,"%0d,%0d,%0d,%04x,%016x,%0d",p,k,i,out_word,out_ts,out_display);corrected_samples++;
        end
      end
    end
    $fclose(trace_file);$fclose(fit_file);$fclose(feature_file);$fclose(bin_file);$fclose(apply_file);
    $display("TEST_PASS tb_innovation_health seed=%0d profiles=8 raw=%0d corrected=%0d fft_bins=8192 errors=0",seed,total_samples,corrected_samples);$finish;
  end
endmodule
`default_nettype wire
