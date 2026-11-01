`default_nettype none
package multires_pkg;
  timeunit 1ns;timeprecision 1ps;
  typedef logic [17:0] frame_index_t; // 18 bits; range-check before narrowing.
  typedef struct packed {
    frame_index_t sample_count,trigger_index;
    logic [9:0] requested_buckets,effective_buckets;
    frame_index_t roi_start;
    logic [11:0] roi_count,roi_trigger_index;
    scope_pkg::sample_timestamp_t first_timestamp;
    logic [31:0] sample_rate;
  } envelope_metadata_t;
  typedef struct packed {
    logic [9:0] bucket_index;
    frame_index_t first_index,last_index,sample_count;
    scope_pkg::adc_sample_t minimum,maximum;
    frame_index_t minimum_index,maximum_index;
    logic otr; // OR of OTR over every sample in this bucket.
  } envelope_bucket_t;
  typedef struct packed {
    logic [11:0] roi_index;
    frame_index_t frame_index;
    scope_pkg::sample_word_t raw_word;
    scope_pkg::adc_sample_t signed_sample;
    scope_pkg::sample_timestamp_t timestamp;
  } envelope_roi_t;
endpackage
`default_nettype wire
