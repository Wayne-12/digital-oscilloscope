`default_nettype none
package innovation_pkg;
  timeunit 1ns;timeprecision 1ps;
  typedef struct packed {
    logic valid;
    logic signed [31:0] gain_q20,offset_q16;
    logic [63:0] zero_variance_q16;
    logic [31:0] compression_loss_ppm,harmonic_power_ppm,otr_count;
  } health_fingerprint_t;
  typedef struct packed {
    logic [31:0] zero_limit_q16,gain_limit_q20;
    logic [63:0] noise_rise_limit_q16;
    logic [31:0] compression_limit_ppm,harmonic_limit_ppm,otr_extra_limit;
  } health_limits_t;
  typedef enum logic [3:0] {HEALTH_OK,HEALTH_ZERO,HEALTH_GAIN,HEALTH_NOISE,
    HEALTH_CLIP,HEALTH_HARMONIC,HEALTH_POLARITY,HEALTH_INVALID} health_class_t;
  typedef struct packed {
    logic [17:0] count,otr_count;
    logic signed [63:0] sum;
    logic [63:0] square_sum;
    logic signed [12:0] minimum,maximum;
    logic [63:0] first_timestamp,last_timestamp;
    logic [31:0] raw_crc32;
  } capture_moments_t;
  typedef struct packed {
    logic [31:0] result_id;
    logic reserved_storage;
    logic [17:0] sample_count,trigger_index,roi_start;
    logic [11:0] roi_count;
    logic [9:0] bucket_count;
    logic [31:0] sample_rate;
    capture_moments_t moments;
  } capture_result_meta_t;
endpackage
`default_nettype wire
