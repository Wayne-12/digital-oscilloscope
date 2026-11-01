`default_nettype none
module scope_safe_ctrl (
  input wire logic clk,
  input wire logic rst,
  input wire logic enable_qualified,
  input wire logic clock_restart,
  output logic dac_data_oe,
  output logic dac_clk_oe,
  output logic adc_clk_oe,
  output logic capture_request,
  output scope_pkg::safe_state_t state
);
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;
  localparam int unsigned DAC_COUNT_WIDTH = $clog2(DAC_INIT_CLOCK_EDGES);
  localparam int unsigned ADC_COUNT_WIDTH = $clog2(ADC_CLOCK_SETTLE_CYCLES);
  typedef logic [DAC_COUNT_WIDTH-1:0] dac_count_t;
  typedef logic [ADC_COUNT_WIDTH-1:0] adc_count_t;
  localparam dac_count_t DAC_LAST = dac_count_t'(DAC_INIT_CLOCK_EDGES - 32'd1);
  localparam adc_count_t ADC_LAST = adc_count_t'(ADC_CLOCK_SETTLE_CYCLES - 32'd1);
  dac_count_t dac_edges;
  adc_count_t adc_edges;

  // This is the input sample clock itself, not a fabric-generated clock.
  // State/OE changes on falling edges leave the next rising edge intact.
  // Asynchronous reset assertion is reserved for reset/MMCM-loss emergencies.
  always_ff @(negedge clk or posedge rst) begin
    if (rst) begin
      state <= SAFE_HIZ;
      dac_data_oe <= 1'b0;
      dac_clk_oe <= 1'b0;
      adc_clk_oe <= 1'b0;
      capture_request <= 1'b0;
      dac_edges <= dac_count_t'('0);
      adc_edges <= adc_count_t'('0);
    end else if ((state >= DAC_MID_ENABLE && state <= RUN) &&
                 (!enable_qualified || clock_restart)) begin
      // Keep already-running clocks unchanged until their ordered stop state.
      state <= STOP_CAPTURE;
      capture_request <= 1'b0;
      dac_edges <= dac_count_t'('0);
      adc_edges <= adc_count_t'('0);
    end else begin
      case (state)
        SAFE_HIZ: begin
          dac_data_oe <= 1'b0;
          dac_clk_oe <= 1'b0;
          adc_clk_oe <= 1'b0;
          capture_request <= 1'b0;
          dac_edges <= dac_count_t'('0);
          adc_edges <= adc_count_t'('0);
          if (enable_qualified && !clock_restart) begin
            state <= DAC_MID_ENABLE;
            dac_data_oe <= 1'b1;
          end
        end
        DAC_MID_ENABLE: begin
          state <= DAC_CLOCK_16_EDGES;
          dac_clk_oe <= 1'b1;
          dac_edges <= dac_count_t'('0);
        end
        DAC_CLOCK_16_EDGES: begin
          // One real DAC rising edge occurred since the previous falling edge.
          if (dac_edges == DAC_LAST) begin
            state <= ADC_CLOCK_ENABLE;
            adc_clk_oe <= 1'b1;
            adc_edges <= adc_count_t'('0);
          end else dac_edges <= dac_edges + dac_count_t'(1'b1);
        end
        ADC_CLOCK_ENABLE: begin
          // Count the first ADC rising edge, including this explicit state.
          state <= ADC_STABILIZE_256_EDGES;
          adc_edges <= adc_count_t'(1'b1);
        end
        ADC_STABILIZE_256_EDGES: begin
          if (adc_edges == ADC_LAST) begin
            state <= RUN;
            capture_request <= 1'b1;
          end else adc_edges <= adc_edges + adc_count_t'(1'b1);
        end
        RUN: begin
          capture_request <= 1'b1;
        end
        STOP_CAPTURE: begin
          state <= STOP_ADC_CLOCK;
          adc_clk_oe <= 1'b0;
        end
        STOP_ADC_CLOCK: begin
          state <= STOP_DAC_CLOCK;
          dac_clk_oe <= 1'b0;
        end
        STOP_DAC_CLOCK: begin
          state <= RELEASE_OUTPUTS;
          dac_data_oe <= 1'b0;
        end
        RELEASE_OUTPUTS: begin
          state <= SAFE_HIZ;
        end
        default: begin
          state <= SAFE_HIZ;
          dac_data_oe <= 1'b0;
          dac_clk_oe <= 1'b0;
          adc_clk_oe <= 1'b0;
          capture_request <= 1'b0;
          dac_edges <= dac_count_t'('0);
          adc_edges <= adc_count_t'('0);
        end
      endcase
    end
  end
endmodule : scope_safe_ctrl
`default_nettype wire
