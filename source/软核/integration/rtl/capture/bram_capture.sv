`default_nettype none
module bram_capture #(parameter bit USE_EXTENDED_TRIGGER=1'b0) (
  input wire logic clk_adc, rst_adc, module_enable, arm,
  input wire scope_pkg::capture_mode_t cfg_mode,
  input wire logic cfg_rising,
  input wire scope_pkg::adc_sample_t cfg_threshold,
  input wire logic [12:0] cfg_hysteresis,
  input wire logic [14:0] cfg_pre_samples,
  input wire logic [31:0] cfg_auto_timeout,
  input wire scope_pkg::trigger_config_t cfg_trigger,
  input wire logic sample_valid,
  input wire scope_pkg::adc_raw_t sample_raw,
  input wire logic sample_otr,
  input wire scope_pkg::sample_timestamp_t sample_timestamp,
  output scope_pkg::capture_state_t capture_state,
  output logic single_done, capture_error,
  output wire logic busy,
  output scope_pkg::bram_addr_t write_pointer,
  input wire logic clk_sys, rst_sys, read_request, frame_release,
  input wire scope_pkg::bram_addr_t read_index,
  output logic frame_ready, read_valid,
  output scope_pkg::capture_metadata_t frame_metadata,
  output wire scope_pkg::sample_word_t read_word,
  output wire scope_pkg::adc_sample_t read_signed,
  output scope_pkg::sample_timestamp_t read_timestamp
);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  capture_mode_t mode_reg;
  trigger_config_t trigger_reg;
  logic rising_reg;
  adc_sample_t threshold_reg;
  logic [12:0] hysteresis_reg;
  logic [14:0] pre_reg,post_reg,history_count,post_remaining;
  logic [31:0] timeout_reg,wait_count;
  logic have_previous;
  sample_timestamp_t previous_timestamp;
  capture_metadata_t metadata_adc;
  logic request_toggle,acknowledge_toggle,seen_toggle;
  (* ASYNC_REG="TRUE" *) logic request_meta,request_sync;
  (* ASYNC_REG="TRUE" *) logic ack_meta,ack_sync;
  wire logic edge_hit,edge_qualified;
  wire logic timestamp_gap=sample_valid && have_previous &&
      sample_timestamp!=(previous_timestamp+64'd1);
  wire logic eligible=(history_count>=pre_reg);
  wire logic auto_due=(mode_reg==CAP_AUTO) && eligible && (wait_count==timeout_reg-32'd1);
  wire logic accept_trigger=eligible && (edge_hit || auto_due);
  wire logic config_valid=(cfg_pre_samples<15'd16384) &&
    (cfg_mode==CAP_AUTO || cfg_mode==CAP_NORMAL || cfg_mode==CAP_SINGLE) &&
    (cfg_mode!=CAP_AUTO || cfg_auto_timeout!=32'd0) &&
    (!USE_EXTENDED_TRIGGER || trigger_config_valid(cfg_trigger));
  wire logic ram_write_enable=!rst_adc && module_enable && sample_valid && !timestamp_gap &&
    (capture_state==CAP_ARMED || capture_state==CAP_POST);
  wire logic ram_read_enable=!rst_sys && frame_ready && read_request && !frame_release;
  bram_addr_t physical_read_address;
  sample_word_t ram_read_word;
  assign busy=(capture_state==CAP_ARMED || capture_state==CAP_POST);
  assign physical_read_address=frame_metadata.start_address+read_index;
  assign read_word=read_valid ? ram_read_word : 16'h07ff;
  assign read_signed=adc_raw_to_signed(read_word[11:0]);
  generate if(!USE_EXTENDED_TRIGGER)begin:legacy
    trigger_edge detector(.clk(clk_adc),.rst(rst_adc),
    .enable(module_enable && capture_state==CAP_ARMED),.sample_valid(sample_valid),
    .rising(rising_reg),.sample_signed(adc_raw_to_signed(sample_raw)),
    .threshold(threshold_reg),.hysteresis(hysteresis_reg),.trigger_hit(edge_hit),.qualified(edge_qualified));
  end else begin:extended
    wire logic config_error, timestamp_error;
    trigger_core detector(.clk(clk_adc),.rst(rst_adc),
      .enable(module_enable && capture_state==CAP_ARMED),.sample_valid(sample_valid),
      .config_in(trigger_reg),.sample_signed(adc_raw_to_signed(sample_raw)),
      .sample_otr(sample_otr),.sample_timestamp(sample_timestamp),.trigger_hit(edge_hit),
      .config_error(config_error),.timestamp_error(timestamp_error));
    assign edge_qualified=1'b0;
  end endgenerate
  capture_bram storage(.write_clk(clk_adc),.write_enable(ram_write_enable),
    .write_address(write_pointer),.write_word(pack_sample(sample_raw,sample_otr)),
    .read_clk(clk_sys),.read_enable(ram_read_enable),.read_address(physical_read_address),.read_word(ram_read_word));

  // One outstanding frozen frame. Metadata is bundled stable data; the single
  // request bit traverses two synchronizer stages before the receiver latches
  // it. Source bus and RAM remain immutable until release returns through ACK.
  always_ff @(posedge clk_adc)begin
    if(rst_adc)begin ack_meta<=1'b0;ack_sync<=1'b0;end
    else begin ack_meta<=acknowledge_toggle;ack_sync<=ack_meta;end
  end
  always_ff @(posedge clk_sys)begin
    if(rst_sys)begin request_meta<=1'b0;request_sync<=1'b0;end
    else begin request_meta<=request_toggle;request_sync<=request_meta;end
  end
  always_ff @(posedge clk_sys)begin
    if(rst_sys)begin
      seen_toggle<=1'b0;acknowledge_toggle<=1'b0;frame_ready<=1'b0;
      frame_metadata<='0;read_valid<=1'b0;read_timestamp<=64'd0;
    end else begin
      read_valid<=ram_read_enable;
      if(ram_read_enable)read_timestamp<=frame_metadata.first_timestamp+{{50{1'b0}},read_index};
      if(frame_ready && frame_release)begin
        frame_ready<=1'b0;read_valid<=1'b0;acknowledge_toggle<=seen_toggle;
      end
      if(request_sync!=seen_toggle)begin
        frame_metadata<=metadata_adc;frame_ready<=1'b1;seen_toggle<=request_sync;
      end
    end
  end

  always_ff @(posedge clk_adc)begin
    if(rst_adc)begin
      capture_state<=CAP_IDLE;write_pointer<=14'd0;history_count<=15'd0;
      post_remaining<=15'd0;wait_count<=32'd0;have_previous<=1'b0;previous_timestamp<=64'd0;
      mode_reg<=CAP_SINGLE;rising_reg<=1'b1;threshold_reg<=13'sd0;hysteresis_reg<=13'd0;
      pre_reg<=15'd0;post_reg<=15'd16383;timeout_reg<=32'd1;
      trigger_reg<='0;metadata_adc<='0;request_toggle<=1'b0;single_done<=1'b0;capture_error<=1'b0;
    end else begin
      case(capture_state)
        CAP_IDLE,CAP_SINGLE_HOLD: begin
          if(arm && module_enable)begin
            if(config_valid)begin
              trigger_reg<=cfg_trigger;
              mode_reg<=cfg_mode;rising_reg<=cfg_rising;threshold_reg<=cfg_threshold;
              hysteresis_reg<=cfg_hysteresis;pre_reg<=cfg_pre_samples;
              post_reg<=15'd16383-cfg_pre_samples;timeout_reg<=cfg_auto_timeout;
              write_pointer<=14'd0;history_count<=15'd0;post_remaining<=15'd0;
              wait_count<=32'd0;have_previous<=1'b0;single_done<=1'b0;capture_error<=1'b0;
              capture_state<=CAP_ARMED;
            end else capture_error<=1'b1;
          end
        end
        CAP_ARMED,CAP_POST: begin
          if(!module_enable || timestamp_gap)begin
            capture_state<=CAP_IDLE;have_previous<=1'b0;history_count<=15'd0;
            if(timestamp_gap && module_enable)capture_error<=1'b1;
          end else if(sample_valid)begin
            write_pointer<=write_pointer+14'd1;
            previous_timestamp<=sample_timestamp;have_previous<=1'b1;
            if(history_count<15'd16384)history_count<=history_count+15'd1;
            if(capture_state==CAP_ARMED)begin
              if(accept_trigger)begin
                metadata_adc.start_address<=write_pointer-pre_reg[13:0];
                metadata_adc.trigger_address<=write_pointer;metadata_adc.trigger_index<=pre_reg[13:0];
                metadata_adc.frame_length<=15'd16384;metadata_adc.pre_samples<=pre_reg;
                metadata_adc.post_samples<=post_reg;metadata_adc.first_timestamp<=sample_timestamp-{{49{1'b0}},pre_reg};
                metadata_adc.trigger_timestamp<=sample_timestamp;
                metadata_adc.last_timestamp<=sample_timestamp+{{49{1'b0}},post_reg};
                metadata_adc.automatic_trigger<=auto_due && !edge_hit;
                metadata_adc.rising<=rising_reg;metadata_adc.mode<=mode_reg;
                metadata_adc.threshold<=threshold_reg;metadata_adc.hysteresis<=hysteresis_reg;
                metadata_adc.extended_trigger<=USE_EXTENDED_TRIGGER;
                metadata_adc.trigger_config<=USE_EXTENDED_TRIGGER?trigger_reg:trigger_config_t'('0);
                post_remaining<=post_reg;
                if(post_reg==15'd0)begin
                  capture_state<=CAP_FROZEN;request_toggle<=!request_toggle;
                  if(mode_reg==CAP_SINGLE)single_done<=1'b1;
                end else capture_state<=CAP_POST;
              end else if(eligible && mode_reg==CAP_AUTO)wait_count<=wait_count+32'd1;
            end else begin
              if(post_remaining==15'd1)begin
                capture_state<=CAP_FROZEN;request_toggle<=!request_toggle;
                metadata_adc.last_timestamp<=sample_timestamp;
                if(mode_reg==CAP_SINGLE)single_done<=1'b1;
              end else post_remaining<=post_remaining-15'd1;
            end
          end
        end
        CAP_FROZEN: begin
          if(ack_sync==request_toggle)begin
            if(mode_reg==CAP_SINGLE)capture_state<=CAP_SINGLE_HOLD;
            else if(module_enable)begin
              capture_state<=CAP_ARMED;write_pointer<=14'd0;history_count<=15'd0;
              wait_count<=32'd0;have_previous<=1'b0;
            end else capture_state<=CAP_IDLE;
          end
        end
        default: begin capture_state<=CAP_IDLE;capture_error<=1'b1;end
      endcase
    end
  end
endmodule
`default_nettype wire
