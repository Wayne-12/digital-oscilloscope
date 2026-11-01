`default_nettype none
// A saturation sample is raw ADC code 0 or 4095. Each accepted word counts
// once. An event is a maximal consecutive run within this linear record;
// the last and first words are never joined. Backpressure does not split runs.
module frame_saturation_counter(
  input wire clk,clear,accept,
  input wire [11:0] raw_code,
  output logic [14:0] samples,saturated_samples,events
);
  timeunit 1ns;timeprecision 1ps;
  logic previous_saturated;
  wire saturated=(raw_code==12'd0 || raw_code==12'd4095);
  always_ff @(posedge clk)begin
    if(clear)begin samples<=0;saturated_samples<=0;events<=0;previous_saturated<=0;end
    else if(accept && samples<15'd16384)begin
      samples<=samples+1'b1;
      if(saturated)saturated_samples<=saturated_samples+1'b1;
      if(saturated && !previous_saturated)events<=events+1'b1;
      previous_saturated<=saturated;
    end
  end
endmodule
`default_nettype wire
