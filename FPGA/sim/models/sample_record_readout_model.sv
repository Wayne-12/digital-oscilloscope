`default_nettype none
// Verification-only record cache/readout. Not a memory controller or UART.
// Payload uses the project's real pack/decode helpers; the TB oracle uses
// independent bit positions and arithmetic. Synchronous reset invalidates count.
module sample_record_readout_model #(parameter int unsigned DEPTH=16384)(
  input wire logic clk, rst,
  input wire logic sample_valid,
  input wire scope_pkg::adc_raw_t sample_raw,
  input wire logic sample_otr,
  input wire scope_pkg::sample_timestamp_t sample_timestamp,
  input wire logic read_request,
  input wire logic [16:0] read_address,
  output logic report_valid,
  output scope_pkg::sample_word_t report_word,
  output scope_pkg::sample_timestamp_t report_timestamp,
  output wire scope_pkg::adc_sample_t report_signed,
  output integer unsigned stored_count
);
  timeunit 1ns;timeprecision 1ps;
  scope_pkg::sample_word_t words[0:DEPTH-1];
  scope_pkg::sample_timestamp_t timestamps[0:DEPTH-1];
  always @(posedge clk)begin
    if(rst)begin
      stored_count<=0;report_valid<=0;report_word<=16'h07ff;report_timestamp<=64'd0;
    end else begin
      report_valid<=read_request;
      if(sample_valid)begin
        assert(stored_count<DEPTH)else $fatal(1,"TEST_FAIL record cache overflow");
        words[stored_count]<=scope_pkg::pack_sample(sample_raw,sample_otr);
        timestamps[stored_count]<=sample_timestamp;
        stored_count<=stored_count+1;
      end
      if(read_request)begin
        assert(32'(read_address)<stored_count)else $fatal(1,"TEST_FAIL record read outside valid range");
        report_word<=words[read_address];report_timestamp<=timestamps[read_address];
      end
    end
  end
  assign report_signed=scope_pkg::adc_raw_to_signed(report_word[11:0]);
endmodule
`default_nettype wire
