`default_nettype none
package scope_pkg;
  timeunit 1ns;
  timeprecision 1ps;

  // Compile-time contract. Rate selection does not implement clock switching.
  localparam int unsigned SYS_CLK_HZ = 100_000_000;
  localparam int unsigned ADC_RATE_10M_HZ = 10_000_000;
  localparam int unsigned ADC_RATE_25M_HZ = 25_000_000;
  localparam int unsigned ADC_RATE_50M_HZ = 50_000_000;
  localparam int unsigned ADC_RATE_65M_HZ = 65_000_000;

  typedef enum logic [1:0] {
    ADC_RATE_10M = 2'd0,
    ADC_RATE_25M = 2'd1,
    ADC_RATE_50M = 2'd2,
    ADC_RATE_65M = 2'd3
  } adc_rate_t;

  localparam adc_rate_t ADC_RATE_DEFAULT = ADC_RATE_25M;
  localparam int unsigned ADC_SAMPLE_RATE_DEFAULT_HZ = ADC_RATE_25M_HZ;

  localparam int unsigned ADC_DATA_WIDTH = 12;
  localparam int unsigned ADC_SIGNED_WIDTH = 13;
  localparam bit ADC_INVERT_DEFAULT = 1'b1;
  localparam int unsigned ADC_PIPELINE_CYCLES = 7;
  localparam int unsigned ADC_CAPTURE_EXTRA_CYCLES = 1;
  localparam int unsigned ADC_SAMPLE_LATENCY_CYCLES = ADC_PIPELINE_CYCLES + ADC_CAPTURE_EXTRA_CYCLES;
  localparam int unsigned ADC_CLOCK_SETTLE_CYCLES = 256;
  localparam int unsigned DAC_DATA_WIDTH = 14;
  localparam int unsigned DAC_INIT_CLOCK_EDGES = 16;
  localparam int unsigned DDS_PHASE_WIDTH = 32;
  localparam int unsigned DDS_LUT_POINTS = 1024;
  localparam int unsigned DAC_SAMPLE_RATE_DEFAULT_HZ = 25_000_000;
  typedef enum logic [1:0] {
    DDS_SINE = 2'd0, DDS_SQUARE = 2'd1,
    DDS_TRIANGLE = 2'd2, DDS_DC = 2'd3
  } dds_wave_t;


  typedef enum logic [3:0] {
    SAFE_HIZ = 4'd0,
    DAC_MID_ENABLE = 4'd1,
    DAC_CLOCK_16_EDGES = 4'd2,
    ADC_CLOCK_ENABLE = 4'd3,
    ADC_STABILIZE_256_EDGES = 4'd4,
    RUN = 4'd5,
    STOP_CAPTURE = 4'd6,
    STOP_ADC_CLOCK = 4'd7,
    STOP_DAC_CLOCK = 4'd8,
    RELEASE_OUTPUTS = 4'd9
  } safe_state_t;
  localparam int unsigned SAFE_STATE_COUNT = 10;

  localparam int unsigned SAMPLE_WORD_WIDTH = 16;
  localparam int unsigned SAMPLE_RESERVED_WIDTH = 3;
  localparam int unsigned SAMPLE_TIMESTAMP_WIDTH = 64;
  localparam int unsigned BRAM_DEPTH = 16_384;
  localparam int unsigned BRAM_DATA_WIDTH = SAMPLE_WORD_WIDTH;
  localparam int unsigned BRAM_ADDR_WIDTH = $clog2(BRAM_DEPTH);

  localparam int unsigned UART_BAUD_DEFAULT = 115_200;
  localparam int unsigned UART_DATA_BITS = 8;
  localparam int unsigned UART_STOP_BITS = 1;
  localparam bit UART_PARITY_ENABLE = 1'b0;
  localparam int unsigned ENVELOPE_COLUMNS = 800;
  localparam int unsigned FFT_POINTS_DEFAULT = 1_024;

  typedef logic [ADC_DATA_WIDTH-1:0] adc_raw_t;
  typedef logic signed [ADC_SIGNED_WIDTH-1:0] adc_sample_t;
  typedef logic [DAC_DATA_WIDTH-1:0] dac_code_t;
  typedef logic [SAMPLE_WORD_WIDTH-1:0] sample_word_t;
  typedef logic [BRAM_ADDR_WIDTH-1:0] bram_addr_t;
  typedef logic [SAMPLE_TIMESTAMP_WIDTH-1:0] sample_timestamp_t;

  localparam adc_raw_t ADC_MID_CODE = 12'd2048;
  localparam adc_raw_t ADC_RAW_MAX = 12'hFFF;
  localparam dac_code_t DAC_MID_CODE = 14'd8192;

  // Packed order is MSB first: [15] OTR, [14:12] zero, [11:0] raw ADC.
  // The signed display/algorithm value must never replace stored raw_code.
  typedef struct packed {
    logic otr;
    logic [SAMPLE_RESERVED_WIDTH-1:0] reserved;
    adc_raw_t raw_code;
  } sample_record_t;

  // Stream payload is distinct from the 16-bit raw storage word.
  // valid and ready are separate handshake controls, not stored payload bits.
  typedef struct packed {
    adc_raw_t sample_raw;
    adc_sample_t sample_signed;
    logic sample_otr;
    sample_timestamp_t sample_timestamp;
  } sample_payload_t;

  // Capture frame contains pre + trigger sample + post = BRAM_DEPTH.
  typedef enum logic [1:0] {
    CAP_AUTO=2'd0, CAP_NORMAL=2'd1, CAP_SINGLE=2'd2
  } capture_mode_t;
  typedef enum logic [2:0] {
    CAP_IDLE=3'd0, CAP_ARMED=3'd1, CAP_POST=3'd2,
    CAP_FROZEN=3'd3, CAP_SINGLE_HOLD=3'd4
  } capture_state_t;
  typedef enum logic [3:0] {
    TRIG_RISE=4'd0, TRIG_FALL=4'd1, TRIG_WINDOW_ENTER=4'd2,
    TRIG_WINDOW_LEAVE=4'd3, TRIG_POS_WIDTH=4'd4, TRIG_NEG_WIDTH=4'd5,
    TRIG_UNDER_AMPLITUDE=4'd6, TRIG_OVER_AMPLITUDE=4'd7, TRIG_OTR=4'd8
  } trigger_type_t;
  typedef struct packed {
    trigger_type_t kind;
    adc_sample_t threshold;
    logic [12:0] hysteresis;
    adc_sample_t window_low, window_high;
    logic [31:0] width_min, width_max; // Inclusive, ADC timestamp ticks.
    logic [13:0] amplitude_limit;     // Peak-to-peak LSB, strict comparison.
    logic [14:0] observation_samples; // Nonoverlapping accepted-sample blocks.
  } trigger_config_t;
  function automatic logic trigger_config_valid(input trigger_config_t c);
    logic signed [14:0] lo, hi, h;
    lo=$signed({{2{c.window_low[12]}},c.window_low});
    hi=$signed({{2{c.window_high[12]}},c.window_high});
    h=$signed({2'b00,c.hysteresis});
    if(c.kind>TRIG_OTR) return 1'b0;
    case(c.kind)
      TRIG_WINDOW_ENTER,TRIG_WINDOW_LEAVE: return (lo+h)<(hi-h);
      TRIG_POS_WIDTH,TRIG_NEG_WIDTH: return c.width_min!=32'd0 && c.width_max>=c.width_min;
      TRIG_UNDER_AMPLITUDE,TRIG_OVER_AMPLITUDE:
        return c.observation_samples>=15'd2 && c.observation_samples<=15'd16384;
      default: return 1'b1;
    endcase
  endfunction
  // Stats use all signed-13-bit inputs [-4096,4095], not just ADC's subrange.
  // Sum: 64 signed bits; square sum: 64 unsigned bits. At BRAM_DEPTH points,
  // signed 13-bit -4096 squared and summed is 2^41 (42 bits including it).
  // Integer means: nearest, ties away from zero. RMS: nearest sqrt(mean square),
  // computed without pre-rounding the mean square. Period is Q16 ADC ticks;
  // frequency is integer Hz; duty is parts per million. All round nearest.
  typedef struct packed {
    logic stats_valid, period_valid, duty_valid;
    // Keep the wire-format counter width; the active record is BRAM_DEPTH.
    logic [17:0] sample_count, period_count;
    adc_sample_t minimum, maximum;
    logic [13:0] peak_to_peak, rms;
    adc_sample_t mean;
    logic signed [63:0] sum;
    logic [63:0] square_sum;
    logic [63:0] period_q16;
    logic [31:0] frequency_hz, duty_ppm;
  } measurement_result_t;
  typedef struct packed {
    bram_addr_t start_address;
    bram_addr_t trigger_address;
    bram_addr_t trigger_index;
    logic [BRAM_ADDR_WIDTH:0] frame_length;
    logic [BRAM_ADDR_WIDTH:0] pre_samples;
    logic [BRAM_ADDR_WIDTH:0] post_samples;
    sample_timestamp_t first_timestamp;
    sample_timestamp_t trigger_timestamp;
    sample_timestamp_t last_timestamp;
    logic automatic_trigger;
    logic rising;
    capture_mode_t mode;
    adc_sample_t threshold;
    logic [ADC_SIGNED_WIDTH-1:0] hysteresis;
    logic extended_trigger;
    trigger_config_t trigger_config;
  } capture_metadata_t;

  function automatic int unsigned adc_rate_hz(input adc_rate_t rate);
    case (rate)
      ADC_RATE_10M: return ADC_RATE_10M_HZ;
      ADC_RATE_25M: return ADC_RATE_25M_HZ;
      ADC_RATE_50M: return ADC_RATE_50M_HZ;
      ADC_RATE_65M: return ADC_RATE_65M_HZ;
      default:     return 32'd0; // Invalid/X configuration, not a clock request.
    endcase
  endfunction

  // AD9226 module polarity is fixed: result = 2047 - raw_code.
  // Both operands and the result are explicitly signed 13-bit values.
  // Range is [-2048, 2047]; no truncation, scaling, saturation, or rounding.
  function automatic adc_sample_t adc_raw_to_signed(input adc_raw_t raw_code);
    return 13'sd2047 - $signed({1'b0, raw_code});
  endfunction

  function automatic sample_word_t pack_sample(
    input adc_raw_t raw_code,
    input logic otr
  );
    return sample_word_t'({otr, 3'b000, raw_code});
  endfunction

  function automatic sample_record_t unpack_sample(input sample_word_t word);
    // Preserve every received bit. Reserved-bit validation belongs to caller.
    return sample_record_t'(word);
  endfunction
  // CRC-32/ISO-HDLC: reflected polynomial, low byte of each word first.
  // Caller initializes to FFFFFFFF and complements after the final word.
  function automatic logic [31:0] crc32_word(input logic [31:0] crc,input logic [15:0] word_in);
    logic [31:0] c;
    c=crc;
    for(int unsigned b=0;b<16;b++)
      c=(c>>1)^((c[0]^word_in[b])?32'hedb88320:32'd0);
    return c;
  endfunction
endpackage : scope_pkg
`default_nettype wire
