`default_nettype none
// Sliding retained byte queue: on any invalid candidate advance ONE byte.
// This preserves 55 AA inside a corrupted frame and prevents permanent loss
// of alignment after an inserted/deleted byte or damaged length field.
module frame_rx #(parameter int unsigned TIMEOUT_CYCLES=100000,QUEUE_ADDR_BITS=11)(
  input wire logic clk,rst,in_valid,header_ready,payload_ready,
  input wire logic [7:0] in_data,
  output wire logic in_ready,header_valid,payload_valid,
  output protocol_pkg::frame_header_t header,
  output wire logic [7:0] payload_data,
  output protocol_pkg::parser_errors_t errors,
  output logic [31:0] good_frames
);
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;
  typedef enum logic [3:0] {FIND,MAGIC2,GET_HEADER,CHECK_HEADER,WAIT_BODY,SCAN_CRC,GET_CRC_LOW,GET_CRC_HIGH,OFFER,PAYLOAD} state_t;
  state_t state;
  (* ram_style="distributed" *) logic [7:0] memory[0:(1<<QUEUE_ADDR_BITS)-1];
  logic [QUEUE_ADDR_BITS-1:0] head,tail,address;
  logic [QUEUE_ADDR_BITS:0] count,pop_count;
  logic [15:0] scan_position,payload_position,crc;
  logic [4:0] header_position;
  logic [7:0] received_version,wire_crc_low;
  logic [31:0] gap_count;
  logic waiting,timed_out;
  logic [7:0] peek;
  wire logic push=in_valid && in_ready;
  assign in_ready=!rst && count<(QUEUE_ADDR_BITS+1)'(1<<QUEUE_ADDR_BITS);
  assign header_valid=state==OFFER && !rst;
  assign payload_valid=state==PAYLOAD && !rst;
  assign payload_data=peek;
  initial begin
    assert(TIMEOUT_CYCLES>0 && (1<<QUEUE_ADDR_BITS)>=MAX_PAYLOAD+MIN_FRAME_BYTES)
      else $fatal(1,"FRAME_RX_PARAMETER_ASSERT");
  end
  always_comb begin
    address=head;
    case(state)
      MAGIC2:address=head+1'b1;
      GET_HEADER:address=head+QUEUE_ADDR_BITS'(header_position);
      SCAN_CRC:address=head+QUEUE_ADDR_BITS'(scan_position);
      GET_CRC_LOW:address=head+QUEUE_ADDR_BITS'(26+header.length);
      GET_CRC_HIGH:address=head+QUEUE_ADDR_BITS'(27+header.length);
      PAYLOAD:address=head+QUEUE_ADDR_BITS'(26+payload_position);
      default:begin end
    endcase
    peek=memory[address];
    waiting=(state==MAGIC2 && count<2) || (state==GET_HEADER && count<=(QUEUE_ADDR_BITS+1)'(header_position)) ||
      (state==WAIT_BODY && count<(QUEUE_ADDR_BITS+1)'(MIN_FRAME_BYTES+header.length));
    timed_out=waiting && !push && gap_count==32'(TIMEOUT_CYCLES-1);
    pop_count=0;
    if(state==FIND && count!=0 && peek!=8'h55)pop_count=1;
    if(state==MAGIC2 && count>=2 && peek!=8'haa)pop_count=1;
    if(state==CHECK_HEADER && (received_version!=PROTOCOL_VERSION || header.length>16'(MAX_PAYLOAD)))pop_count=1;
    if(state==GET_CRC_HIGH && {peek,wire_crc_low}!=crc)pop_count=1;
    if(state==OFFER && header_ready && header.length==16'd0)pop_count=(QUEUE_ADDR_BITS+1)'(MIN_FRAME_BYTES);
    if(state==PAYLOAD && payload_ready && payload_position==header.length-16'd1)pop_count=(QUEUE_ADDR_BITS+1)'(MIN_FRAME_BYTES+header.length);
    if(timed_out)pop_count=1;
  end
  always_ff @(posedge clk)begin
    if(rst)begin
      state<=FIND;head<=0;tail<=0;count<=0;header<='0;errors<='0;good_frames<=0;
      header_position<=0;scan_position<=0;payload_position<=0;crc<=16'hffff;received_version<=0;wire_crc_low<=0;gap_count<=0;
    end else begin
      if(push)begin memory[tail]<=in_data;tail<=tail+1'b1;end
      if(pop_count!=0)head<=head+QUEUE_ADDR_BITS'(pop_count);
      count<=count+(push?1'b1:1'b0)-pop_count;
      if(!waiting || push || timed_out)gap_count<=0;else gap_count<=gap_count+32'd1;
      if(timed_out)begin errors.timeout<=errors.timeout+32'd1;state<=FIND;end
      else case(state)
        FIND:if(count!=0 && peek==8'h55)state<=MAGIC2;
        MAGIC2:if(count>=2)begin
          if(peek==8'haa)begin state<=GET_HEADER;header_position<=5'd2;end else state<=FIND;
        end
        GET_HEADER:if(count>(QUEUE_ADDR_BITS+1)'(header_position))begin
          case(header_position)
            5'd2:begin received_version<=peek;header<='0;end
            5'd3:header.kind<=peek;
            5'd4:header.seq[7:0]<=peek;5'd5:header.seq[15:8]<=peek;
            5'd6:header.length[7:0]<=peek;5'd7:header.length[15:8]<=peek;
            5'd8,5'd9,5'd10,5'd11,5'd12,5'd13,5'd14,5'd15:header.timestamp[32'(header_position-5'd8)*8+:8]<=peek;
            5'd16,5'd17,5'd18,5'd19:header.sample_rate[32'(header_position-5'd16)*8+:8]<=peek;
            5'd20,5'd21,5'd22,5'd23:header.trigger_index[32'(header_position-5'd20)*8+:8]<=peek;
            5'd24:header.flags[7:0]<=peek;5'd25:header.flags[15:8]<=peek;default:begin end
          endcase
          if(header_position==5'd25)state<=CHECK_HEADER;else header_position<=header_position+5'd1;
        end
        CHECK_HEADER:if(received_version!=PROTOCOL_VERSION)begin errors.version<=errors.version+32'd1;state<=FIND;end
          else if(header.length>16'(MAX_PAYLOAD))begin errors.length<=errors.length+32'd1;state<=FIND;end
          else state<=WAIT_BODY;
        WAIT_BODY:if(count>=(QUEUE_ADDR_BITS+1)'(MIN_FRAME_BYTES+header.length))begin scan_position<=16'd2;crc<=16'hffff;state<=SCAN_CRC;end
        SCAN_CRC:begin
          crc<=crc16_byte(crc,peek);
          if(scan_position==16'd25+header.length)state<=GET_CRC_LOW;else scan_position<=scan_position+16'd1;
        end
        GET_CRC_LOW:begin wire_crc_low<=peek;state<=GET_CRC_HIGH;end
        GET_CRC_HIGH:if({peek,wire_crc_low}==crc)begin good_frames<=good_frames+32'd1;state<=OFFER;end
          else begin errors.crc<=errors.crc+32'd1;state<=FIND;end
        OFFER:if(header_ready)begin payload_position<=0;state<=header.length==16'd0 ?FIND:PAYLOAD;end
        PAYLOAD:if(payload_ready)begin
          if(payload_position==header.length-16'd1)state<=FIND;else payload_position<=payload_position+16'd1;
        end
        default:state<=FIND;
      endcase
    end
  end
endmodule
`default_nettype wire

