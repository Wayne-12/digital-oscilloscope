`default_nettype none
module measurement_core (
  input wire logic clk,rst,start,
  input wire logic [17:0] frame_length,
  input wire logic [31:0] sample_rate_hz,
  input wire scope_pkg::adc_sample_t threshold,
  input wire logic [12:0] hysteresis,
  input wire logic sample_valid,
  input wire scope_pkg::adc_sample_t sample_signed,
  input wire scope_pkg::sample_timestamp_t sample_timestamp,
  output wire logic sample_ready,busy,
  output logic measurement_done,measurement_valid,measurement_error,
  output scope_pkg::measurement_result_t result
);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  typedef enum logic [2:0] {IDLE,ACQUIRE,DIV_START,DIV_WAIT,SQRT,FINISH} state_t;
  state_t state;
  logic [17:0] length_reg,count,periods;
  logic [31:0] rate_reg;
  adc_sample_t threshold_reg,min_reg,max_reg;
  logic [12:0] hyst_reg;
  logic signed [63:0] sum_reg,x64;
  logic [63:0] square_sum,elapsed_sum,high_sum,previous_ts,last_rise,last_fall;
  logic have_previous,known_level,high_level_state,have_rise,have_fall,time_ok;
  logic signed [14:0] low_level,high_level,x;
  logic rise,fall;
  logic [2:0] operation;
  logic [63:0] numerator,denominator,quotient,remainder,rounded,mean_square;
  wire logic divider_done,divider_busy;
  logic [13:0] root,candidate,accepted_root;
  logic [3:0] sqrt_bit;
  logic [27:0] candidate_square;
  logic [63:0] rounding_boundary;
  assign sample_ready=state==ACQUIRE;
  assign busy=state!=IDLE;
  always_comb begin
    x=$signed({{2{sample_signed[12]}},sample_signed});
    x64=$signed({{51{sample_signed[12]}},sample_signed});
    low_level=$signed({{2{threshold_reg[12]}},threshold_reg})-$signed({2'b00,hyst_reg});
    high_level=$signed({{2{threshold_reg[12]}},threshold_reg})+$signed({2'b00,hyst_reg});
    rise=known_level && !high_level_state && x>high_level;
    fall=known_level && high_level_state && x<low_level;
    // All denominators are nonzero in their selected operation.
    numerator=64'd0;denominator={{46{1'b0}},length_reg};
    case(operation)
      3'd0: numerator=sum_reg<64'sd0 ?64'(-sum_reg):64'(sum_reg);
      3'd1: numerator=square_sum;
      3'd2: begin numerator=elapsed_sum<<16;denominator={{46{1'b0}},periods};end
      3'd3: begin numerator={{32{1'b0}},rate_reg}*{{46{1'b0}},periods};denominator=elapsed_sum;end
      3'd4: begin numerator=high_sum*64'd1000000;denominator=elapsed_sum;end
      default: numerator=64'd0;
    endcase
    rounded=quotient+((remainder>=(denominator>>1)+(denominator&64'd1))?64'd1:64'd0);
    candidate=root|(14'd1<<sqrt_bit);
    candidate_square=candidate*candidate;
    accepted_root={{36{1'b0}},candidate_square}<=mean_square?candidate:root;
    // Exact nearest sqrt: compare 4*S against N*(2*r+1)^2.
    rounding_boundary={{46{1'b0}},length_reg}*
      (64'd4*{{50{1'b0}},accepted_root}*{{50{1'b0}},accepted_root}+64'd4*{{50{1'b0}},accepted_root}+64'd1);
  end
  measure_udiv divider(.clk(clk),.rst(rst),.start(state==DIV_START),.dividend(numerator),.divisor(denominator),
    .busy(divider_busy),.done(divider_done),.quotient(quotient),.remainder(remainder));
  always_ff @(posedge clk)begin
    if(rst)begin
      state<=IDLE;measurement_done<=1'b0;measurement_valid<=1'b0;measurement_error<=1'b0;result<='0;
      length_reg<=18'd0;count<=18'd0;periods<=18'd0;rate_reg<=32'd0;
      threshold_reg<=13'sd0;hyst_reg<=13'd0;min_reg<=13'sd0;max_reg<=13'sd0;
      sum_reg<=64'sd0;square_sum<=64'd0;elapsed_sum<=64'd0;high_sum<=64'd0;
      previous_ts<=64'd0;last_rise<=64'd0;last_fall<=64'd0;
      have_previous<=1'b0;known_level<=1'b0;high_level_state<=1'b0;have_rise<=1'b0;have_fall<=1'b0;time_ok<=1'b1;
      operation<=3'd0;mean_square<=64'd0;root<=14'd0;sqrt_bit<=4'd0;
    end else begin
      measurement_done<=1'b0;
      case(state)
        IDLE: if(start)begin
          result<='0;measurement_valid<=1'b0;measurement_error<=1'b0;
          if(frame_length==18'd0 || frame_length>18'd16384 || sample_rate_hz==32'd0)begin
            measurement_done<=1'b1;measurement_error<=1'b1;
          end else begin
            state<=ACQUIRE;length_reg<=frame_length;rate_reg<=sample_rate_hz;threshold_reg<=threshold;hyst_reg<=hysteresis;
            count<=18'd0;periods<=18'd0;sum_reg<=64'sd0;square_sum<=64'd0;elapsed_sum<=64'd0;high_sum<=64'd0;
            min_reg<=13'sd4095;max_reg<=13'sh1000;have_previous<=1'b0;
            known_level<=1'b0;high_level_state<=1'b0;have_rise<=1'b0;have_fall<=1'b0;time_ok<=1'b1;
          end
        end
        ACQUIRE: if(sample_valid)begin
          count<=count+18'd1;sum_reg<=sum_reg+x64;square_sum<=square_sum+64'(x64*x64);
          if(sample_signed<min_reg)min_reg<=sample_signed;
          if(sample_signed>max_reg)max_reg<=sample_signed;
          have_previous<=1'b1;previous_ts<=sample_timestamp;
          if(have_previous && sample_timestamp!=previous_ts+64'd1)begin time_ok<=1'b0;measurement_error<=1'b1;end
          if(!known_level)begin
            if(x<=low_level)begin known_level<=1'b1;high_level_state<=1'b0;end
            else if(x>=high_level)begin known_level<=1'b1;high_level_state<=1'b1;end
          end else if(rise)begin
            high_level_state<=1'b1;
            if(have_rise && have_fall)begin
              periods<=periods+18'd1;elapsed_sum<=elapsed_sum+(sample_timestamp-last_rise);
              high_sum<=high_sum+(last_fall-last_rise);
            end
            have_rise<=1'b1;have_fall<=1'b0;last_rise<=sample_timestamp;
          end else if(fall)begin high_level_state<=1'b0;last_fall<=sample_timestamp;have_fall<=have_rise;end
          if(count==length_reg-18'd1)begin state<=DIV_START;operation<=3'd0;end
        end
        DIV_START: state<=DIV_WAIT;
        DIV_WAIT: if(divider_done)begin
          case(operation)
            3'd0: begin result.mean<=13'(sum_reg<64'sd0 ?-$signed(rounded):$signed(rounded));operation<=3'd1;state<=DIV_START;end
            3'd1: begin mean_square<=quotient;root<=14'd0;sqrt_bit<=4'd13;state<=SQRT;end
            3'd2: begin result.period_q16<=rounded;operation<=3'd3;state<=DIV_START;end
            3'd3: begin result.frequency_hz<=32'(rounded);operation<=3'd4;state<=DIV_START;end
            3'd4: begin result.duty_ppm<=32'(rounded);state<=FINISH;end
            default: state<=FINISH;
          endcase
        end
        SQRT: begin
          root<=accepted_root;
          if(sqrt_bit==4'd0)begin
            result.rms<=accepted_root+((square_sum<<2)>=rounding_boundary?14'd1:14'd0);
            if(periods!=18'd0 && time_ok && elapsed_sum!=64'd0)begin operation<=3'd2;state<=DIV_START;end
            else state<=FINISH;
          end else sqrt_bit<=sqrt_bit-4'd1;
        end
        FINISH: begin
          result.stats_valid<=1'b1;result.minimum<=min_reg;result.maximum<=max_reg;
          result.peak_to_peak<=14'($signed({max_reg[12],max_reg})-$signed({min_reg[12],min_reg}));
          result.sample_count<=count;result.sum<=sum_reg;result.square_sum<=square_sum;
          result.period_count<=time_ok?periods:18'd0;
          result.period_valid<=time_ok && periods!=18'd0;result.duty_valid<=time_ok && periods!=18'd0;
          measurement_valid<=time_ok && periods!=18'd0;measurement_done<=1'b1;state<=IDLE;
        end
        default: begin state<=IDLE;measurement_error<=1'b1;end
      endcase
    end
  end
endmodule
`default_nettype wire

