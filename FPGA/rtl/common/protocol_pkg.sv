`default_nettype none
package protocol_pkg;
  timeunit 1ns;timeprecision 1ps;
  localparam int unsigned HEADER_BYTES=26,MAX_PAYLOAD=1024,MIN_FRAME_BYTES=28;
  localparam logic [7:0] PROTOCOL_VERSION=8'd1;
  localparam logic [15:0] FLAG_RESPONSE=16'h0001,FLAG_ERROR=16'h0002,
    FLAG_MORE=16'h0004,FLAG_FIRST=16'h0008,FLAG_LAST=16'h0010;
  localparam logic [7:0] CMD_PING=8'h01,CMD_VERSION=8'h02,CMD_STATUS=8'h03,
    CMD_RECORD=8'h10,CMD_TRIGGER=8'h11,CMD_SINGLE=8'h20,CMD_STOP=8'h21,
    CMD_WAVE=8'h30,CMD_MEASURE=8'h31,CMD_SPECTRUM=8'h33,CMD_DDS=8'h40,
    CMD_CAPABILITIES=8'h04,CMD_CONFIG_READ=8'h05,CMD_ENVELOPE=8'h32,
    CMD_CAPTURE_MODE=8'h12,CMD_CAPTURE_CONFIG=8'h13,CMD_RUN=8'h22,CMD_RELEASE=8'h23,CMD_SATURATION=8'h34,CMD_DIAGNOSTIC=8'h14,
    CMD_AWG_BEGIN=8'h15,CMD_AWG_CHUNK=8'h16,CMD_AWG_COMMIT=8'h17,
    CMD_AWG_READ=8'h18,CMD_AWG_STATUS=8'h19,CMD_AWG_SELECT=8'h1a;
  localparam logic [7:0] OK=8'd0,ERR_LENGTH=8'd1,ERR_CONFIG=8'd2,ERR_BUSY=8'd3,
    ERR_NO_FRAME=8'd4,ERR_UNKNOWN=8'd5;
  typedef struct packed {
    logic [7:0] kind;
    logic [15:0] seq,length;
    logic [63:0] timestamp;
    logic [31:0] sample_rate,trigger_index;
    logic [15:0] flags;
  } frame_header_t;
  // The command engine consumes only these fields. Request acquisition
  // metadata is retained by the protocol core's diagnostic output.
  typedef struct packed {
    logic [7:0] kind;
    logic [15:0] seq,length,flags;
  } command_header_t;
  typedef struct packed {logic [31:0] crc,length,version,timeout;} parser_errors_t;
  function automatic logic [15:0] crc16_byte(input logic [15:0] initial_crc,input logic [7:0] data);
    logic [15:0] c;
    c=initial_crc^{data,8'd0};
    for(int unsigned b=0;b<8;b++)c=(c<<1)^(c[15]?16'h1021:16'd0);
    return c;
  endfunction
  function automatic logic [7:0] header_byte(input frame_header_t h,input logic [4:0] n);
    case(n)
      5'd0:return 8'h55;5'd1:return 8'haa;5'd2:return PROTOCOL_VERSION;5'd3:return h.kind;
      5'd4:return h.seq[7:0];5'd5:return h.seq[15:8];
      5'd6:return h.length[7:0];5'd7:return h.length[15:8];
      5'd8,5'd9,5'd10,5'd11,5'd12,5'd13,5'd14,5'd15:return 8'(h.timestamp>>(32'(n-5'd8)*32'd8));
      5'd16,5'd17,5'd18,5'd19:return 8'(h.sample_rate>>(32'(n-5'd16)*32'd8));
      5'd20,5'd21,5'd22,5'd23:return 8'(h.trigger_index>>(32'(n-5'd20)*32'd8));
      5'd24:return h.flags[7:0];5'd25:return h.flags[15:8];default:return 8'd0;
    endcase
  endfunction
endpackage
`default_nettype wire
