`default_nettype none
module frame_tx(
  input wire logic clk,rst,header_valid,payload_valid,out_ready,
  input wire protocol_pkg::frame_header_t header,
  input wire logic [7:0] payload_data,
  output wire logic header_ready,payload_ready,out_valid,
  output logic [7:0] out_data,
  output logic done
);
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;
  typedef enum logic [2:0] {IDLE,HEADER,PAYLOAD,CRC_LOW,CRC_HIGH} state_t;
  state_t state;
  frame_header_t held;
  logic [4:0] position;
  logic [15:0] payload_position,crc;
  assign header_ready=state==IDLE && !rst;
  assign out_valid=!rst && state!=IDLE && (state!=PAYLOAD || payload_valid);
  assign payload_ready=state==PAYLOAD && out_ready && !rst;
  always_comb begin
    case(state)
      HEADER:out_data=header_byte(held,position);
      PAYLOAD:out_data=payload_data;
      CRC_LOW:out_data=crc[7:0];CRC_HIGH:out_data=crc[15:8];default:out_data=0;
    endcase
  end
  always_ff @(posedge clk)begin
    if(rst)begin state<=IDLE;held<='0;position<=0;payload_position<=0;crc<=16'hffff;done<=0;end
    else begin
      done<=0;
      if(header_valid && header_ready)begin
        // translate_off
        assert(header.length<=16'(MAX_PAYLOAD))else $fatal(1,"FRAME_TX_LENGTH_ASSERT");
        // translate_on
        held<=header;position<=0;crc<=16'hffff;payload_position<=0;state<=HEADER;
      end else if(out_valid && out_ready)begin
        case(state)
          HEADER:begin
            if(position>=5'd2)crc<=crc16_byte(crc,out_data);
            if(position==5'd25)state<=held.length==16'd0 ?CRC_LOW:PAYLOAD;
            else position<=position+5'd1;
          end
          PAYLOAD:begin
            crc<=crc16_byte(crc,out_data);
            if(payload_position==held.length-16'd1)state<=CRC_LOW;
            else payload_position<=payload_position+16'd1;
          end
          CRC_LOW:state<=CRC_HIGH;
          CRC_HIGH:begin state<=IDLE;done<=1;end
          default:state<=IDLE;
        endcase
      end
    end
  end
endmodule
`default_nettype wire

