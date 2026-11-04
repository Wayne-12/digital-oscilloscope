`default_nettype none
// Frozen-frame reduction and compact UART packetization. The existing reducer
// scans BRAM once; only five bytes per bucket cross the serial link. Raw ROI
// requests use CMD_WAVE afterwards while this same frame remains frozen.
module protocol_envelope_tx(
  input wire logic clk,rst,request,cancel,
  input wire logic [9:0] request_buckets,
  input wire logic [15:0] request_sequence,
  input wire logic [63:0] first_timestamp,
  input wire logic [31:0] sample_rate,trigger_index,record_length,
  output wire logic request_ready,header_valid,payload_valid,
  output protocol_pkg::frame_header_t header,
  output logic [7:0] payload_data,
  input wire logic header_ready,payload_ready,packet_done,
  output wire logic sample_request,
  output wire logic [17:0] sample_index,
  input wire logic sample_ready,sample_valid,
  input wire logic [15:0] sample_word
);
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;
  import multires_pkg::*;
  typedef enum logic [2:0] {IDLE,START,WAIT_META,DESCRIPTOR,PREFIX,BUCKET,WAIT_PACKET} state_t;
  state_t state;
  logic [9:0] requested,offset,remaining,segment_count,position;
  logic [3:0] prefix_position;
  logic [2:0] bucket_byte;
  logic [15:0] seq;
  logic [31:0] total,rate_reg,trigger_reg;
  logic [63:0] timestamp_reg;
  logic cancel_pending;
  wire reducer_busy,reducer_ready,metadata_valid,bucket_valid;
  envelope_metadata_t metadata;
  envelope_bucket_t bucket;
  wire [9:0] next_segment=remaining>10'd202 ? 10'd202:remaining;
  wire bucket_ready=state==BUCKET && bucket_byte==3'd4 && payload_ready;
  assign request_ready=state==IDLE && !reducer_busy && !rst;
  assign header_valid=state==DESCRIPTOR && !rst;
  assign payload_valid=!rst && (state==PREFIX || (state==BUCKET && bucket_valid));
  multires_envelope reducer(.clk(clk),.rst(rst),.module_enable(state!=IDLE),
    .start(state==START && reducer_ready),.start_ready(reducer_ready),.busy(reducer_busy),
    .cfg_sample_count(total[17:0]),.cfg_trigger_index(trigger_reg[17:0]),
    .cfg_bucket_count(requested),.cfg_roi_count(12'd0),
    .cfg_first_timestamp(timestamp_reg),.cfg_sample_rate(rate_reg),
    .metadata_valid(metadata_valid),.metadata_ready(state==WAIT_META),.metadata(metadata),
    .bucket_valid(bucket_valid),.bucket_ready(bucket_ready),.bucket(bucket),
    .roi_valid(),.roi_ready(1'b1),.roi(),
    .sample_request(sample_request),.sample_index(sample_index),.sample_ready(sample_ready),
    .sample_valid(sample_valid),.sample_word(sample_word),
    .done(),.config_error(),.cancelled(),.consumed_samples());
  always_comb begin
    header='0;header.kind=CMD_ENVELOPE|8'h80;header.seq=seq;
    header.length=16'd12+16'(next_segment)*16'd5;
    header.timestamp=timestamp_reg;header.sample_rate=rate_reg;header.trigger_index=trigger_reg;
    header.flags=FLAG_RESPONSE|(offset==0?FLAG_FIRST:16'd0)|
      (remaining>10'd202 ? FLAG_MORE:FLAG_LAST);
    payload_data=0;
    if(state==PREFIX)begin
      case(prefix_position)
        0,1,2,3:payload_data=8'(32'(offset)>>(32'(prefix_position)*8));
        4,5,6,7:payload_data=8'(total>>(32'(prefix_position-4'd4)*8));
        8:payload_data=metadata.effective_buckets[7:0];
        9:payload_data={6'd0,metadata.effective_buckets[9:8]};
        10:payload_data=8'd1; // encoding 1: little-endian i16 min, i16 max, u8 OTR
        default:payload_data=0;
      endcase
    end else if(state==BUCKET)begin
      case(bucket_byte)
        0:payload_data=bucket.minimum[7:0];
        1:payload_data={{3{bucket.minimum[12]}},bucket.minimum[12:8]};
        2:payload_data=bucket.maximum[7:0];
        3:payload_data={{3{bucket.maximum[12]}},bucket.maximum[12:8]};
        4:payload_data={7'd0,bucket.otr};
        default:payload_data=0;
      endcase
    end
  end
  always_ff @(posedge clk)begin
    if(rst)begin
      state<=IDLE;requested<=0;offset<=0;remaining<=0;segment_count<=0;position<=0;
      prefix_position<=0;bucket_byte<=0;seq<=0;total<=0;rate_reg<=0;
      trigger_reg<=0;timestamp_reg<=0;cancel_pending<=0;
    end else begin
      if(cancel && state!=IDLE)cancel_pending<=1;
      // Before a packet is committed it is safe to cancel immediately. Once
      // committed, finish its declared payload/CRC, then abort the reduction.
      if(cancel && (state==START || state==WAIT_META || (state==DESCRIPTOR && !header_ready)))state<=IDLE;
      else case(state)
        IDLE:if(request && request_ready)begin
          requested<=request_buckets;seq<=request_sequence;total<=record_length;
          rate_reg<=sample_rate;trigger_reg<=trigger_index;timestamp_reg<=first_timestamp;
          offset<=0;cancel_pending<=0;state<=START;
        end
        START:if(reducer_ready)state<=WAIT_META;
        WAIT_META:if(metadata_valid)begin remaining<=metadata.effective_buckets;state<=DESCRIPTOR;end
        DESCRIPTOR:if(header_ready)begin segment_count<=next_segment;position<=0;prefix_position<=0;state<=PREFIX;end
        PREFIX:if(payload_ready)begin
          if(prefix_position==4'd11)begin bucket_byte<=0;state<=BUCKET;end
          else prefix_position<=prefix_position+4'd1;
        end
        BUCKET:if(bucket_valid && payload_ready)begin
          if(bucket_byte==3'd4)begin
            bucket_byte<=0;
            if(position==segment_count-10'd1)state<=WAIT_PACKET;
            else position<=position+10'd1;
          end else bucket_byte<=bucket_byte+3'd1;
        end
        WAIT_PACKET:if(packet_done)begin
          if(cancel_pending || cancel || remaining==segment_count)state<=IDLE;
          else begin offset<=offset+segment_count;remaining<=remaining-segment_count;seq<=seq+16'd1;state<=DESCRIPTOR;end
        end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
`default_nettype wire
