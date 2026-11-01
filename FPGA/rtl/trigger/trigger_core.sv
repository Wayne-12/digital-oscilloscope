`default_nettype none
module trigger_core (
  input wire logic clk, rst, enable, sample_valid,
  input wire scope_pkg::trigger_config_t config_in,
  input wire scope_pkg::adc_sample_t sample_signed,
  input wire logic sample_otr,
  input wire scope_pkg::sample_timestamp_t sample_timestamp,
  output logic trigger_hit,
  output wire logic config_error,
  output logic timestamp_error
);
  timeunit 1ns; timeprecision 1ps;
  import scope_pkg::*;
  logic qualified, level_known, level_high, pulse_active, otr_previous;
  logic have_previous;
  sample_timestamp_t previous_timestamp, pulse_start;
  logic [14:0] block_count;
  adc_sample_t block_min, block_max;
  logic signed [14:0] x,lo,hi,h,wl,wh;
  adc_sample_t next_min,next_max;
  logic [13:0] span;
  logic [63:0] pulse_width;
  logic rising_cross, falling_cross, gap;
  assign config_error=!trigger_config_valid(config_in);
  always_comb begin
    x=$signed({{2{sample_signed[12]}},sample_signed});
    h=$signed({2'b00,config_in.hysteresis});
    lo=$signed({{2{config_in.threshold[12]}},config_in.threshold})-h;
    hi=$signed({{2{config_in.threshold[12]}},config_in.threshold})+h;
    wl=$signed({{2{config_in.window_low[12]}},config_in.window_low});
    wh=$signed({{2{config_in.window_high[12]}},config_in.window_high});
    gap=have_previous && sample_timestamp!=previous_timestamp+64'd1;
    rising_cross=level_known && !level_high && x>hi;
    falling_cross=level_known && level_high && x<lo;
    next_min=(block_count==15'd0 || sample_signed<block_min)?sample_signed:block_min;
    next_max=(block_count==15'd0 || sample_signed>block_max)?sample_signed:block_max;
    span=14'($signed({next_max[12],next_max})-$signed({next_min[12],next_min}));
    pulse_width=sample_timestamp-pulse_start;
    trigger_hit=1'b0;
    if(!rst && enable && sample_valid && !config_error && !gap)begin
      case(config_in.kind)
        TRIG_RISE: trigger_hit=qualified && x>hi;
        TRIG_FALL: trigger_hit=qualified && x<lo;
        TRIG_WINDOW_ENTER: trigger_hit=qualified && x>wl+h && x<wh-h;
        TRIG_WINDOW_LEAVE: trigger_hit=qualified && (x<wl-h || x>wh+h);
        TRIG_POS_WIDTH,TRIG_NEG_WIDTH:
          trigger_hit=pulse_active && (config_in.kind==TRIG_POS_WIDTH?falling_cross:rising_cross) &&
            pulse_width>={{32{1'b0}},config_in.width_min} && pulse_width<={{32{1'b0}},config_in.width_max};
        TRIG_UNDER_AMPLITUDE,TRIG_OVER_AMPLITUDE:
          if(block_count==config_in.observation_samples-15'd1)
            trigger_hit=config_in.kind==TRIG_UNDER_AMPLITUDE?span<config_in.amplitude_limit:span>config_in.amplitude_limit;
        TRIG_OTR: trigger_hit=sample_otr && !otr_previous;
        default: trigger_hit=1'b0;
      endcase
    end
  end
  // Configuration must remain stable while enable=1; capture wrapper latches it.
  // Timestamp gaps suppress the current hit and flush all temporal qualification.
  always_ff @(posedge clk)begin
    if(rst || !enable || config_error)begin
      qualified<=1'b0;level_known<=1'b0;level_high<=1'b0;pulse_active<=1'b0;
      otr_previous<=1'b0;have_previous<=1'b0;previous_timestamp<=64'd0;
      pulse_start<=64'd0;block_count<=15'd0;block_min<=13'sd0;block_max<=13'sd0;
      timestamp_error<=1'b0;
    end else if(sample_valid)begin
      have_previous<=1'b1;previous_timestamp<=sample_timestamp;
      if(gap)begin
        qualified<=1'b0;level_known<=1'b0;level_high<=1'b0;pulse_active<=1'b0;
        otr_previous<=1'b0;block_count<=15'd0;timestamp_error<=1'b1;
      end else begin
        otr_previous<=sample_otr;
        if(!level_known)begin
          if(x<=lo)begin level_known<=1'b1;level_high<=1'b0;end
          else if(x>=hi)begin level_known<=1'b1;level_high<=1'b1;end
        end else if(rising_cross || falling_cross)begin
          level_high<=rising_cross;
          if(config_in.kind==TRIG_POS_WIDTH?rising_cross:falling_cross)begin
            pulse_active<=1'b1;pulse_start<=sample_timestamp;
          end else pulse_active<=1'b0;
        end
        if(trigger_hit)qualified<=1'b0;
        else case(config_in.kind)
          TRIG_RISE: if(x<=lo)qualified<=1'b1;
          TRIG_FALL: if(x>=hi)qualified<=1'b1;
          TRIG_WINDOW_ENTER: if(x<=wl-h || x>=wh+h)qualified<=1'b1;
          TRIG_WINDOW_LEAVE: if(x>=wl+h && x<=wh-h)qualified<=1'b1;
          default: qualified<=1'b0;
        endcase
        if(config_in.kind==TRIG_UNDER_AMPLITUDE || config_in.kind==TRIG_OVER_AMPLITUDE)begin
          if(block_count==config_in.observation_samples-15'd1)block_count<=15'd0;
          else block_count<=block_count+15'd1;
          block_min<=next_min;block_max<=next_max;
        end
      end
    end
  end
endmodule
`default_nettype wire
