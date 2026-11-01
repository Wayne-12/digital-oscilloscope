`default_nettype none
module ad9226_scenario #(
  parameter int unsigned RATE_HZ = 25_000_000,
  parameter realtime T_CO_NS = 3.5,
  parameter int unsigned PROFILE = 0,
  parameter realtime FORWARD_NS = 0.0
) (
  output logic done
);
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;
  localparam int unsigned MAX_SAMPLES = 131072;
  localparam int signed GAIN = (PROFILE == 1) ? 98304 : ((PROFILE == 4) ? 69632 : 65536);
  localparam int signed OFFSET = (PROFILE == 1) ? -3 : ((PROFILE == 4) ? 7 : 0);
  localparam int unsigned NOISE = (PROFILE == 2) ? 3 : ((PROFILE == 4) ? 2 : 0);
  localparam logic [11:0] MISSING = (PROFILE == 4) ? 12'd2040 : 12'd2048;
  localparam logic [11:0] REPLACEMENT = (PROFILE == 4) ? 12'd2041 : 12'd2049;
  wire clk_sample, adc_clk;
  logic rst, capture_enable, force_enable, force_value;
  logic signed [31:0] ideal_sample;
  logic [31:0] noise_seed;
  wire adc_raw_t model_raw, sample_raw;
  wire adc_sample_t sample_signed;
  wire model_otr, model_valid, sample_valid, sample_otr;
  wire sample_timestamp_t sample_timestamp;
  logic [63:0] stimulus[0:MAX_SAMPLES-1];
  logic [31:0] expected[0:MAX_SAMPLES-1];
  realtime sampled_at[0:MAX_SAMPLES-1], ready_at[0:MAX_SAMPLES-1];
  logic [4095:0] ramp_seen;
  int signed adc_edge, capture_edge;
  int unsigned mode, base_seed, header_seed, total, ramp_start, zero_start, random_start, random_count;
  int unsigned captured, model_checked, random_checked, random_streak, max_random_streak;
  int unsigned zero_checked, ramp_checked, missing_checked, false_high_checked, suppressed_checked;
  int signed zero_sum;
  int trace_file, metadata_file, read_count;
  string vector_dir, expected_dir, trace_dir, case_name;
  realtime last_adc_edge;

  ideal_clock clock_model (.frequency_hz(RATE_HZ), .clk(clk_sample));
  // Simulation-only forwarding phase; never added to RTL Design Sources.
  assign #(FORWARD_NS) adc_clk = clk_sample;
  ad9226_model #(.T_CO_NS(T_CO_NS), .GAIN_Q16(GAIN), .OFFSET_LSB(OFFSET),
      .NOISE_LSB(NOISE), .MISSING_CODE_ENABLE(PROFILE >= 3),
      .MISSING_CODE(MISSING), .MISSING_REPLACEMENT(REPLACEMENT)) model (
    .adc_clk(adc_clk), .rst(rst), .ideal_sample(ideal_sample), .noise_seed(noise_seed),
    .force_otr_enable(force_enable), .force_otr_value(force_value),
    .raw_code(model_raw), .otr(model_otr), .output_valid(model_valid)
  );
  adc_capture dut (.clk_sample(clk_sample), .rst(rst), .capture_enable(capture_enable),
    .adc_data(model_raw), .adc_otr(model_otr), .sample_valid(sample_valid),
    .sample_raw(sample_raw), .sample_signed(sample_signed), .sample_otr(sample_otr),
    .sample_timestamp(sample_timestamp));

  task automatic drive_sample(input int unsigned index);
    ideal_sample = $signed(stimulus[index][63:32]);
    force_enable = stimulus[index][31];
    force_value = stimulus[index][30];
  endtask

  // Independent time-indexed oracle: expected files contain integer results,
  // not another copy of the model's seven register stages or RTL decode.
  always @(posedge adc_clk) begin : model_scoreboard
    int signed index;
    adc_raw_t previous_raw;
    logic previous_otr, previous_valid;
    last_adc_edge = $realtime;
    if (rst) adc_edge = -1;
    else begin
      adc_edge++;
      if (mode == 1) begin
        if (adc_edge < int'(total)) sampled_at[adc_edge] = $realtime;
        index = adc_edge - 7;
        previous_raw = model_raw;
        previous_otr = model_otr;
        previous_valid = model_valid;
        #(T_CO_NS - 0.001);
        assert ({model_valid,model_otr,model_raw} === {previous_valid,previous_otr,previous_raw})
          else $fatal(1, "TEST_FAIL %s model changed before T_CO at ADC edge %0d", case_name, adc_edge);
        #2ps;
        assert (model_valid === (index >= 0))
          else $fatal(1, "TEST_FAIL %s model pipeline valid at edge %0d", case_name, adc_edge);
        if (index >= 0 && index < int'(total)) begin
          assert (model_raw === expected[index][11:0] && model_otr === expected[index][25])
            else $fatal(1, "TEST_FAIL %s model id=%0d raw=%0h exp=%0h OTR=%b exp=%b",
                        case_name,index,model_raw,expected[index][11:0],model_otr,expected[index][25]);
          ready_at[index] = last_adc_edge + T_CO_NS;
          model_checked++;
        end
      end
    end
  end

  always @(model_raw or model_otr or model_valid) begin
    if (mode != 0 && !rst) begin
      assert (($realtime - last_adc_edge) >= T_CO_NS - 0.0011 &&
              ($realtime - last_adc_edge) <= T_CO_NS + 0.0011)
        else $fatal(1, "TEST_FAIL %s pin update did not occur at T_CO", case_name);
    end
  end

  always @(posedge clk_sample) begin : capture_scoreboard
    int signed index, expected_signed;
    int unsigned phase;
    logic valid_expected;
    logic [31:0] word_value;
    adc_raw_t held_raw;
    logic held_otr;
    sample_timestamp_t held_timestamp;
    held_raw = sample_raw;
    held_otr = sample_otr;
    held_timestamp = sample_timestamp;
    if (rst) capture_edge = -1;
    else capture_edge++;
    valid_expected = !rst && capture_enable && capture_edge >= 8;
    index = capture_edge - 8;
    #2ps;
    if (mode != 0) begin
      assert (sample_valid === valid_expected)
        else $fatal(1, "TEST_FAIL %s capture valid edge=%0d", case_name, capture_edge);
      if (!rst && !valid_expected) begin
        assert ({sample_raw,sample_otr,sample_timestamp} === {held_raw,held_otr,held_timestamp})
          else $fatal(1, "TEST_FAIL %s invalid-cycle payload changed", case_name);
      end
    end
    if (mode == 1 && valid_expected && index >= 0 && index < int'(total)) begin
      word_value = expected[index];
      expected_signed = int'($signed(word_value[24:12]));
      assert (sample_raw === word_value[11:0] && model_raw === word_value[11:0] &&
              sample_signed === adc_sample_t'(expected_signed) && sample_otr === word_value[25])
        else $fatal(1, "TEST_FAIL %s capture id=%0d raw=%0h exp=%0h signed=%0d exp=%0d OTR=%b exp=%b",
                    case_name,index,sample_raw,word_value[11:0],sample_signed,expected_signed,sample_otr,word_value[25]);
      assert (model_valid && sample_timestamp === sample_timestamp_t'(index) &&
              ready_at[index] < $realtime && sampled_at[index] < ready_at[index])
        else $fatal(1, "TEST_FAIL %s source timestamp/extra capture edge id=%0d", case_name,index);
      phase = {29'd0,stimulus[index][29:27]};
      if (phase == 1) begin
        ramp_checked++;
        if (PROFILE == 0) begin
          assert (int'($signed(sample_signed)) == -2048 + int'(ramp_checked) - 1 &&
                  sample_raw == adc_raw_t'(4096 - ramp_checked))
            else $fatal(1, "TEST_FAIL ramp/bit order id=%0d", index);
          ramp_seen[sample_raw] = 1'b1;
        end
      end
      if (phase == 2) begin
        zero_checked++;
        zero_sum += int'($signed(sample_signed));
      end
      if (phase == 3) begin
        random_checked++;
        random_streak++;
        if (random_streak > max_random_streak) max_random_streak = random_streak;
      end else random_streak = 0;
      if (word_value[27]) missing_checked++;
      if (stimulus[index][31] && stimulus[index][30] && !word_value[26]) false_high_checked++;
      if (stimulus[index][31] && !stimulus[index][30] && word_value[26]) suppressed_checked++;
      $fdisplay(trace_file,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0.3f,%0.3f,%0.3f,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
        index,$signed(stimulus[index][63:32]),phase,index+7,index+8,stimulus[index][31],stimulus[index][30],
        sampled_at[index],ready_at[index],$realtime,word_value[11:0],model_raw,sample_raw,
        expected_signed,sample_signed,word_value[25],sample_otr,sample_timestamp,word_value[27]);
      captured++;
    end
  end

  initial begin : stimulus_and_acceptance
    done = 1'b0;
    mode = 0;
    rst = 1'b1;
    capture_enable = 1'b0;
    ideal_sample = 32'sd0;
    force_enable = 1'b0;
    force_value = 1'b0;
    adc_edge = -1;
    capture_edge = -1;
    last_adc_edge = 0.0;
    captured = 0;
    model_checked = 0;
    random_checked = 0;
    random_streak = 0;
    max_random_streak = 0;
    ramp_checked = 0;
    zero_checked = 0;
    zero_sum = 0;
    missing_checked = 0;
    false_high_checked = 0;
    suppressed_checked = 0;
    ramp_seen = '0;
    base_seed = 32'd20261020;
    if ($value$plusargs("SEED=%d", base_seed)) begin end
    assert ($value$plusargs("VECTOR_DIR=%s",vector_dir) &&
            $value$plusargs("EXPECTED_DIR=%s",expected_dir) && $value$plusargs("TRACE_DIR=%s",trace_dir))
      else $fatal(1, "TEST_FAIL missing ADC vector/expected/trace directory");
    metadata_file = $fopen({vector_dir,"/adc_meta.txt"},"r");
    assert (metadata_file != 0) else $fatal(1, "TEST_FAIL missing ADC metadata");
    read_count = $fscanf(metadata_file,"%d %d %d %d %d %d",header_seed,total,ramp_start,zero_start,random_start,random_count);
    $fclose(metadata_file);
    assert (read_count == 6 && header_seed == base_seed && total < MAX_SAMPLES &&
            random_count >= 10000 && zero_start-ramp_start == 4096 && random_start-zero_start == 256 &&
            ADC_PIPELINE_CYCLES == 7 && ADC_CAPTURE_EXTRA_CYCLES == 1 && ADC_SAMPLE_LATENCY_CYCLES == 8)
      else $fatal(1, "TEST_FAIL invalid ADC oracle contract");
    $readmemh({vector_dir,"/adc_stim.mem"},stimulus,0,total-1);
    $readmemh($sformatf("%s/adc_expected_p%0d.mem",expected_dir,PROFILE),expected,0,total-1);
    noise_seed = base_seed ^ 32'ha9226000 ^ (32'(PROFILE) * 32'h9e3779b9);
    if (noise_seed == 0) noise_seed = 32'd1;
    case_name = $sformatf("r%0d_d%0d_p%0d_f%0d",RATE_HZ,int'(T_CO_NS*1000.0),PROFILE,int'(FORWARD_NS*1000.0));
    trace_file = $fopen($sformatf("%s/%s.csv",trace_dir,case_name),"w");
    assert (trace_file != 0) else $fatal(1, "TEST_FAIL cannot create ADC trace");
    $fdisplay(trace_file,"sample_id,input_lsb,phase,adc_output_edge,capture_edge,force_enable,force_value,input_time_ns,model_ready_ns,capture_time_ns,expected_raw,model_raw,sample_raw,expected_signed,sample_signed,expected_otr,sample_otr,timestamp,missing_hit");
    repeat (4) @(posedge adc_clk);
    @(negedge clk_sample);
    #1ps;
    drive_sample(0);
    capture_enable = 1'b1;
    rst = 1'b0;
    mode = 1;
    for (int unsigned index = 1; index < total; index++) begin
      @(negedge clk_sample);
      #1ps;
      drive_sample(index);
    end
    wait (captured == total);
    #3ps;
    assert (model_checked >= total && random_checked == random_count && max_random_streak == random_count &&
            ramp_checked == 4096 && zero_checked == 256 && false_high_checked > 0 && suppressed_checked > 0)
      else $fatal(1, "TEST_FAIL %s incomplete ADC comparison/OTR coverage",case_name);
    if (PROFILE == 0) begin
      assert ((&ramp_seen) && zero_sum == 0)
        else $fatal(1, "TEST_FAIL %s missing code or nonzero zero-input mean",case_name);
    end
    if (PROFILE >= 3) assert (missing_checked > 0) else $fatal(1,"TEST_FAIL missing-code injection untested");
    $fclose(trace_file);
    // Disable and re-enable without stalling or resampling the ADC itself.
    @(negedge clk_sample);
    #1ps;
    mode = 2;
    capture_enable = 1'b0;
    repeat (3) begin @(posedge clk_sample); #3ps; assert (!sample_valid) else $fatal(1,"TEST_FAIL capture disable"); end
    @(negedge clk_sample);
    #1ps;
    capture_enable = 1'b1;
    @(posedge clk_sample);
    #3ps;
    assert (sample_valid) else $fatal(1,"TEST_FAIL capture resume");
    @(negedge clk_sample);
    #1ps;
    rst = 1'b1;
    #2ps;
    assert (sample_valid) else $fatal(1,"TEST_FAIL capture reset was not synchronous");
    @(posedge clk_sample);
    #3ps;
    assert (!sample_valid && sample_raw == 12'd2047 && sample_signed == 13'sd0 &&
            !sample_otr && sample_timestamp == 64'd0) else $fatal(1,"TEST_FAIL capture reset values");
    repeat (3) @(posedge adc_clk);
    @(negedge clk_sample);
    #1ps;
    drive_sample(0);
    rst = 1'b0;
    for (int unsigned edge_index = 0; edge_index < 9; edge_index++) begin
      @(posedge clk_sample);
      #3ps;
      assert (sample_valid === (edge_index == 8)) else $fatal(1,"TEST_FAIL restart warmup edge=%0d",edge_index);
    end
    assert (sample_raw === expected[0][11:0] && sample_signed === adc_sample_t'($signed(expected[0][24:12])) &&
            sample_otr === expected[0][25] && sample_timestamp == 64'd0)
      else $fatal(1,"TEST_FAIL reset flush or timestamp epoch");
    $display("ADC_CASE_PASS case=%s compared=%0d random=%0d continuous=%0d model_latency=7 capture_extra=1 total_latency=8 ramp=4096 zero=256 forced_high=%0d forced_low=%0d missing=%0d seed=%0d",
       case_name,captured,random_checked,max_random_streak,false_high_checked,suppressed_checked,missing_checked,base_seed);
    mode = 0;
    done = 1'b1;
  end
endmodule : ad9226_scenario
`default_nettype wire
