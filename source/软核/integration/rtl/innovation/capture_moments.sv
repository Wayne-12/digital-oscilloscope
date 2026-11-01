`default_nettype none
// Acquisition-domain full-frame integer summary; freeze after N accepted words.
// N<=16384; signed sum needs 29 bits and square sum 40 bits for ADC12.
// Use 64 bits, including headroom for the signed13 algorithm contract.
module capture_moments(
  input wire clk,rst,start,sample_valid,
  input wire [17:0] cfg_count,
  input wire [15:0] sample_word,
  input wire [63:0] sample_timestamp,
  output logic busy,done,error,
  output innovation_pkg::capture_moments_t result
);
  timeunit 1ns;timeprecision 1ps;
  logic signed [12:0] decoded;
  logic signed [63:0] x;
  logic [31:0] crc;
  logic [17:0] length;
  assign decoded=scope_pkg::adc_raw_to_signed(sample_word[11:0]);
  assign x=$signed({{51{decoded[12]}},decoded});
  always_ff @(posedge clk)begin
    if(rst)begin busy<=0;done<=0;error<=0;result<='0;crc<=32'hffffffff;length<=0;end
    else begin
      done<=0;
      if(start && !busy)begin
        result<='0;result.minimum<=13'sd4095;result.maximum<=-13'sd4096;crc<=32'hffffffff;
        error<=cfg_count==0 || cfg_count>18'd16384;busy<=cfg_count!=0 && cfg_count<=18'd16384;length<=cfg_count;
      end else if(sample_valid && busy)begin
        result.count<=result.count+18'd1;result.sum<=result.sum+x;result.square_sum<=result.square_sum+64'(x*x);
        result.otr_count<=result.otr_count+{17'd0,sample_word[15]};
        if(decoded<result.minimum)result.minimum<=decoded;if(decoded>result.maximum)result.maximum<=decoded;
        if(result.count==0)result.first_timestamp<=sample_timestamp;
        result.last_timestamp<=sample_timestamp;crc<=scope_pkg::crc32_word(crc,sample_word);
        if(result.count==length-18'd1)begin result.raw_crc32<=~scope_pkg::crc32_word(crc,sample_word);busy<=0;done<=1;end
        // translate_off
        assert(sample_word[14:12]==0 && (result.count==0 || sample_timestamp==result.last_timestamp+64'd1))else $fatal(1,"INNOVATION_MOMENTS_SAMPLE");
        // translate_on
      end
    end
  end
endmodule
`default_nettype wire
