`default_nettype none
// System-clock command adapter. Capture/read/measurement ports are explicit
// backend contracts; cross-domain hardware integration belongs in its wrapper.
module protocol_commands #(
  parameter bit LOOPBACK_BOOT_PRESET=1'b0,SUPPORT_MULTIRES=1'b0,SUPPORT_ANALYSIS=1'b0,SUPPORT_MODES=1'b0,SUPPORT_SATURATION=1'b0,SUPPORT_AWG=1'b0,
  parameter logic [31:0] FIRMWARE_BUILD=32'd0)(
  input wire logic clk,rst,header_valid,payload_valid,
  input wire [9:0] awg_play_index,
  output wire signed [15:0] awg_play_value,
  output logic awg_selected,
  input wire protocol_pkg::command_header_t header,
  input wire logic [7:0] payload_data,
  output wire logic header_ready,payload_ready,
  output wire logic response_valid,response_payload_valid,
  output protocol_pkg::frame_header_t response,
  output wire logic [7:0] response_payload,
  input wire logic response_ready,response_payload_ready,response_done,
  input wire protocol_pkg::parser_errors_t parser_errors,
  input wire logic [31:0] good_frames,uart_framing_errors,rx_overruns,
  input wire logic capture_busy,capture_ready,frame_available,backend_error,wave_ready,
  input wire logic [63:0] backend_timestamp,
  input wire logic [31:0] backend_rate,backend_trigger_index,backend_length,
  input wire scope_pkg::measurement_result_t measurements,
  input wire logic measurement_error,
  input wire logic [767:0] spectrum_bytes,
  input wire logic [127:0] saturation_bytes,
  output logic [1:0] diagnostic_mode,
  output logic single_pulse,stop_pulse,release_pulse,acquire_enable,wave_request,
  output logic [31:0] wave_offset,wave_count,
  output logic [15:0] wave_sequence,
  output logic envelope_request,
  output logic [9:0] envelope_buckets,
  output logic [15:0] envelope_sequence,
  output logic [17:0] record_length,pre_samples,
  output scope_pkg::capture_mode_t capture_mode,
  output logic [31:0] auto_timeout,
  output scope_pkg::trigger_config_t trigger_config,
  output scope_pkg::dds_wave_t dds_wave,
  output logic dds_enable,
  output logic [31:0] dds_phase_inc,dds_phase_offset,
  output logic [15:0] dds_amplitude,
  output logic signed [17:0] dds_dc_offset,
  output logic [31:0] unknown_commands,command_errors
);
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;import scope_pkg::*;
  // Physical 25 MHz board preset; generic protocol instances keep their
  // original reset defaults. External pins remain gated by the safety core.
  localparam logic [31:0] BUILD_ID=(FIRMWARE_BUILD!=0?FIRMWARE_BUILD:SUPPORT_SATURATION?32'h22261027:SUPPORT_MODES?32'h21261026:SUPPORT_ANALYSIS?32'h20261026:(LOOPBACK_BOOT_PRESET?32'h20261025:32'h20261022)) |
    (SUPPORT_MULTIRES?32'h80000000:32'd0);
  typedef enum logic [4:0] {IDLE,RECEIVE,EXECUTE,FILL,SEND_HEADER,SEND_PAYLOAD,WAIT_PACKET,DIV_START,DIV_WAIT,WAIT_CAPTURE,AWG_VALIDATE,AWG_COPY,AWG_READ_WAIT,AWG_READ_STORE} state_t;
  state_t state;
  command_header_t command;
  (* ram_style="distributed" *) logic [7:0] memory[0:MAX_PAYLOAD-1];
  logic ack_mode;
  logic [7:0] ack_code;
  logic [255:0] command_bytes;
  logic [15:0] position,send_position,fill_length;
  logic [3:0] fill_kind;
  logic [383:0] configuration_bytes,configuration_snapshot;
  logic [31:0] dds_frequency_hz;
  parser_errors_t errors_snapshot;
  measurement_result_t measure_snapshot;
  logic [767:0] spectrum_snapshot;
  logic [127:0] saturation_snapshot;
  logic measurement_error_snapshot,backend_error_snapshot;
  logic [31:0] framing_snapshot,overrun_snapshot,good_snapshot;
  logic [7:0] status_snapshot;
  logic [63:0] div_numerator,div_denominator;
  wire logic [63:0] quotient,remainder;
  wire logic div_busy,div_done;
  logic div_for_dds;
  logic [31:0] start_wait;
  capture_mode_t selected_mode;
  logic [63:0] capture_configuration_snapshot;
  trigger_config_t candidate_trigger;
  logic trigger_fields_ok;
  logic [32:0] requested_end;
  logic [7:0] fill_byte;
  // Two complete banks: only a full CRC-checked staging bank becomes active.
  (* ram_style="block" *) logic signed [15:0] awg_table[0:2047];
  logic awg_bank,awg_valid,awg_uploading;
  logic [10:0] awg_received;
  logic [15:0] awg_crc,awg_active_crc,awg_read_value;
  logic signed [15:0] awg_play_reg;
  logic [127:0] awg_status_snapshot;
  wire [15:0] awg_chunk_word={memory[position[9:0]+10'd1],memory[position[9:0]]};
  wire [10:0] awg_write_index=awg_received+((position-16'd2)>>1);
  wire [9:0] awg_read_index=10'(command_bytes[15:0]+((position-16'd4)>>1));
  always_ff @(posedge clk)begin
    if(!rst && state==AWG_COPY)awg_table[{!awg_bank,awg_write_index[9:0]}]<=awg_chunk_word;
    else awg_read_value<=awg_table[{awg_bank,awg_read_index}];
  end
  always_ff @(negedge clk)awg_play_reg<=awg_table[{awg_bank,awg_play_index}];
  assign awg_play_value=awg_valid?awg_play_reg:16'sd0;

  assign header_ready=state==IDLE && !rst;
  assign payload_ready=state==RECEIVE && !rst;
  assign response_valid=state==SEND_HEADER && !rst;
  assign response_payload_valid=state==SEND_PAYLOAD && !rst;
  assign response_payload=ack_mode?ack_code:memory[send_position[9:0]];
  // One explicit physical write port. Status/measurement fills and received
  // payloads are mutually exclusive; ACK bytes do not modify this RAM.
  always_ff @(posedge clk)begin
    if(!rst && ((state==RECEIVE && payload_valid) || state==FILL || state==AWG_READ_STORE))
      memory[position[9:0]]<=state==FILL?fill_byte:
        state==AWG_READ_STORE?(position[0]?awg_read_value[15:8]:awg_read_value[7:0]):payload_data;
  end
  measure_udiv divider(.clk(clk),.rst(rst),.start(state==DIV_START),.dividend(div_numerator),.divisor(div_denominator),
    .busy(div_busy),.done(div_done),.quotient(quotient),.remainder(remainder));
  always_comb begin
    configuration_bytes='0;
    configuration_bytes[31:0]=32'(record_length);
    configuration_bytes[63:32]=32'(pre_samples);
    configuration_bytes[71:64]=8'(trigger_config.kind);
    configuration_bytes[95:80]=16'($signed(trigger_config.threshold));
    configuration_bytes[111:96]=16'(trigger_config.hysteresis);
    configuration_bytes[127:112]=16'($signed(trigger_config.window_low));
    configuration_bytes[143:128]=16'($signed(trigger_config.window_high));
    configuration_bytes[175:144]=trigger_config.width_min;
    configuration_bytes[207:176]=trigger_config.width_max;
    configuration_bytes[223:208]=16'(trigger_config.amplitude_limit);
    configuration_bytes[255:224]=32'(trigger_config.observation_samples);
    configuration_bytes[263:256]=8'(dds_wave);
    configuration_bytes[271:264]={7'd0,dds_enable};
    configuration_bytes[303:272]=dds_frequency_hz;
    configuration_bytes[335:304]=dds_phase_offset;
    configuration_bytes[351:336]=dds_amplitude;
    configuration_bytes[383:352]=32'($signed(dds_dc_offset));
    candidate_trigger='0;
    candidate_trigger.kind=trigger_type_t'(command_bytes[3:0]);
    candidate_trigger.threshold=$signed(command_bytes[28:16]);candidate_trigger.hysteresis=command_bytes[44:32];
    candidate_trigger.window_low=$signed(command_bytes[60:48]);candidate_trigger.window_high=$signed(command_bytes[76:64]);
    candidate_trigger.width_min=command_bytes[111:80];candidate_trigger.width_max=command_bytes[143:112];
    candidate_trigger.amplitude_limit=command_bytes[157:144];candidate_trigger.observation_samples=command_bytes[174:160];
    trigger_fields_ok=command_bytes[15:8]==8'd0 && command_bytes[7:0]<=8'd8 &&
      $signed(command_bytes[31:16])>=-16'sd4096 && $signed(command_bytes[31:16])<=16'sd4095 && command_bytes[47:32]<=16'd8191 &&
      $signed(command_bytes[63:48])>=-16'sd4096 && $signed(command_bytes[63:48])<=16'sd4095 &&
      $signed(command_bytes[79:64])>=-16'sd4096 && $signed(command_bytes[79:64])<=16'sd4095 &&
      command_bytes[159:144]<=16'd16383 && command_bytes[191:160]<=32'd16384 && trigger_config_valid(candidate_trigger);
    requested_end={1'b0,command_bytes[31:0]}+{1'b0,command_bytes[63:32]};
    fill_byte=0;
    case(fill_kind)
      2'd0:case(position)
        0:fill_byte=1;1,2,3:fill_byte=0;default:fill_byte=8'(BUILD_ID>>(32'(position-16'd4)*8));
      endcase
      2'd1:begin
        if(position==0)fill_byte=status_snapshot;
        else if(position==1)fill_byte={7'd0,backend_error_snapshot};else if(position==2)fill_byte=PROTOCOL_VERSION;
        else if(position>=4 && position<8)fill_byte=8'(32'(record_length)>>(32'(position-16'd4)*8));
        else if(position>=8 && position<12)fill_byte=8'(32'(pre_samples)>>(32'(position-16'd8)*8));
        else if(position>=12 && position<16)fill_byte=8'(errors_snapshot.crc>>(32'(position-16'd12)*8));
        else if(position>=16 && position<20)fill_byte=8'(errors_snapshot.length>>(32'(position-16'd16)*8));
        else if(position>=20 && position<24)fill_byte=8'(errors_snapshot.version>>(32'(position-16'd20)*8));
        else if(position>=24 && position<28)fill_byte=8'(errors_snapshot.timeout>>(32'(position-16'd24)*8));
        else if(position>=28 && position<32)fill_byte=8'(unknown_commands>>(32'(position-16'd28)*8));
        else if(position>=32 && position<36)fill_byte=8'(command_errors>>(32'(position-16'd32)*8));
        else if(position>=36 && position<40)fill_byte=8'(framing_snapshot>>(32'(position-16'd36)*8));
        else if(position>=40 && position<44)fill_byte=8'(overrun_snapshot>>(32'(position-16'd40)*8));
        else if(position>=44 && position<48)fill_byte=8'(good_snapshot>>(32'(position-16'd44)*8));
      end
      2'd2:begin
        case(position)
          0:fill_byte={7'd0,measure_snapshot.stats_valid};1:fill_byte={7'd0,measure_snapshot.period_valid};
          2:fill_byte={7'd0,measure_snapshot.duty_valid};3:fill_byte={7'd0,measurement_error_snapshot};default:begin end
        endcase
        if(position>=4 && position<8)fill_byte=8'(32'(measure_snapshot.sample_count)>>(32'(position-16'd4)*8));
        else if(position>=8 && position<10)fill_byte=8'(16'($signed(measure_snapshot.minimum))>>(32'(position-16'd8)*8));
        else if(position>=10 && position<12)fill_byte=8'(16'($signed(measure_snapshot.maximum))>>(32'(position-16'd10)*8));
        else if(position>=12 && position<14)fill_byte=8'(16'($signed(measure_snapshot.mean))>>(32'(position-16'd12)*8));
        else if(position>=14 && position<16)fill_byte=8'(16'(measure_snapshot.peak_to_peak)>>(32'(position-16'd14)*8));
        else if(position>=16 && position<18)fill_byte=8'(16'(measure_snapshot.rms)>>(32'(position-16'd16)*8));
        else if(position>=20 && position<28)fill_byte=8'(64'(measure_snapshot.sum)>>(32'(position-16'd20)*8));
        else if(position>=28 && position<36)fill_byte=8'(measure_snapshot.square_sum>>(32'(position-16'd28)*8));
        else if(position>=36 && position<44)fill_byte=8'(measure_snapshot.period_q16>>(32'(position-16'd36)*8));
        else if(position>=44 && position<48)fill_byte=8'(measure_snapshot.frequency_hz>>(32'(position-16'd44)*8));
        else if(position>=48 && position<52)fill_byte=8'(measure_snapshot.duty_ppm>>(32'(position-16'd48)*8));
        else if(position>=52 && position<56)fill_byte=8'(32'(measure_snapshot.period_count)>>(32'(position-16'd52)*8));
      end
      2'd3:case(position)
        0:fill_byte=(SUPPORT_ANALYSIS?8'd7:8'd3)|(SUPPORT_MODES?8'd8:8'd0)|(SUPPORT_SATURATION?8'd16:8'd0)|(SUPPORT_AWG?8'd32:8'd0); // bit 2: frozen measurement + 1024 FFT summary
        4:fill_byte=8'h20;5:fill_byte=8'h03; // 800 buckets
        6:fill_byte=8'h00;7:fill_byte=8'h08; // 2048 raw ROI samples
        default:fill_byte=0;
      endcase
      3'd4:fill_byte=8'(configuration_snapshot>>(32'(position)*8));
      3'd5:fill_byte=8'(spectrum_snapshot>>(32'(position)*8));
      3'd6:fill_byte=8'(capture_configuration_snapshot>>(32'(position)*8));
      4'd8:fill_byte=8'(awg_status_snapshot>>(32'(position)*8));
      3'd7:fill_byte=8'(saturation_snapshot>>(32'(position)*8));
      default:begin end
    endcase
  end
  task automatic reply(input logic [7:0] code);
    ack_mode<=1;ack_code<=code;response.length<=16'd1;response.flags<=FLAG_RESPONSE|(code==OK?16'd0:FLAG_ERROR);
    if(code!=OK)command_errors<=command_errors+32'd1;
    state<=SEND_HEADER;
  endtask
  always_ff @(posedge clk)begin
    if(rst)begin
      awg_bank<=0;awg_valid<=0;awg_uploading<=0;awg_selected<=0;awg_received<=0;awg_crc<=16'hffff;awg_active_crc<=0;awg_status_snapshot<=0;
      state<=IDLE;command<='0;response<='0;command_bytes<='0;position<=0;send_position<=0;fill_length<=0;fill_kind<=0;ack_mode<=0;ack_code<=0;
      errors_snapshot<='0;measure_snapshot<='0;measurement_error_snapshot<=0;backend_error_snapshot<=0;framing_snapshot<=0;overrun_snapshot<=0;good_snapshot<=0;status_snapshot<=0;
      capture_mode<=CAP_SINGLE;selected_mode<=CAP_SINGLE;auto_timeout<=32'd2500000;capture_configuration_snapshot<=0;
      single_pulse<=0;stop_pulse<=0;release_pulse<=0;acquire_enable<=0;wave_request<=0;wave_offset<=0;wave_count<=0;wave_sequence<=0;
      envelope_request<=0;envelope_buckets<=0;envelope_sequence<=0;
      configuration_snapshot<='0;spectrum_snapshot<='0;saturation_snapshot<=0;diagnostic_mode<=0;
      dds_frequency_hz<=LOOPBACK_BOOT_PRESET?32'd100000:32'd0;
      record_length<=18'd16384;pre_samples<=18'd8192;trigger_config<='0;trigger_config.kind<=TRIG_RISE;
      trigger_config.threshold<=LOOPBACK_BOOT_PRESET?13'sd4:13'sd0;
      trigger_config.hysteresis<=LOOPBACK_BOOT_PRESET?13'd2:13'd8;
      dds_wave<=DDS_SINE;dds_enable<=LOOPBACK_BOOT_PRESET;
      // round(100000 * 2^32 / 25000000), and round(0.10 * 8191).
      dds_phase_inc<=LOOPBACK_BOOT_PRESET?32'd17179869:32'd0;
      dds_phase_offset<=0;dds_amplitude<=LOOPBACK_BOOT_PRESET?16'd819:16'd0;dds_dc_offset<=0;
      unknown_commands<=0;command_errors<=0;div_numerator<=0;div_denominator<=1;div_for_dds<=0;start_wait<=0;
    end else begin
      single_pulse<=0;stop_pulse<=0;release_pulse<=0;wave_request<=0;envelope_request<=0;
      case(state)
        IDLE:if(header_valid)begin
          command<=header;command_bytes<='0;position<=0;state<=header.length==16'd0 ?EXECUTE:RECEIVE;
        end
        RECEIVE:if(payload_valid)begin
          if(position<16'd32)command_bytes[32'(position)*8+:8]<=payload_data;
          if(position==command.length-16'd1)state<=EXECUTE;else position<=position+16'd1;
        end
        EXECUTE:begin
          ack_mode<=0;
          response.kind<=command.kind|8'h80;response.seq<=command.seq;response.timestamp<=backend_timestamp;
          response.sample_rate<=backend_rate;response.trigger_index<=backend_trigger_index;response.flags<=FLAG_RESPONSE;
          if(command.flags!=16'd0)reply(ERR_CONFIG);
          else case(command.kind)
            CMD_PING:begin response.length<=command.length;state<=SEND_HEADER;end
            CMD_VERSION:if(command.length!=0)reply(ERR_LENGTH);else begin fill_kind<=0;fill_length<=8;position<=0;response.length<=8;state<=FILL;end
            CMD_CAPABILITIES:if(!SUPPORT_MULTIRES)begin unknown_commands<=unknown_commands+32'd1;reply(ERR_UNKNOWN);end
              else if(command.length!=0)reply(ERR_LENGTH);
              else begin fill_kind<=3;fill_length<=8;position<=0;response.length<=8;state<=FILL;end
            CMD_CONFIG_READ:if(!SUPPORT_MULTIRES)begin unknown_commands<=unknown_commands+32'd1;reply(ERR_UNKNOWN);end
              else if(command.length!=0)reply(ERR_LENGTH);
              else begin configuration_snapshot<=configuration_bytes;fill_kind<=4;fill_length<=48;position<=0;response.length<=48;state<=FILL;end
            CMD_STATUS:if(command.length!=0)reply(ERR_LENGTH);else begin
              errors_snapshot<=parser_errors;backend_error_snapshot<=backend_error;framing_snapshot<=uart_framing_errors;overrun_snapshot<=rx_overruns;good_snapshot<=good_frames;
              status_snapshot<={5'd0,dds_enable,frame_available,capture_busy};fill_kind<=1;fill_length<=48;position<=0;response.length<=48;state<=FILL;
            end
            CMD_RECORD:if(command.length!=8)reply(ERR_LENGTH);
              else if(capture_busy)reply(ERR_BUSY);
              else if(command_bytes[31:0]!=32'd16384 || command_bytes[63:32]>32'd1000000)reply(ERR_CONFIG);
              else begin
                div_numerator<=({32'd0,command_bytes[31:0]}-64'd1)*{32'd0,command_bytes[63:32]}+64'd500000;
                div_denominator<=64'd1000000;div_for_dds<=0;state<=DIV_START;
              end
            CMD_TRIGGER:if(command.length!=24)reply(ERR_LENGTH);else if(capture_busy)reply(ERR_BUSY);
              else if(!trigger_fields_ok)reply(ERR_CONFIG);else begin trigger_config<=candidate_trigger;reply(OK);end
            CMD_CAPTURE_MODE:if(!SUPPORT_MODES)reply(ERR_UNKNOWN);
              else if(command.length!=8)reply(ERR_LENGTH);
              else if(capture_busy || acquire_enable)reply(ERR_BUSY);
              else if(command_bytes[7:0]>2 || command_bytes[31:8]!=0 || command_bytes[63:32]==0)reply(ERR_CONFIG);
              else begin selected_mode<=capture_mode_t'(command_bytes[1:0]);auto_timeout<=command_bytes[63:32];reply(OK);end
            CMD_CAPTURE_CONFIG:if(!SUPPORT_MODES)reply(ERR_UNKNOWN);
              else if(command.length!=0)reply(ERR_LENGTH);
              else begin capture_configuration_snapshot<={auto_timeout,24'd0,6'd0,selected_mode};
                fill_kind<=6;fill_length<=8;position<=0;response.length<=8;state<=FILL;end
            CMD_RUN:if(!SUPPORT_MODES)reply(ERR_UNKNOWN);
              else if(command.length!=0)reply(ERR_LENGTH);
              else if(capture_busy || !wave_ready)reply(ERR_BUSY);
              else begin
                capture_mode<=selected_mode;acquire_enable<=0;
                if(frame_available)release_pulse<=1;
                start_wait<=0;state<=WAIT_CAPTURE;
              end
            CMD_RELEASE:if(!SUPPORT_MODES)reply(ERR_UNKNOWN);
              else if(command.length!=0)reply(ERR_LENGTH);
              else if(!acquire_enable || capture_mode==CAP_SINGLE)reply(ERR_CONFIG);
              else if(!frame_available)reply(ERR_NO_FRAME);
              else if(!wave_ready)reply(ERR_BUSY);
              else begin release_pulse<=1;reply(OK);end
            CMD_SINGLE:if(command.length!=0)reply(ERR_LENGTH);else if(capture_busy || !wave_ready)reply(ERR_BUSY);
              else if(frame_available || !capture_ready)begin
                capture_mode<=CAP_SINGLE;acquire_enable<=0;if(frame_available)release_pulse<=1;start_wait<=0;state<=WAIT_CAPTURE;
              end else begin capture_mode<=CAP_SINGLE;single_pulse<=1;acquire_enable<=1;reply(OK);end
            CMD_STOP:if(command.length!=0)reply(ERR_LENGTH);else begin stop_pulse<=1;acquire_enable<=0;diagnostic_mode<=0;reply(OK);end
            CMD_WAVE:if(command.length!=8)reply(ERR_LENGTH);else if(!frame_available)reply(ERR_NO_FRAME);
              else if(!wave_ready)reply(ERR_BUSY);
              else if(command_bytes[63:32]==0 || requested_end>{1'b0,backend_length})reply(ERR_CONFIG);
              else begin wave_request<=1;wave_offset<=command_bytes[31:0];wave_count<=command_bytes[63:32];wave_sequence<=command.seq;state<=IDLE;end
            CMD_ENVELOPE:if(!SUPPORT_MULTIRES)begin unknown_commands<=unknown_commands+32'd1;reply(ERR_UNKNOWN);end
              else if(command.length!=2)reply(ERR_LENGTH);
              else if(!frame_available)reply(ERR_NO_FRAME);
              else if(!wave_ready)reply(ERR_BUSY);
              else if(command_bytes[15:0]==0 || command_bytes[15:0]>16'd800)reply(ERR_CONFIG);
              else begin envelope_request<=1;envelope_buckets<=command_bytes[9:0];envelope_sequence<=command.seq;state<=IDLE;end
            CMD_MEASURE:if(command.length!=0)reply(ERR_LENGTH);
              else if(SUPPORT_ANALYSIS && !frame_available)reply(capture_busy?ERR_BUSY:ERR_NO_FRAME);else begin
              measure_snapshot<=measurements;measurement_error_snapshot<=measurement_error;
              fill_kind<=2;fill_length<=64;position<=0;response.length<=64;state<=FILL;
            end
            CMD_SPECTRUM:if(!SUPPORT_ANALYSIS)begin unknown_commands<=unknown_commands+32'd1;reply(ERR_UNKNOWN);end
              else if(command.length!=0)reply(ERR_LENGTH);
              else if(!frame_available)reply(capture_busy?ERR_BUSY:ERR_NO_FRAME);
              else begin spectrum_snapshot<=spectrum_bytes;fill_kind<=5;fill_length<=96;position<=0;response.length<=96;state<=FILL;end
            CMD_SATURATION:if(!SUPPORT_SATURATION)reply(ERR_UNKNOWN);
              else if(command.length!=0)reply(ERR_LENGTH);
              else if(!frame_available)reply(capture_busy?ERR_BUSY:ERR_NO_FRAME);
              else begin saturation_snapshot<=saturation_bytes;fill_kind<=7;fill_length<=16;position<=0;response.length<=16;state<=FILL;end
            CMD_DIAGNOSTIC:if(!SUPPORT_SATURATION)reply(ERR_UNKNOWN);
              else if(command.length!=1)reply(ERR_LENGTH);
              else if(capture_busy || acquire_enable)reply(ERR_BUSY);
              else if(command_bytes[7:0]>3)reply(ERR_CONFIG);
              else begin diagnostic_mode<=command_bytes[1:0];reply(OK);end
            CMD_AWG_BEGIN:if(!SUPPORT_AWG)reply(ERR_UNKNOWN);
              else if(command.length!=4)reply(ERR_LENGTH);
              else if(dds_enable || capture_busy || acquire_enable)reply(ERR_BUSY);
              else if(command_bytes[31:0]!=32'd1024)reply(ERR_CONFIG);
              else begin awg_uploading<=1;awg_received<=0;awg_crc<=16'hffff;reply(OK);end
            CMD_AWG_CHUNK:if(!SUPPORT_AWG)reply(ERR_UNKNOWN);
              else if(command.length<4 || command.length>514 || command.length[0])reply(ERR_LENGTH);
              else if(dds_enable || capture_busy || acquire_enable)reply(ERR_BUSY);
              else if(!awg_uploading || command_bytes[15:0]!={5'd0,awg_received} ||
                {1'b0,awg_received}+((command.length-16'd2)>>1)>16'd1024)reply(ERR_CONFIG);
              else begin position<=2;state<=AWG_VALIDATE;end
            CMD_AWG_COMMIT:if(!SUPPORT_AWG)reply(ERR_UNKNOWN);
              else if(command.length!=2)reply(ERR_LENGTH);
              else if(dds_enable || capture_busy || acquire_enable)reply(ERR_BUSY);
              else if(!awg_uploading || awg_received!=1024 || command_bytes[15:0]!=awg_crc)reply(ERR_CONFIG);
              else begin awg_bank<=!awg_bank;awg_valid<=1;awg_uploading<=0;awg_active_crc<=awg_crc;reply(OK);end
            CMD_AWG_SELECT:if(!SUPPORT_AWG)reply(ERR_UNKNOWN);
              else if(command.length!=1)reply(ERR_LENGTH);
              else if(dds_enable || capture_busy || acquire_enable)reply(ERR_BUSY);
              else if(command_bytes[7:0]>1 || (command_bytes[0] && !awg_valid))reply(ERR_CONFIG);
              else begin awg_selected<=command_bytes[0];reply(OK);end
            CMD_AWG_STATUS:if(!SUPPORT_AWG)reply(ERR_UNKNOWN);
              else if(command.length!=0)reply(ERR_LENGTH);
              else begin
                awg_status_snapshot<={32'd0,awg_crc,awg_active_crc,5'd0,awg_received,16'd1024,
                  16'd0,5'd0,awg_selected,awg_uploading,awg_valid,8'd1};
                fill_kind<=8;fill_length<=16;position<=0;response.length<=16;state<=FILL;
              end
            CMD_AWG_READ:if(!SUPPORT_AWG)reply(ERR_UNKNOWN);
              else if(command.length!=4)reply(ERR_LENGTH);
              else if(!awg_valid || command_bytes[31:16]==0 || command_bytes[31:16]>256 ||
                {1'b0,command_bytes[15:0]}+{1'b0,command_bytes[31:16]}>17'd1024)reply(ERR_CONFIG);
              else begin
                // First four payload bytes echo offset/count; table follows.
                position<=4;response.length<=4+(command_bytes[31:16]<<1);state<=AWG_READ_WAIT;
              end
            CMD_DDS:if(command.length!=16)reply(ERR_LENGTH);
              else if(command_bytes[7:0]>3 || command_bytes[15:8]>1 || command_bytes[47:16]>32'd12500000 ||
                command_bytes[95:80]>16'd16383 || $signed(command_bytes[127:96]) < -32'sd131072 || $signed(command_bytes[127:96])>32'sd131071)reply(ERR_CONFIG);
              else begin
                div_numerator<=({32'd0,command_bytes[47:16]}<<32)+64'd12500000;
                div_denominator<=64'd25000000;div_for_dds<=1;state<=DIV_START;
              end
            default:begin unknown_commands<=unknown_commands+32'd1;reply(ERR_UNKNOWN);end
          endcase
        end
        AWG_VALIDATE:begin
          if(awg_chunk_word==16'h8000)reply(ERR_CONFIG);
          else if(position==command.length-2)begin position<=2;state<=AWG_COPY;end
          else position<=position+2;
        end
        AWG_COPY:begin
          awg_crc<=crc16_byte(crc16_byte(awg_crc,awg_chunk_word[7:0]),awg_chunk_word[15:8]);
          if(position==command.length-2)begin
            awg_received<=awg_received+11'((command.length-2)>>1);reply(OK);
          end else position<=position+2;
        end
        AWG_READ_WAIT:state<=AWG_READ_STORE;
        AWG_READ_STORE:begin
          if(position==response.length-1)state<=SEND_HEADER;
          else begin position<=position+1;state<=AWG_READ_WAIT;end
        end
        DIV_START:state<=DIV_WAIT;
        DIV_WAIT:if(div_done)begin
          if(div_for_dds)begin
            dds_frequency_hz<=command_bytes[47:16];
            dds_phase_inc<=quotient[31:0];dds_wave<=dds_wave_t'(command_bytes[1:0]);dds_enable<=command_bytes[8];
            dds_phase_offset<=command_bytes[79:48];dds_amplitude<=command_bytes[95:80];dds_dc_offset<=$signed(command_bytes[113:96]);
          end else begin record_length<=command_bytes[17:0];pre_samples<=quotient[17:0];end
          reply(OK);
        end
        WAIT_CAPTURE:if(capture_ready)begin acquire_enable<=1;single_pulse<=1;reply(OK);end
          else if(start_wait==32'd99999)reply(ERR_BUSY);else start_wait<=start_wait+32'd1;
        FILL:begin if(position==fill_length-16'd1)state<=SEND_HEADER;else position<=position+16'd1;end
        SEND_HEADER:if(response_ready)begin send_position<=0;state<=response.length==16'd0 ?WAIT_PACKET:SEND_PAYLOAD;end
        SEND_PAYLOAD:if(response_payload_ready)begin
          if(send_position==response.length-16'd1)state<=WAIT_PACKET;else send_position<=send_position+16'd1;
        end
        WAIT_PACKET:if(response_done)state<=IDLE;
        default:state<=IDLE;
      endcase
    end
  end
endmodule
`default_nettype wire

