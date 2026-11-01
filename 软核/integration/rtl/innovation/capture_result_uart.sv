`default_nettype none
// B2 response, payload = offset(u32 LE) + <=1020 container bytes.
// Reuses the Step 9 frame_tx and CRC16. One chunk RAM; no full-frame copy.
module capture_result_uart(
  input wire clk,rst,module_enable,start,
  output wire start_ready,
  input wire [31:0] cfg_total_bytes,
  input protocol_pkg::frame_header_t cfg_header,
  input wire in_valid,
  output wire in_ready,
  input wire [7:0] in_data,
  output wire out_valid,
  input wire out_ready,
  output wire [7:0] out_data,
  output logic done,error
);
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;
  typedef enum logic [2:0] {IDLE,FILL,SEND_HEADER,SEND_PAYLOAD,WAIT_DONE} state_t;
  state_t state;
  logic [7:0] memory[0:1019];
  logic [31:0] total,offset;
  logic [10:0] chunk,fill_count,payload_position;
  frame_header_t held,header;
  wire header_ready,payload_ready,tx_done;
  logic [7:0] payload_data;
  assign start_ready=state==IDLE && module_enable && !rst;
  assign in_ready=state==FILL && module_enable && !rst;
  always_comb begin
    header=held;header.kind=8'hb2;header.length={5'd0,chunk}+16'd4;
    header.flags=FLAG_RESPONSE | (offset==0 ? FLAG_FIRST:16'd0) |
      (offset+{21'd0,chunk}==total ? FLAG_LAST:FLAG_MORE);
    if(payload_position<11'd4)payload_data=8'(offset>>(32'(payload_position)*32'd8));
    else if(state==SEND_PAYLOAD && payload_position<chunk+11'd4)payload_data=memory[payload_position-11'd4];
    else payload_data=8'd0;
  end
  frame_tx transmitter(.clk(clk),.rst(rst || !module_enable),.header_valid(state==SEND_HEADER),.header(header),.header_ready(header_ready),
    .payload_valid(state==SEND_PAYLOAD),.payload_data(payload_data),.payload_ready(payload_ready),.out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),.done(tx_done));
  always_ff @(posedge clk)begin
    if(rst)begin state<=IDLE;total<=0;offset<=0;chunk<=0;fill_count<=0;payload_position<=0;held<='0;done<=0;error<=0;end
    else begin
      done<=0;error<=0;
      if(!module_enable)state<=IDLE;
      else case(state)
        IDLE:if(start)begin
          if(cfg_total_bytes==0 || cfg_total_bytes>32'd1000000)error<=1;
          else begin total<=cfg_total_bytes;offset<=0;chunk<=cfg_total_bytes>1020 ?11'd1020:11'(cfg_total_bytes);fill_count<=0;held<=cfg_header;state<=FILL;end
        end
        FILL:if(in_valid)begin
          memory[fill_count]<=in_data;fill_count<=fill_count+11'd1;
          if(fill_count==chunk-11'd1)state<=SEND_HEADER;
        end
        SEND_HEADER:if(header_ready)begin payload_position<=0;state<=SEND_PAYLOAD;end
        SEND_PAYLOAD:if(payload_ready)begin
          payload_position<=payload_position+11'd1;
          if(payload_position==chunk+11'd3)state<=WAIT_DONE;
        end
        WAIT_DONE:if(tx_done)begin
          if(offset+{21'd0,chunk}==total)begin state<=IDLE;done<=1;end
          else begin
            offset<=offset+{21'd0,chunk};held.seq<=held.seq+16'd1;fill_count<=0;
            chunk<=total-offset-{21'd0,chunk}>1020 ?11'd1020:11'(total-offset-{21'd0,chunk});state<=FILL;
          end
        end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
`default_nettype wire
