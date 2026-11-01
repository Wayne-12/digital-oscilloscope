`default_nettype none
module health_compare(
  input wire clk,rst,module_enable,in_valid,
  output wire in_ready,
  input innovation_pkg::health_fingerprint_t baseline,current,
  input innovation_pkg::health_limits_t limits,
  output logic out_valid,
  input wire out_ready,
  output logic [6:0] alarms,
  output innovation_pkg::health_class_t classification
);
  timeunit 1ns;timeprecision 1ps;
  import innovation_pkg::*;
  logic signed [32:0] offset_delta,gain_delta;
  logic [32:0] abs_offset,abs_gain,base_gain,new_gain;
  logic [6:0] flags;
  health_class_t selected;
  assign in_ready=module_enable && !rst && (!out_valid || out_ready);
  always_comb begin
    offset_delta=$signed({current.offset_q16[31],current.offset_q16})-$signed({baseline.offset_q16[31],baseline.offset_q16});
    abs_offset=offset_delta<0 ?33'(-offset_delta):33'(offset_delta);
    base_gain=baseline.gain_q20<0 ?33'(-$signed({baseline.gain_q20[31],baseline.gain_q20})):33'($signed({baseline.gain_q20[31],baseline.gain_q20}));
    new_gain=current.gain_q20<0 ?33'(-$signed({current.gain_q20[31],current.gain_q20})):33'($signed({current.gain_q20[31],current.gain_q20}));
    gain_delta=$signed(new_gain)-$signed(base_gain);abs_gain=gain_delta<0 ?33'(-gain_delta):33'(gain_delta);
    flags=0;
    flags[0]=abs_offset>{1'b0,limits.zero_limit_q16};
    flags[1]=abs_gain>{1'b0,limits.gain_limit_q20};
    flags[2]=current.zero_variance_q16>baseline.zero_variance_q16 && current.zero_variance_q16-baseline.zero_variance_q16>limits.noise_rise_limit_q16;
    flags[3]=(current.compression_loss_ppm>baseline.compression_loss_ppm && current.compression_loss_ppm-baseline.compression_loss_ppm>limits.compression_limit_ppm) ||
      (current.otr_count>baseline.otr_count && current.otr_count-baseline.otr_count>limits.otr_extra_limit);
    flags[4]=current.harmonic_power_ppm>baseline.harmonic_power_ppm && current.harmonic_power_ppm-baseline.harmonic_power_ppm>limits.harmonic_limit_ppm;
    flags[5]=current.gain_q20[31]!=baseline.gain_q20[31];
    flags[6]=!baseline.valid || !current.valid || baseline.gain_q20==0 || current.gain_q20==0;
    selected=HEALTH_OK;
    if(flags[6])selected=HEALTH_INVALID;else if(flags[5])selected=HEALTH_POLARITY;
    else if(flags[3])selected=HEALTH_CLIP;else if(flags[2])selected=HEALTH_NOISE;
    else if(flags[1])selected=HEALTH_GAIN;else if(flags[0])selected=HEALTH_ZERO;
    else if(flags[4])selected=HEALTH_HARMONIC;
  end
  always_ff @(posedge clk)begin
    if(rst)begin out_valid<=0;alarms<=0;classification<=HEALTH_INVALID;end
    else if(!module_enable)out_valid<=0;
    else begin
      if(out_valid && out_ready)out_valid<=0;
      if(in_valid && in_ready)begin out_valid<=1;alarms<=flags;classification<=selected;end
    end
  end
endmodule
`default_nettype wire
