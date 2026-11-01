`default_nettype none
module fft_ip_wrapper (
  input wire clk, rst, module_enable, start,
  output wire start_ready,
  input wire cfg_inverse,
  input wire in_valid,
  output wire in_ready,
  input wire signed [15:0] in_real, in_imag,
  input wire in_last,
  output wire out_valid,
  input wire out_ready,
  output wire signed [31:0] out_real, out_imag,
  output wire [10:0] out_bin,
  output wire out_last,
  output logic done, cancelled, protocol_error
);
  timeunit 1ns; timeprecision 1ps;
  typedef enum logic [2:0] {IDLE, CONFIGURE, GUARD, FEED, DRAIN} state_t;
  state_t state;
  logic [2:0] reset_hold, guard_count;
  logic inverse;
  logic [10:0] input_count, output_count;
  wire ip_resetn = !rst && module_enable && (reset_hold == 3'd0);
  wire config_ready, data_ready, data_valid, data_last;
  wire [63:0] data_out;
  wire [15:0] user_out;
  wire event_started, event_unexpected, event_missing;
  wire event_status_halt, event_input_halt, event_output_halt;
  assign start_ready = ip_resetn && (state == IDLE);
  assign in_ready = ip_resetn && (state == FEED) && data_ready;
  assign out_valid = ip_resetn && (state == DRAIN) && data_valid;
  assign out_real = $signed(data_out[31:0]);
  assign out_imag = $signed(data_out[63:32]);
  assign out_bin = {1'b0, user_out[9:0]};
  assign out_last = data_last;
  // Unscaled FFT: 16 + log2(1024) + 1 = 27 significant bits.
  // The vendor packs each signed result into a sign-extended 32-bit lane.
  scope_fft_1024 fft (
    .aclk(clk), .aresetn(ip_resetn),
    .s_axis_config_tdata({7'd0, !inverse}),
    .s_axis_config_tvalid(ip_resetn && state == CONFIGURE),
    .s_axis_config_tready(config_ready),
    .s_axis_data_tdata({in_imag, in_real}),
    .s_axis_data_tvalid(ip_resetn && state == FEED && in_valid),
    .s_axis_data_tready(data_ready), .s_axis_data_tlast(in_last),
    .m_axis_data_tdata(data_out), .m_axis_data_tuser(user_out),
    .m_axis_data_tvalid(data_valid),
    .m_axis_data_tready(ip_resetn && state == DRAIN && out_ready),
    .m_axis_data_tlast(data_last),
    .event_frame_started(event_started), .event_tlast_unexpected(event_unexpected),
    .event_tlast_missing(event_missing), .event_status_channel_halt(event_status_halt),
    .event_data_in_channel_halt(event_input_halt), .event_data_out_channel_halt(event_output_halt)
  );
  always_ff @(posedge clk) begin
    if (rst) begin
      state <= IDLE; reset_hold <= 3'd4; guard_count <= 3'd0;
      inverse <= 1'b0; input_count <= 11'd0; output_count <= 11'd0;
      done <= 1'b0; cancelled <= 1'b0; protocol_error <= 1'b0;
    end else begin
      done <= 1'b0; cancelled <= 1'b0; protocol_error <= 1'b0;
      if (!module_enable) begin
        cancelled <= state != IDLE; state <= IDLE; reset_hold <= 3'd4;
        input_count <= 11'd0; output_count <= 11'd0; guard_count <= 3'd0;
      end else if (reset_hold != 3'd0) reset_hold <= reset_hold - 3'd1;
      else begin
        case (state)
          IDLE: if (start) begin
            inverse <= cfg_inverse; state <= CONFIGURE;
            input_count <= 11'd0; output_count <= 11'd0;
          end
          CONFIGURE: if (config_ready) begin state <= GUARD; guard_count <= 3'd4; end
          GUARD: if (guard_count == 3'd1) state <= FEED;
                 else guard_count <= guard_count - 3'd1;
          FEED: if (in_valid && in_ready) begin
            if (in_last != (input_count == 11'd1023)) begin
              protocol_error <= 1'b1; state <= IDLE; reset_hold <= 3'd4;
            end else if (input_count == 11'd1023) state <= DRAIN;
            else input_count <= input_count + 11'd1;
          end
          DRAIN: if (out_valid && out_ready) begin
            if (output_count == 11'd1023) begin done <= 1'b1; state <= IDLE; end
            else output_count <= output_count + 11'd1;
          end
          default: begin state <= IDLE; reset_hold <= 3'd4; protocol_error <= 1'b1; end
        endcase
      end
    end
  end
`ifndef SYNTHESIS
  logic stalled;
  logic [90:0] held;
  always_ff @(posedge clk) begin
    if (rst || !ip_resetn) begin stalled <= 1'b0; held <= '0; end
    else begin
      if (stalled) assert(out_valid && {out_bin,out_real,out_imag,out_last} == held[75:0])
        else $fatal(1,"FFT_OUTPUT_STABILITY");
      stalled <= out_valid && !out_ready;
      held <= {15'd0,out_bin,out_real,out_imag,out_last};
      if (in_valid && in_ready) assert(in_last == (input_count == 11'd1023))
        else $fatal(1,"FFT_INPUT_TLAST");
      if (out_valid) begin
        assert(out_bin == output_count && out_last == (output_count == 11'd1023))
          else $fatal(1,"FFT_BIN_ORDER_TLAST");
        assert(user_out[15:10] == 6'd0 && data_out[31:27] == {5{data_out[26]}} &&
               data_out[63:59] == {5{data_out[58]}}) else $fatal(1,"FFT_SIGN_PADDING");
      end
      assert(!event_missing && !event_unexpected) else $fatal(1,"FFT_VENDOR_TLAST_EVENT");
    end
  end
`endif
endmodule
`default_nettype wire
