`default_nettype none
module adc_capture (
  input wire logic clk_sample,
  input wire logic rst,
  input wire logic capture_enable,
  input wire scope_pkg::adc_raw_t adc_data,
  input wire logic adc_otr,
  output logic sample_valid,
  output wire scope_pkg::adc_raw_t sample_raw,
  output wire scope_pkg::adc_sample_t sample_signed,
  output wire logic sample_otr,
  output scope_pkg::sample_timestamp_t sample_timestamp
);
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;
  localparam int unsigned WARM_WIDTH = $clog2(ADC_SAMPLE_LATENCY_CYCLES + 32'd1);
  typedef logic [WARM_WIDTH-1:0] warm_count_t;
  localparam warm_count_t WARM_DONE = warm_count_t'(ADC_SAMPLE_LATENCY_CYCLES);
  localparam sample_timestamp_t LATENCY = sample_timestamp_t'(ADC_SAMPLE_LATENCY_CYCLES);
  warm_count_t warm_count;
  sample_timestamp_t edge_counter;
  // These are the actual first-stage input registers, not a second pipeline.
  // Keep the existing reset, clock enable, sample latency and timestamp contract.
  (* IOB="TRUE" *) adc_raw_t raw_iob;
  (* IOB="TRUE" *) logic otr_iob;
  assign sample_raw=raw_iob;
  assign sample_otr=otr_iob;

  // Same rising-edge domain as the ADC clock source. At edge n this reads
  // the previous settled bus, before the ADC's positive clock-to-out delay.
  // High-active synchronous reset. No register simulation initial values.
  always_ff @(posedge clk_sample) begin
    if (rst) begin
      sample_valid <= 1'b0;
      raw_iob <= 12'd2047;
      otr_iob <= 1'b0;
      sample_timestamp <= sample_timestamp_t'('0);
      edge_counter <= sample_timestamp_t'('0);
      warm_count <= warm_count_t'('0);
    end else begin
      edge_counter <= edge_counter + sample_timestamp_t'(1'b1);
      if (warm_count != WARM_DONE) warm_count <= warm_count + warm_count_t'(1'b1);
      sample_valid <= capture_enable && (warm_count == WARM_DONE);
      if (capture_enable && (warm_count == WARM_DONE)) begin
        raw_iob <= adc_data;
        otr_iob <= adc_otr;
        // Source sample n appears on the ADC bus at n+7 and is captured at
        // n+8. Unsigned 64-bit subtraction intentionally wraps modulo 2^64.
        sample_timestamp <= edge_counter - LATENCY;
      end
    end
  end
  // Combinational decode of the registered raw word adds no capture cycle.
  assign sample_signed = adc_raw_to_signed(sample_raw);
endmodule : adc_capture
`default_nettype wire
