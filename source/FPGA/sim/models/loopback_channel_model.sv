`default_nettype none
// Digital approximation only. ADC-clock falling-edge processing makes all
// outputs stable before the next ADC rising edge. rst is a verification flush.
module loopback_channel_model #(
  parameter int unsigned DELAY_SAMPLES=0,
  parameter int unsigned FRACTION_Q16=0,
  parameter int unsigned GAIN_Q16=16384,
  parameter bit INVERT=1'b0,
  parameter int signed OFFSET_LSB=0,
  parameter int unsigned NOISE_LSB=0,
  parameter bit CLIP_ENABLE=1'b0,
  parameter int signed CLIP_LOW=-2048, CLIP_HIGH=2047,
  parameter int unsigned LPF_ALPHA_Q16=65536,
  parameter int signed EVEN_Q16=0, ODD_Q16=0
)(
  input wire logic clk_sample, rst,
  input wire logic [13:0] dac_code,
  input wire logic dac_valid,
  input wire logic [31:0] noise_seed,
  input wire logic force_otr_enable, force_otr_value,
  output logic signed [31:0] ideal_sample,
  output logic sample_valid, channel_clipped,
  output logic adc_force_otr_enable, adc_force_otr_value
);
  timeunit 1ns;timeprecision 1ps;
  typedef logic signed [63:0] math_t;
  math_t history[0:DELAY_SAMPLES];
  math_t filter_q16;
  logic [31:0] noise_state;
  integer unsigned fill_count;
  function automatic math_t round_div(input math_t n,input math_t d);
    if(n<64'sd0)return -((-n+d/64'sd2)/d);
    return (n+d/64'sd2)/d;
  endfunction
  function automatic logic [31:0] advance(input logic [31:0] s);
    logic [31:0] t;
    t=s^(s<<32'd13);t=t^(t>>32'd17);return t^(t<<32'd5);
  endfunction
  initial begin
    assert(DELAY_SAMPLES<=64 && FRACTION_Q16<65536 && GAIN_Q16<=262144 &&
      OFFSET_LSB>=-1000000 && OFFSET_LSB<=1000000 && NOISE_LSB<=4096 &&
      LPF_ALPHA_Q16>=1 && LPF_ALPHA_Q16<=65536 &&
      EVEN_Q16>=-65536 && EVEN_Q16<=65536 && ODD_Q16>=-65536 && ODD_Q16<=65536 &&
      (!CLIP_ENABLE || CLIP_LOW<CLIP_HIGH))else $fatal(1,"TEST_FAIL invalid loopback configuration");
  end
  always @(negedge clk_sample)begin : channel_tick
    math_t x, current_delayed, previous_delayed, interpolated, even_term, odd_term;
    math_t distorted, gained, noise, biased, next_filter, filtered;
    logic [31:0] random_word;
    if(rst || !dac_valid)begin
      ideal_sample<=32'sd0;sample_valid<=1'b0;channel_clipped<=1'b0;
      adc_force_otr_enable<=1'b0;adc_force_otr_value<=1'b0;
      fill_count<=0;filter_q16<=64'sd0;
      noise_state<=(noise_seed==32'd0)?32'd1:noise_seed;
      for(integer i=0;i<=DELAY_SAMPLES;i++)history[i]<=64'sd0;
    end else begin
      assert(!$isunknown({dac_code,noise_seed,force_otr_enable,force_otr_value}))
        else $fatal(1,"TEST_FAIL unknown loopback input");
      x=math_t'($signed({1'b0,dac_code}))-64'sd8192;
      for(integer i=DELAY_SAMPLES;i>0;i--)history[i]<=history[i-1];
      history[0]<=x;
      if(fill_count<DELAY_SAMPLES+2)fill_count<=fill_count+1;
      if(fill_count>=DELAY_SAMPLES+((FRACTION_Q16!=0)?1:0))begin
        // history[0] is the previous tick. D=0 uses the current DAC value.
        if(DELAY_SAMPLES==0)current_delayed=x;
        else current_delayed=history[DELAY_SAMPLES-1];
        previous_delayed=history[DELAY_SAMPLES];
        interpolated=round_div((64'sd65536-math_t'(FRACTION_Q16))*current_delayed+
          math_t'(FRACTION_Q16)*previous_delayed,64'sd65536);
        // Weak polynomial perturbations add even/odd harmonics; they are not
        // a calibrated analog nonlinearity or a pure-harmonic signal source.
        even_term=round_div(math_t'(EVEN_Q16)*interpolated*interpolated,64'sd536870912);
        odd_term=round_div(math_t'(ODD_Q16)*interpolated*interpolated*interpolated,64'sd4398046511104);
        distorted=interpolated+even_term+odd_term;
        gained=round_div(distorted*math_t'(GAIN_Q16),64'sd65536);
        if(INVERT)gained=-gained;
        random_word=advance(noise_state);noise_state<=random_word;
        noise=math_t'(random_word%(32'd2*NOISE_LSB+32'd1))-math_t'(NOISE_LSB);
        biased=gained+math_t'(OFFSET_LSB)+noise;
        next_filter=filter_q16+round_div((biased*64'sd65536-filter_q16)*math_t'(LPF_ALPHA_Q16),64'sd65536);
        filter_q16<=next_filter;
        filtered=round_div(next_filter,64'sd65536);
        channel_clipped<=1'b0;
        if(CLIP_ENABLE && filtered<math_t'(CLIP_LOW))begin filtered=math_t'(CLIP_LOW);channel_clipped<=1'b1;end
        else if(CLIP_ENABLE && filtered>math_t'(CLIP_HIGH))begin filtered=math_t'(CLIP_HIGH);channel_clipped<=1'b1;end
        assert(filtered>=-64'sd2147483648 && filtered<=64'sd2147483647)
          else $fatal(1,"TEST_FAIL loopback signed32 overflow");
        ideal_sample<=32'(filtered);sample_valid<=1'b1;
        adc_force_otr_enable<=force_otr_enable;adc_force_otr_value<=force_otr_value;
      end else begin
        ideal_sample<=32'sd0;sample_valid<=1'b0;channel_clipped<=1'b0;
        adc_force_otr_enable<=1'b0;adc_force_otr_value<=1'b0;
      end
    end
  end
endmodule
`default_nettype wire
