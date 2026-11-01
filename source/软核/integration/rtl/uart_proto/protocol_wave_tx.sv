`default_nettype none
module protocol_wave_tx(
  input wire logic clk,rst,request,cancel,
  input wire logic [31:0] request_offset,request_count,
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
  typedef enum logic [3:0] {IDLE,DESCRIPTOR,PREFIX,READ_REQ,READ_WAIT,LOW_BYTE,HIGH_BYTE,WAIT_PACKET} state_t;
  state_t state;
  logic [31:0] offset,remaining,initial_offset,total;
  logic [63:0] timestamp_reg;
  logic [31:0] rate_reg,trigger_reg;
  logic [15:0] seq,segment_words,word_position,held_word;
  logic [2:0] prefix_position;
  logic cancel_pending;
  wire logic [15:0] next_segment=remaining>32'd508 ?16'd508:16'(remaining);
  assign request_ready=state==IDLE && !rst;
  assign header_valid=state==DESCRIPTOR && !rst;
  assign payload_valid=!rst && (state==PREFIX || state==LOW_BYTE || state==HIGH_BYTE);
  assign sample_request=state==READ_REQ && !rst;
  assign sample_index=18'(offset+32'(word_position));
  always_comb begin
    header='0;header.kind=CMD_WAVE|8'h80;header.seq=seq;header.length=16'd8+(next_segment<<1);
    header.timestamp=timestamp_reg+{32'd0,offset};header.sample_rate=rate_reg;header.trigger_index=trigger_reg;
    header.flags=FLAG_RESPONSE|(offset==initial_offset?FLAG_FIRST:16'd0)|(remaining>32'd508 ?FLAG_MORE:FLAG_LAST);
    if(state==PREFIX)payload_data=prefix_position<3'd4 ?8'(offset>>(32'(prefix_position)*8)):8'(total>>(32'(prefix_position-3'd4)*8));
    else if(state==LOW_BYTE)payload_data=held_word[7:0];else if(state==HIGH_BYTE)payload_data=held_word[15:8];else payload_data=0;
  end
  always_ff @(posedge clk)begin
    if(rst)begin state<=IDLE;offset<=0;remaining<=0;initial_offset<=0;total<=0;timestamp_reg<=0;rate_reg<=0;trigger_reg<=0;
      seq<=0;segment_words<=0;word_position<=0;held_word<=0;prefix_position<=0;cancel_pending<=0;end
    else begin
      if(cancel && state!=IDLE)cancel_pending<=1;
      if(cancel && state==DESCRIPTOR && !header_ready)state<=IDLE;
      else case(state)
        IDLE:if(request)begin
          // translate_off
          assert(request_count!=0 && {1'b0,request_offset}+{1'b0,request_count}<={1'b0,record_length} && record_length<=16384)
            else $fatal(1,"WAVE_REQUEST_RANGE_ASSERT");
          // translate_on
          offset<=request_offset;initial_offset<=request_offset;remaining<=request_count;total<=record_length;
          timestamp_reg<=first_timestamp;rate_reg<=sample_rate;trigger_reg<=trigger_index;seq<=request_sequence;
          cancel_pending<=0;state<=DESCRIPTOR;
        end
        DESCRIPTOR:if(header_ready)begin segment_words<=next_segment;word_position<=0;prefix_position<=0;state<=PREFIX;end
        PREFIX:if(payload_ready)begin if(prefix_position==3'd7)state<=READ_REQ;else prefix_position<=prefix_position+3'd1;end
        READ_REQ:if(sample_ready)state<=READ_WAIT;
        READ_WAIT:if(sample_valid)begin held_word<=sample_word;state<=LOW_BYTE;end
        LOW_BYTE:if(payload_ready)state<=HIGH_BYTE;
        HIGH_BYTE:if(payload_ready)begin
          if(word_position==segment_words-16'd1)state<=WAIT_PACKET;
          else begin word_position<=word_position+16'd1;state<=READ_REQ;end
        end
        WAIT_PACKET:if(packet_done)begin
          if(cancel_pending || cancel || remaining==32'(segment_words))state<=IDLE;
          else begin offset<=offset+32'(segment_words);remaining<=remaining-32'(segment_words);seq<=seq+16'd1;state<=DESCRIPTOR;end
        end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
`default_nettype wire

