`default_nettype none
module safe_scenario #(
  parameter int unsigned START_RATE_HZ = 25_000_000
) (
  output logic done
);
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;
  logic [31:0] frequency_hz;
  wire clk;
  logic arst, clock_locked, module_enable, clock_restart;
  wire dac_data_oe, dac_clk_oe, adc_clk_oe, capture_enable;
  wire core_rst, enable_qualified;
  wire dac_aclk, dac_wr1, adc_clk;
  wire [13:0] dac_da;
  wire dac_code_t dac_data;
  wire safe_state_t state;
  int unsigned dac_rises, adc_rises, successful_starts;
  int unsigned checks, state_visits[0:9], transitions[0:9][0:9];
  int unsigned qualified_samples, release_samples, stop_age, start_age;
  int unsigned base_seed, effective_seed, rng_state, random_word;
  int unsigned clock_check_skip;
  int unsigned fault_visits[0:1][0:9], cancel_visits[1:5];
  int unsigned restart_visits[1:5], reenable_visits[6:9];
  int unsigned boundary_aborts, pulse_aborts, transition_bins;
  logic [31:0] random_signature;
  logic monitor_active;
  realtime last_rise_ns;

  ideal_clock clock_model (.frequency_hz(frequency_hz), .clk(clk));
  scope_core dut (
    .clk_sample(clk), .arst(arst), .clock_locked(clock_locked),
    .module_enable(module_enable), .clock_restart(clock_restart),
    .dac_data_oe(dac_data_oe), .dac_clk_oe(dac_clk_oe), .adc_clk_oe(adc_clk_oe),
    .capture_enable(capture_enable), .dac_data(dac_data), .state(state),
    .core_rst(core_rst), .enable_qualified(enable_qualified)
  );
  scope_pin_model pins (
    .clk(clk), .dac_data(dac_data), .dac_data_oe(dac_data_oe),
    .dac_clk_oe(dac_clk_oe), .adc_clk_oe(adc_clk_oe),
    .dac_da(dac_da), .dac_aclk(dac_aclk), .dac_wr1(dac_wr1), .adc_clk(adc_clk)
  );

  function automatic realtime period_ns();
    return 1000000000.0 / real'(frequency_hz);
  endfunction

  function automatic bit required_transition(input int unsigned from_state,
                                             input int unsigned to_state);
    return ((from_state == 0 || from_state == 2 || from_state == 4 || from_state == 5)
            && from_state == to_state)
        || (from_state < 5 && to_state == from_state + 32'd1)
        || (from_state >= 1 && from_state <= 5 && to_state == 6)
        || (from_state >= 6 && from_state <= 8 && to_state == from_state + 32'd1)
        || (from_state == 9 && to_state == 0);
  endfunction

  task automatic check_hiz();
    checks++;
    assert (dac_da === 14'bz && dac_aclk === 1'bz &&
            dac_wr1 === 1'bz && adc_clk === 1'bz && capture_enable === 1'b0)
      else $fatal(1, "TEST_FAIL %0d Hz pins not high-Z state=%0d time=%0t",
                  START_RATE_HZ, state, $time);
  endtask

  task automatic await_state(input safe_state_t target, input int unsigned limit);
    for (int unsigned cycle = 0; cycle < limit; cycle++) begin
      @(posedge clk);
      #5ps;
      if (state === target) return;
    end
    $fatal(1, "TEST_FAIL %0d Hz deadlock waiting for state %0d (actual %0d)",
           START_RATE_HZ, target, state);
  endtask

  task automatic idle();
    module_enable = 1'b0;
    clock_restart = 1'b0;
    await_state(SAFE_HIZ, 8);
    check_hiz();
    repeat (3) @(posedge clk);
    #5ps;
  endtask

  task automatic abort_at(input safe_state_t target);
    module_enable = 1'b1;
    await_state(target, 290);
    if (target == DAC_CLOCK_16_EDGES) repeat (6) @(posedge clk);
    if (target == ADC_STABILIZE_256_EDGES) repeat (31) @(posedge clk);
    if (target == RUN) repeat (3) @(posedge clk);
    #(period_ns() * 0.1);
    module_enable = 1'b0;
    #5ps;
    assert (!capture_enable) else $fatal(1, "TEST_FAIL capture not immediately stopped");
    idle();
    cancel_visits[int'(target)]++;
  endtask

  // Withdraw between the final pin rising edge and the control falling edge.
  // These cases exercise cancellation exactly where a counter could advance.
  task automatic abort_on_edge(input bit use_adc, input int unsigned edge_target);
    module_enable = 1'b1;
    await_state(use_adc ? ADC_CLOCK_ENABLE : DAC_CLOCK_16_EDGES, 290);
    for (int unsigned cycle = 0; cycle < 260; cycle++) begin
      @(posedge clk);
      #5ps;
      if ((use_adc ? adc_rises : dac_rises) == edge_target) begin
        assert (!capture_enable) else $fatal(1, "TEST_FAIL capture before boundary cancellation");
        module_enable = 1'b0;
        idle();
        boundary_aborts++;
        return;
      end
    end
    $fatal(1, "TEST_FAIL missed boundary ADC=%0d edge=%0d", use_adc, edge_target);
  endtask

  task automatic restart_at(input safe_state_t target);
    module_enable = 1'b1;
    await_state(target, 290);
    #(period_ns() * 0.1);
    clock_restart = 1'b1;
    #5ps;
    assert (!capture_enable) else $fatal(1, "TEST_FAIL capture not stopped by restart");
    await_state(SAFE_HIZ, 8);
    repeat (3) begin @(posedge clk); #5ps; check_hiz(); end
    clock_restart = 1'b0;
    await_state(RUN, 290);
    restart_visits[int'(target)]++;
    idle();
  endtask

  task automatic reenable_at(input safe_state_t target);
    module_enable = 1'b1;
    await_state(RUN, 290);
    module_enable = 1'b0;
    await_state(target, 8);
    module_enable = 1'b1;
    // Even an enable qualified during shutdown must finish the stop sequence.
    await_state(SAFE_HIZ, 8);
    check_hiz();
    await_state(RUN, 290);
    reenable_visits[int'(target)]++;
    idle();
  endtask

  // Pin events, not DUT counter values, define the golden cycle counts.
  always @(posedge dac_data_oe) begin
    dac_rises = 0;
    adc_rises = 0;
    #2ps;
    checks++;
    assert (dac_da === 14'd8192 && dac_aclk === 1'bz && adc_clk === 1'bz)
      else $fatal(1, "TEST_FAIL DAC middle code must precede clocks");
  end
  always @(posedge dac_aclk) begin
    if (dac_aclk === 1'b1) begin
      dac_rises++;
      #1ps;
      checks++;
      assert (dac_wr1 === 1'b1 && dac_da === 14'd8192)
        else $fatal(1, "TEST_FAIL DAC clocks/middle code mismatch");
    end
  end
  always @(posedge adc_clk) begin
    if (adc_clk === 1'b1) begin
      adc_rises++;
      checks++;
      assert (dac_rises >= 16 && dac_data_oe && dac_clk_oe)
        else $fatal(1, "TEST_FAIL ADC started before 16 DAC rising edges");
    end
  end
  always @(posedge capture_enable) begin
    checks++;
    assert (adc_rises == 256 && state === RUN && adc_clk_oe && dac_clk_oe)
      else $fatal(1, "TEST_FAIL capture started with ADC edges=%0d state=%0d", adc_rises, state);
    successful_starts++;
  end

  // Asynchronous emergency protection is checked without waiting for a clock.
  always @(posedge arst or negedge clock_locked) begin
    #5ps;
    if (monitor_active) begin
      check_hiz();
      assert (state === SAFE_HIZ) else $fatal(1, "TEST_FAIL emergency did not clear FSM");
    end
  end
  always @(dac_clk_oe or adc_clk_oe) begin
    if (monitor_active && !arst && clock_locked && !core_rst) begin
      checks++;
      assert (clk === 1'b0) else $fatal(1, "TEST_FAIL clock OE changed in high phase");
    end
  end

  // Independently check the two-sample enable qualifier using an integer run
  // length, including the asynchronous cancellation of short low pulses.
  always @(negedge clk or posedge core_rst or negedge module_enable) begin
    if (core_rst || !module_enable) qualified_samples = 0;
    else if (qualified_samples < 2) qualified_samples++;
    #2ps;
    if (monitor_active) begin
      checks++;
      assert (enable_qualified === (qualified_samples >= 2))
        else $fatal(1, "TEST_FAIL enable qualifier samples=%0d", qualified_samples);
    end
  end

  always @(negedge clk or posedge arst or negedge clock_locked) begin
    if (arst || !clock_locked) release_samples = 0;
    else if (release_samples < 2) release_samples++;
    #2ps;
    if (monitor_active) begin
      checks++;
      assert (core_rst === (release_samples < 2))
        else $fatal(1, "TEST_FAIL reset release did not require two local edges");
    end
  end

  // State/outputs scoreboard: quotas come from actual pin edges. It does not
  // read the DUT's binary counters or reconstruct their arithmetic.
  always @(negedge clk) begin : state_scoreboard
    safe_state_t old_state, expected_state;
    logic [3:0] expected_oe;
    logic reset_before;
    old_state = state;
    reset_before = core_rst;
    expected_state = old_state;
    expected_oe = {dac_data_oe, dac_clk_oe, adc_clk_oe, capture_enable};
    if (monitor_active) begin
      if (reset_before) begin
        expected_state = SAFE_HIZ;
        expected_oe = 4'b0000;
      end else if ((old_state >= DAC_MID_ENABLE && old_state <= RUN) &&
                   (!enable_qualified || clock_restart)) begin
        expected_state = STOP_CAPTURE;
        expected_oe[0] = 1'b0;
      end else begin
        case (old_state)
          SAFE_HIZ: begin
            expected_state = (enable_qualified && !clock_restart) ? DAC_MID_ENABLE : SAFE_HIZ;
            expected_oe = (expected_state == DAC_MID_ENABLE) ? 4'b1000 : 4'b0000;
          end
          DAC_MID_ENABLE: begin expected_state = DAC_CLOCK_16_EDGES; expected_oe = 4'b1100; end
          DAC_CLOCK_16_EDGES: begin
            assert (dac_rises <= 16) else $fatal(1, "TEST_FAIL DAC startup stuck");
            if (dac_rises == 16) begin expected_state = ADC_CLOCK_ENABLE; expected_oe = 4'b1110; end
          end
          ADC_CLOCK_ENABLE: expected_state = ADC_STABILIZE_256_EDGES;
          ADC_STABILIZE_256_EDGES: begin
            assert (adc_rises <= 256) else $fatal(1, "TEST_FAIL ADC stabilization stuck");
            if (adc_rises == 256) begin expected_state = RUN; expected_oe = 4'b1111; end
          end
          RUN: expected_oe = 4'b1111;
          STOP_CAPTURE: begin expected_state = STOP_ADC_CLOCK; expected_oe[1:0] = 2'b00; end
          STOP_ADC_CLOCK: begin expected_state = STOP_DAC_CLOCK; expected_oe[2:0] = 3'b000; end
          STOP_DAC_CLOCK: begin expected_state = RELEASE_OUTPUTS; expected_oe = 4'b0000; end
          RELEASE_OUTPUTS: begin expected_state = SAFE_HIZ; expected_oe = 4'b0000; end
          default: $fatal(1, "TEST_FAIL illegal/uninitialized state");
        endcase
      end
      #4ps;
      if (core_rst) begin expected_state = SAFE_HIZ; expected_oe = 4'b0000; end
      checks += 2;
      assert (state === expected_state)
        else $fatal(1, "TEST_FAIL %0d Hz state actual=%0d expected=%0d old=%0d DAC=%0d ADC=%0d",
                    START_RATE_HZ, state, expected_state, old_state, dac_rises, adc_rises);
      assert ({dac_data_oe, dac_clk_oe, adc_clk_oe, capture_enable} === expected_oe)
        else $fatal(1, "TEST_FAIL output-enable ordering at state %0d", state);
      assert (int'(state) < 10) else $fatal(1, "TEST_FAIL unknown state");
      state_visits[int'(state)]++;
      transitions[int'(old_state)][int'(state)]++;
      // A cancelled startup ends its liveness interval. Re-enabling during
      // shutdown must neither extend the stop deadline nor join two startups.
      if (state >= STOP_CAPTURE && state <= RELEASE_OUTPUTS) stop_age++; else stop_age = 0;
      assert (stop_age <= 5) else $fatal(1, "TEST_FAIL shutdown deadlock");
      if (state >= DAC_MID_ENABLE && state <= ADC_STABILIZE_256_EDGES) start_age++;
      else start_age = 0;
      assert (start_age <= 290)
        else $fatal(1, "TEST_FAIL startup deadlock state=%0d age=%0d", state, start_age);
      if (state == SAFE_HIZ || core_rst) check_hiz();
    end
  end

  always @(posedge clk) begin : clock_checker
    realtime difference;
    if (monitor_active && last_rise_ns > 0.0 && clock_check_skip == 0) begin
      difference = ($realtime - last_rise_ns) - period_ns();
      checks++;
      assert (difference <= 0.0011 && difference >= -0.0011)
        else $fatal(1, "TEST_FAIL ideal clock period error %0f ns", difference);
    end
    if (clock_check_skip > 0) clock_check_skip--;
    last_rise_ns = $realtime;
  end

  initial begin : scenario
    done = 1'b0;
    monitor_active = 1'b0;
    frequency_hz = START_RATE_HZ;
    arst = 1'b1;
    clock_locked = 1'b0;
    module_enable = 1'b1;
    clock_restart = 1'b0;
    checks = 0;
    dac_rises = 0;
    adc_rises = 0;
    successful_starts = 0;
    boundary_aborts = 0;
    pulse_aborts = 0;
    transition_bins = 0;
    random_signature = 32'h00000000;
    qualified_samples = 0;
    release_samples = 0;
    stop_age = 0;
    start_age = 0;
    clock_check_skip = 0;
    last_rise_ns = 0.0;
    base_seed = 32'd20261020;
    if ($value$plusargs("SEED=%d", base_seed)) begin end
    effective_seed = base_seed ^ START_RATE_HZ;
    rng_state = effective_seed;
    random_word = $urandom(rng_state);
    foreach (state_visits[index]) state_visits[index] = 0;
    foreach (transitions[row, column]) transitions[row][column] = 0;
    foreach (fault_visits[kind, index]) fault_visits[kind][index] = 0;
    foreach (cancel_visits[index]) cancel_visits[index] = 0;
    foreach (restart_visits[index]) restart_visits[index] = 0;
    foreach (reenable_visits[index]) reenable_visits[index] = 0;
    #10ps;
    monitor_active = 1'b1;
    repeat (5) begin @(posedge clk); #5ps; check_hiz(); end
    arst = 1'b0;
    repeat (5) begin @(posedge clk); #5ps; check_hiz(); end
    module_enable = 1'b0;
    clock_locked = 1'b1;
    idle();

    // A short enable crossing one falling edge must not start anything.
    @(posedge clk);
    #(period_ns() * 0.4);
    module_enable = 1'b1;
    #(period_ns() * 0.2);
    module_enable = 1'b0;
    repeat (5) begin @(posedge clk); #5ps; check_hiz(); end

    for (int unsigned target = 1; target <= 5; target++) abort_at(safe_state_t'(target));
    abort_on_edge(1'b0, 15);
    abort_on_edge(1'b0, 16);
    abort_on_edge(1'b1, 255);
    abort_on_edge(1'b1, 256);

    // Interrupt every startup AND shutdown state with both reset and lock loss.
    for (int unsigned fault_kind = 0; fault_kind < 2; fault_kind++) begin
      for (int unsigned target = 0; target < 10; target++) begin
        if (target != 0) begin
          module_enable = 1'b1;
          if (target >= 6) begin
            await_state(RUN, 290);
            module_enable = 1'b0;
          end
          await_state(safe_state_t'(target), 290);
        end
        #(period_ns() * 0.1);
        if (fault_kind == 0) arst = 1'b1; else clock_locked = 1'b0;
        #5ps;
        check_hiz();
        assert (state === SAFE_HIZ) else $fatal(1, "TEST_FAIL fault recovery state");
        fault_visits[fault_kind][target]++;
        module_enable = 1'b0;
        repeat (3) @(posedge clk);
        if (fault_kind == 0) arst = 1'b0; else clock_locked = 1'b1;
        idle();
      end
    end

    // Low pulses entirely between falling edges must cancel EVERY active phase.
    for (int unsigned target = 1; target <= 5; target++) begin
      module_enable = 1'b1;
      await_state(safe_state_t'(target), 290);
      #(period_ns() * 0.1);
      module_enable = 1'b0;
      #5ps;
      assert (!capture_enable) else $fatal(1, "TEST_FAIL short disable did not stop capture");
      #(period_ns() * 0.05);
      module_enable = 1'b1;
      await_state(SAFE_HIZ, 8);
      check_hiz();
      await_state(RUN, 290);
      pulse_aborts++;
      idle();
    end

    for (int unsigned target = 1; target <= 5; target++) restart_at(safe_state_t'(target));
    for (int unsigned target = 6; target <= 9; target++) reenable_at(safe_state_t'(target));

    // Explicitly dwell in RUN; complete startup alone does not cover RUN->RUN.
    module_enable = 1'b1;
    await_state(RUN, 290);
    repeat (4) begin
      @(posedge clk);
      #5ps;
      assert (state === RUN && capture_enable && adc_clk_oe && dac_clk_oe && dac_data_oe)
        else $fatal(1, "TEST_FAIL steady RUN outputs changed");
    end
    assert (transitions[5][5] >= 3) else $fatal(1, "TEST_FAIL steady RUN transition accounting");
    $display("TEST_CASE_PASS steady_RUN rate=%0d", START_RATE_HZ);
    idle();

    // Restart handshake: stop first, change the ideal input clock only while
    // high-Z, hold restart during the change, then re-run all 16/256 edges.
    module_enable = 1'b1;
    await_state(RUN, 290);
    clock_restart = 1'b1;
    await_state(SAFE_HIZ, 8);
    clock_check_skip = 3;
    frequency_hz = (START_RATE_HZ == ADC_RATE_50M_HZ) ? ADC_RATE_10M_HZ : ADC_RATE_50M_HZ;
    repeat (5) begin @(posedge clk); #5ps; check_hiz(); end
    clock_restart = 1'b0;
    await_state(RUN, 290);
    idle();

    for (int unsigned trial = 0; trial < 16; trial++) begin
      random_word = $urandom();
      // Explicit 32-bit rotate/XOR fingerprint of the actual random choices.
      random_signature = {random_signature[26:0], random_signature[31:27]} ^ random_word;
      abort_at(safe_state_t'(32'd1 + (random_word % 32'd5)));
    end
    for (int unsigned index = 0; index < 10; index++) begin
      assert (state_visits[index] > 0)
        else $fatal(1, "TEST_FAIL unreachable/unvisited state %0d", index);
    end
    assert (successful_starts >= 10) else $fatal(1, "TEST_FAIL insufficient complete startups");
    foreach (transitions[row, column]) begin
      if (required_transition(row, column)) begin
        assert (transitions[row][column] > 0)
          else $fatal(1, "TEST_FAIL uncovered transition %0d -> %0d", row, column);
        transition_bins++;
        $display("TRANSITION_COVERAGE rate=%0d from=%0d to=%0d hits=%0d",
                 START_RATE_HZ, row, column, transitions[row][column]);
      end
    end
    foreach (fault_visits[kind, index]) begin
      assert (fault_visits[kind][index] > 0)
        else $fatal(1, "TEST_FAIL missing fault kind=%0d state=%0d", kind, index);
    end
    foreach (cancel_visits[index]) begin
      assert (cancel_visits[index] > 0 && restart_visits[index] > 0)
        else $fatal(1, "TEST_FAIL missing cancellation/restart state=%0d", index);
    end
    foreach (reenable_visits[index]) begin
      assert (reenable_visits[index] > 0)
        else $fatal(1, "TEST_FAIL missing shutdown re-enable state=%0d", index);
    end
    assert (transition_bins == 18 && boundary_aborts == 4 && pulse_aborts == 5)
      else $fatal(1, "TEST_FAIL incomplete directed coverage");
    $display("SCENARIO_COVERAGE rate=%0d transitions=18/18 faults=20/20 cancels=5/5 restarts=5/5 reenable=4/4 boundaries=4/4 pulses=5/5 signature=%08h",
             START_RATE_HZ, random_signature);
    $display("AGENT_PASS rate=%0d states=10/10 startups=%0d checks=%0d seed=%0d",
             START_RATE_HZ, successful_starts, checks, effective_seed);
    for (int unsigned row = 0; row < 10; row++) begin
      $display("STATE_COVERAGE rate=%0d state=%0d visits=%0d", START_RATE_HZ, row, state_visits[row]);
    end
    done = 1'b1;
  end
endmodule : safe_scenario
`default_nettype wire
