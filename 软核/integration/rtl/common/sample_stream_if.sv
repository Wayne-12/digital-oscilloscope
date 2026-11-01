`default_nettype none
interface sample_stream_if;
  timeunit 1ns;
  timeprecision 1ps;

  // All signals belong to one sampling clock domain supplied by the modules.
  // Transfer at rising edge iff sample_valid && sample_ready.
  // Producer holds valid and all payload fields stable while stalled.
  // This interface contains no state and implements neither reset nor CDC.
  logic sample_valid;
  logic sample_ready;
  scope_pkg::adc_raw_t sample_raw;
  scope_pkg::adc_sample_t sample_signed;
  logic sample_otr;
  scope_pkg::sample_timestamp_t sample_timestamp;

  modport producer (
    output sample_valid, sample_raw, sample_signed, sample_otr, sample_timestamp,
    input sample_ready
  );
  modport consumer (
    input sample_valid, sample_raw, sample_signed, sample_otr, sample_timestamp,
    output sample_ready
  );
  modport monitor (
    input sample_valid, sample_ready, sample_raw, sample_signed, sample_otr,
          sample_timestamp
  );
endinterface : sample_stream_if
`default_nettype wire
