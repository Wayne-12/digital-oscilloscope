`default_nettype none
module tb_scope_pkg;
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;

  int unsigned checks;
  int unsigned transactions;
  int unsigned seed;
  int unsigned rng_state;
  int unsigned random_cases;
  logic [31:0] random_word;
  logic allow_transfer;
  sample_payload_t observed_payload;
  sample_word_t observed_word;
  sample_stream_if stream();

  scope_pkg_import_probe import_probe (
    .allow_transfer(allow_transfer),
    .samples(stream),
    .observed_payload(observed_payload),
    .observed_word(observed_word)
  );

  task automatic expect_equal(
    input string label_text,
    input int signed actual,
    input int signed expected
  );
    checks = checks + 32'd1;
    assert (actual === expected)
      else $fatal(1, "TEST_FAIL %s actual=%0d expected=%0d seed=%0d time=%0t",
                  label_text, actual, expected, seed, $time);
  endtask

  // Independent arithmetic oracle: do not call package conversion helpers
  // or reuse a package struct to construct the expected storage word.
  task automatic scoreboard(
    input adc_raw_t raw_code,
    input logic otr
  );
    int signed raw_value;
    int signed expected_signed;
    int signed expected_word;
    adc_sample_t actual_signed;
    sample_word_t actual_word;
    sample_record_t decoded;

    raw_value = int'({1'b0, raw_code});
    expected_signed = 32'sd2047 - raw_value;
    expected_word = raw_value + (otr ? 32'sd32768 : 32'sd0);
    actual_signed = adc_raw_to_signed(raw_code);
    actual_word = pack_sample(raw_code, otr);
    decoded = unpack_sample(actual_word);

    expect_equal("signed conversion", int'($signed(actual_signed)), expected_signed);
    expect_equal("storage layout", int'({1'b0, actual_word}), expected_word);
    expect_equal("raw round trip", int'({1'b0, decoded.raw_code}), raw_value);
    expect_equal("OTR round trip", int'({1'b0, decoded.otr}), int'({1'b0, otr}));
    expect_equal("reserved bits zero", int'({1'b0, decoded.reserved}), 32'sd0);
    transactions = transactions + 32'd1;
  endtask

  initial begin : run_test
    checks = 32'd0;
    transactions = 32'd0;
    seed = 32'd20261020;
    random_cases = 32'd1000;
    allow_transfer = 1'b0;
    stream.sample_valid = 1'b0;
    stream.sample_raw = 12'd0;
    stream.sample_signed = 13'sd0;
    stream.sample_otr = 1'b0;
    stream.sample_timestamp = 64'd0;
    if ($value$plusargs("SEED=%d", seed)) begin end
    if ($value$plusargs("RANDOM_CASES=%d", random_cases)) begin end
    assert (random_cases <= 32'd10000)
      else $fatal(1, "TEST_FAIL RANDOM_CASES must be <= 10000");
    rng_state = seed;
    random_word = $urandom(rng_state);
    $display("TEST_BEGIN tb_scope_pkg seed=%0d random_cases=%0d", seed, random_cases);

    expect_equal("system clock Hz", int'(SYS_CLK_HZ), 32'sd100000000);
    expect_equal("10 MSPS", int'(adc_rate_hz(ADC_RATE_10M)), 32'sd10000000);
    expect_equal("25 MSPS", int'(adc_rate_hz(ADC_RATE_25M)), 32'sd25000000);
    expect_equal("50 MSPS", int'(adc_rate_hz(ADC_RATE_50M)), 32'sd50000000);
    expect_equal("65 MSPS", int'(adc_rate_hz(ADC_RATE_65M)), 32'sd65000000);
    expect_equal("default rate", int'(ADC_RATE_DEFAULT), int'(ADC_RATE_25M));
    expect_equal("default rate Hz", int'(ADC_SAMPLE_RATE_DEFAULT_HZ),
                 int'(adc_rate_hz(ADC_RATE_DEFAULT)));
    expect_equal("ADC raw width", $bits(adc_raw_t), 32'sd12);
    expect_equal("ADC signed width", $bits(adc_sample_t), 32'sd13);
    expect_equal("sample timestamp width", $bits(sample_timestamp_t), 32'sd64);
    expect_equal("stream payload width", $bits(sample_payload_t), 32'sd90);
    expect_equal("DAC width", $bits(dac_code_t), 32'sd14);
    expect_equal("DAC middle code", int'(DAC_MID_CODE), 32'sd8192);
    expect_equal("ADC pipeline cycles", int'(ADC_PIPELINE_CYCLES), 32'sd7);
    expect_equal("ADC settle cycles", int'(ADC_CLOCK_SETTLE_CYCLES), 32'sd256);
    expect_equal("DAC init edges", int'(DAC_INIT_CLOCK_EDGES), 32'sd16);
    expect_equal("record width", $bits(sample_record_t), 32'sd16);
    expect_equal("sample word width", $bits(sample_word_t), $bits(sample_record_t));
    expect_equal("BRAM depth", int'(BRAM_DEPTH), 32'sd16384);
    expect_equal("BRAM data width", int'(BRAM_DATA_WIDTH), 32'sd16);
    expect_equal("BRAM address width", $bits(bram_addr_t), 32'sd14);
    expect_equal("UART baud", int'(UART_BAUD_DEFAULT), 32'sd115200);
    expect_equal("UART data bits", int'(UART_DATA_BITS), 32'sd8);
    expect_equal("UART parity disabled", int'(UART_PARITY_ENABLE), 32'sd0);
    expect_equal("UART stop bits", int'(UART_STOP_BITS), 32'sd1);
    expect_equal("envelope columns", int'(ENVELOPE_COLUMNS), 32'sd800);
    expect_equal("FFT default", int'(FFT_POINTS_DEFAULT), 32'sd1024);
    $display("TEST_CASE_PASS constants_and_types");

    expect_equal("default polarity", int'(ADC_INVERT_DEFAULT), 32'sd1);
    expect_equal("default raw 0", int'(adc_raw_to_signed(12'd0)), 32'sd2047);
    expect_equal("default raw 2047", int'(adc_raw_to_signed(12'd2047)), 32'sd0);
    expect_equal("default raw 2048", int'(adc_raw_to_signed(12'd2048)), -32'sd1);
    expect_equal("default raw 4095", int'(adc_raw_to_signed(12'd4095)), -32'sd2048);
    $display("TEST_CASE_PASS default_polarity_and_boundaries");

    for (int unsigned raw_index = 32'd0; raw_index < 32'd4096; raw_index++) begin
      for (int unsigned flags = 32'd0; flags < 32'd2; flags++) begin
        scoreboard(adc_raw_t'(raw_index), flags[0]);
        #1ns;
      end
    end
    expect_equal("exhaustive transaction count", int'(transactions), 32'sd8192);
    $display("TEST_CASE_PASS exhaustive_raw_x_otr transactions=%0d", transactions);

    for (int unsigned index = 32'd0; index < random_cases; index++) begin
      random_word = $urandom();
      scoreboard(adc_raw_t'(random_word[11:0]), random_word[12]);
      #1ns;
    end
    expect_equal("total transaction count", int'(transactions),
                 32'sd8192 + int'(random_cases));
    $display("TEST_CASE_PASS seeded_random cases=%0d seed=%0d", random_cases, seed);

    // Exercise the public interface through a separately compiled RTL-style
    // consumer. All four ready/valid states and all 64 timestamp bits matter.
    for (int unsigned flags = 32'd0; flags < 32'd4; flags++) begin
      allow_transfer = flags[0];
      stream.sample_valid = flags[1];
      stream.sample_raw = 12'd4095;
      stream.sample_signed = adc_raw_to_signed(12'd4095);
      stream.sample_otr = 1'b1;
      stream.sample_timestamp = 64'hFEDC_BA98_7654_3210;
      #1ns;
      expect_equal("interface ready", int'(stream.sample_ready), int'(flags[0]));
      expect_equal("interface valid", int'(stream.sample_valid), int'(flags[1]));
      expect_equal("interface raw", int'(observed_payload.sample_raw), 32'sd4095);
      expect_equal("interface signed", int'(observed_payload.sample_signed), -32'sd2048);
      expect_equal("interface OTR", int'(observed_payload.sample_otr), 32'sd1);
      expect_equal("interface storage", int'(observed_word), 32'sd36863);
      checks = checks + 32'd1;
      assert (observed_payload.sample_timestamp === 64'hFEDC_BA98_7654_3210)
        else $fatal(1, "TEST_FAIL 64-bit timestamp truncated");
    end
    $display("TEST_CASE_PASS rtl_and_testbench_import_and_stream_types");
    $display("TEST_PASS tb_scope_pkg seed=%0d transactions=%0d checks=%0d",
             seed, transactions, checks);
    $finish;
  end

  initial begin : watchdog
    #100us;
    $fatal(1, "TEST_FAIL watchdog timeout");
  end
endmodule : tb_scope_pkg
`default_nettype wire
