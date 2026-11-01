`default_nettype none
// Verification-only combinational consumer: checks package use from RTL-style
// typed ANSI ports, an interface modport, and module-local import together.
module scope_pkg_import_probe (
  input wire logic allow_transfer,
  sample_stream_if.consumer samples,
  output wire scope_pkg::sample_payload_t observed_payload,
  output wire scope_pkg::sample_word_t observed_word
);
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;

  assign samples.sample_ready = allow_transfer;
  assign observed_payload = sample_payload_t'({
    samples.sample_raw, samples.sample_signed, samples.sample_otr,
    samples.sample_timestamp
  });
  assign observed_word = pack_sample(samples.sample_raw, samples.sample_otr);
endmodule : scope_pkg_import_probe
`default_nettype wire
