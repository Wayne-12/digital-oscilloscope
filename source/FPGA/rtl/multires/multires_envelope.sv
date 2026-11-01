`default_nettype none
// Single-clock, post-capture reduction. Caller keeps the source frame frozen
// until done/cancel drain. Exactly one read may be outstanding. Read response
// arrives no earlier than the clock AFTER the request handshake.
module multires_envelope(
  input wire logic clk,rst,module_enable,start,
  output wire logic start_ready,busy,
  input wire multires_pkg::frame_index_t cfg_sample_count,cfg_trigger_index,
  input wire logic [9:0] cfg_bucket_count,
  input wire logic [11:0] cfg_roi_count,
  input wire scope_pkg::sample_timestamp_t cfg_first_timestamp,
  input wire logic [31:0] cfg_sample_rate,
  output wire logic metadata_valid,
  input wire logic metadata_ready,
  output multires_pkg::envelope_metadata_t metadata,
  output logic bucket_valid,
  input wire logic bucket_ready,
  output multires_pkg::envelope_bucket_t bucket,
  output logic roi_valid,
  input wire logic roi_ready,
  output multires_pkg::envelope_roi_t roi,
  output wire logic sample_request,
  output wire multires_pkg::frame_index_t sample_index,
  input wire logic sample_ready,sample_valid,
  input wire scope_pkg::sample_word_t sample_word,
  output logic done,config_error,cancelled,
  output multires_pkg::frame_index_t consumed_samples
);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import multires_pkg::*;
  typedef enum logic [3:0] {IDLE,DIV_START,DIV_WAIT,HEADER,READ_REQUEST,READ_WAIT,DRAIN,ABORT_WAIT} state_t;
  state_t state;
  frame_index_t index,bucket_start,bucket_end,base_size,acc_count,min_index,max_index;
  logic [9:0] bucket_number,remainder_step,remainder_acc;
  logic [10:0] remainder_sum;
  adc_sample_t acc_min,acc_max,current_sample,next_min,next_max;
  frame_index_t next_min_index,next_max_index;
  logic acc_otr;
  wire logic [63:0] quotient,remainder;
  wire logic divider_busy,divider_done;
  logic [9:0] selected_buckets;
  frame_index_t selected_roi,centered_roi,selected_roi_start;
  wire logic config_valid=cfg_sample_count!=18'd0 && cfg_sample_count<=18'd16384 &&
    cfg_trigger_index<cfg_sample_count && cfg_bucket_count!=10'd0 && cfg_bucket_count<=10'd800 &&
    (cfg_roi_count==12'd0 || (cfg_roi_count>=12'd512 && cfg_roi_count<=12'd2048));
  assign start_ready=state==IDLE && module_enable && !rst;
  assign busy=state!=IDLE;
  assign metadata_valid=state==HEADER && module_enable && !rst;
  assign sample_request=state==READ_REQUEST && module_enable && !rst;
  assign sample_index=index;
  measure_udiv divider(.clk(clk),.rst(rst || !module_enable),.start(state==DIV_START),
    .dividend({46'd0,metadata.sample_count}),.divisor({54'd0,metadata.effective_buckets}),
    .busy(divider_busy),.done(divider_done),.quotient(quotient),.remainder(remainder));
  always_comb begin
    selected_buckets=cfg_sample_count<{8'd0,cfg_bucket_count}?cfg_sample_count[9:0]:cfg_bucket_count;
    selected_roi=cfg_sample_count<{6'd0,cfg_roi_count}?cfg_sample_count:{6'd0,cfg_roi_count};
    centered_roi=cfg_trigger_index>=(selected_roi>>1)?cfg_trigger_index-(selected_roi>>1):18'd0;
    selected_roi_start=centered_roi>cfg_sample_count-selected_roi?cfg_sample_count-selected_roi:centered_roi;
    if(cfg_roi_count==12'd0)begin selected_roi=0;selected_roi_start=0;end
    remainder_sum={1'b0,remainder_acc}+{1'b0,remainder_step};
    current_sample=adc_raw_to_signed(sample_word[11:0]);
    next_min=(acc_count==18'd0 || current_sample<acc_min)?current_sample:acc_min;
    next_max=(acc_count==18'd0 || current_sample>acc_max)?current_sample:acc_max;
    next_min_index=(acc_count==18'd0 || current_sample<acc_min)?index:min_index;
    next_max_index=(acc_count==18'd0 || current_sample>acc_max)?index:max_index;
  end
  // Assertions are active in behavioral simulation; parameter/config rejection
  // is a normal interface response and is tested separately without fatal.
  // translate_off
  always @(posedge clk)if(!rst)begin
    if(sample_valid)assert(state==READ_WAIT || state==ABORT_WAIT)else $fatal(1,"MULTIRES_RESPONSE_PROTOCOL_ASSERT");
    if(sample_request)assert(index<metadata.sample_count && index<18'd16384)
      else $fatal(1,"MULTIRES_READ_RANGE_ASSERT");
    if(state==READ_WAIT && sample_valid && module_enable)begin
      assert(!$isunknown(sample_word) && sample_word[14:12]==3'd0)else $fatal(1,"MULTIRES_SAMPLE_FORMAT_ASSERT");
      assert(bucket_start<=index && index<bucket_end && bucket_end<=metadata.sample_count && acc_count==index-bucket_start)
        else $fatal(1,"MULTIRES_ACCOUNTING_ASSERT");
    end
  end
  // translate_on
  always_ff @(posedge clk)begin
    if(rst)begin
      state<=IDLE;metadata<='0;bucket<='0;roi<='0;bucket_valid<=0;roi_valid<=0;
      done<=0;config_error<=0;cancelled<=0;consumed_samples<=0;
      index<=0;bucket_start<=0;bucket_end<=0;base_size<=0;acc_count<=0;min_index<=0;max_index<=0;
      bucket_number<=0;remainder_step<=0;remainder_acc<=0;acc_min<=0;acc_max<=0;acc_otr<=0;
    end else begin
      done<=0;config_error<=0;cancelled<=0;
      if(bucket_valid && bucket_ready)bucket_valid<=0;
      if(roi_valid && roi_ready)roi_valid<=0;
      if(state==ABORT_WAIT)begin
        if(sample_valid)state<=IDLE;
      end else if(!module_enable)begin
        if(state!=IDLE)cancelled<=1;
        bucket_valid<=0;roi_valid<=0;
        state<=(state==READ_WAIT && !sample_valid)?ABORT_WAIT:IDLE;
      end else case(state)
        IDLE:if(start)begin
          if(!config_valid)config_error<=1;
          else begin
            metadata.sample_count<=cfg_sample_count;metadata.trigger_index<=cfg_trigger_index;
            metadata.requested_buckets<=cfg_bucket_count;metadata.effective_buckets<=selected_buckets;
            metadata.roi_start<=selected_roi_start;metadata.roi_count<=selected_roi[11:0];
            metadata.roi_trigger_index<=cfg_roi_count==12'd0 ?12'd0:12'(cfg_trigger_index-selected_roi_start);
            metadata.first_timestamp<=cfg_first_timestamp;metadata.sample_rate<=cfg_sample_rate;
            consumed_samples<=0;index<=0;bucket_start<=0;bucket_number<=0;acc_count<=0;acc_min<=0;acc_max<=0;acc_otr<=0;min_index<=0;max_index<=0;
            state<=DIV_START;
          end
        end
        DIV_START:state<=DIV_WAIT;
        DIV_WAIT:if(divider_done)begin
          base_size<=quotient[17:0];bucket_end<=quotient[17:0];
          remainder_step<=remainder[9:0];remainder_acc<=remainder[9:0];state<=HEADER;
        end
        HEADER:if(metadata_ready)state<=READ_REQUEST;
        READ_REQUEST:if(sample_ready)state<=READ_WAIT;
        READ_WAIT:if(sample_valid)begin
          consumed_samples<=consumed_samples+18'd1;
          acc_min<=next_min;acc_max<=next_max;min_index<=next_min_index;max_index<=next_max_index;
          acc_count<=acc_count+18'd1;acc_otr<=acc_otr || sample_word[15];
          if(index>=metadata.roi_start && index<metadata.roi_start+{6'd0,metadata.roi_count})begin
            roi_valid<=1;roi.roi_index<=12'(index-metadata.roi_start);roi.frame_index<=index;
            roi.raw_word<=sample_word;roi.signed_sample<=current_sample;roi.timestamp<=metadata.first_timestamp+{46'd0,index};
          end
          if(index==bucket_end-18'd1)begin
            bucket_valid<=1;bucket.bucket_index<=bucket_number;bucket.first_index<=bucket_start;bucket.last_index<=index;
            bucket.sample_count<=acc_count+18'd1;bucket.minimum<=next_min;bucket.maximum<=next_max;
            bucket.minimum_index<=next_min_index;bucket.maximum_index<=next_max_index;bucket.otr<=acc_otr || sample_word[15];
            if(bucket_number!=metadata.effective_buckets-10'd1)begin
              bucket_number<=bucket_number+10'd1;bucket_start<=bucket_end;
              // floor((i+1)*N/B) via N=q*B+r; the extra sample is assigned
              // exactly when the accumulated remainder crosses B.
              if(remainder_sum>={1'b0,metadata.effective_buckets})begin
                bucket_end<=bucket_end+base_size+18'd1;
                remainder_acc<=10'(remainder_sum-{1'b0,metadata.effective_buckets});
              end else begin bucket_end<=bucket_end+base_size;remainder_acc<=remainder_sum[9:0];end
              acc_count<=0;acc_otr<=0;
            end
          end
          state<=DRAIN;
        end
        DRAIN:if((!bucket_valid || bucket_ready) && (!roi_valid || roi_ready))begin
          if(index==metadata.sample_count-18'd1)begin done<=1;state<=IDLE;end
          else begin index<=index+18'd1;state<=READ_REQUEST;end
        end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
`default_nettype wire
