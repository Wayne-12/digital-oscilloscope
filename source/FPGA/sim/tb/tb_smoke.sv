`default_nettype none
module tb_smoke;
  timeunit 1ns;
  timeprecision 1ps;
  import scope_pkg::*;

  localparam int unsigned COUNTER_WIDTH = 8;
  localparam time CLOCK_PERIOD = 10ns;
  localparam time HALF_PERIOD = 5ns;
  logic clk;
  logic rst;
  wire logic [COUNTER_WIDTH-1:0] count;
  int unsigned expected_count;
  int unsigned checked_edges;
  int unsigned reset_edges;
  int unsigned wraps;
  int unsigned seed;
  int unsigned rng_state;
  int unsigned random_cycles;
  logic [31:0] random_word;
  logic [31:0] random_signature;
  time last_posedge;
  logic [COUNTER_WIDTH-1:0] held_count;

  smoke_counter #(.COUNTER_WIDTH(COUNTER_WIDTH)) dut (
    .clk(clk), .rst(rst), .count(count)
  );

  initial begin : clock_generator
    clk = 1'b0;
    forever #(HALF_PERIOD) clk = ~clk;
  end

  // Independent integer scoreboard; sample DUT after the NBA update.
  always @(posedge clk) begin : scoreboard
    if (checked_edges != 32'd0) begin
      assert (($time - last_posedge) == CLOCK_PERIOD)
        else $fatal(1, "TEST_FAIL clock period actual=%0t expected=%0t",
                    $time - last_posedge, CLOCK_PERIOD);
    end
    last_posedge = $time;
    assert (!$isunknown(rst)) else $fatal(1, "TEST_FAIL reset is unknown");
    if (rst) begin
      expected_count = 32'd0;
      reset_edges = reset_edges + 32'd1;
    end else begin
      if (expected_count == 32'd255) wraps = wraps + 32'd1;
      expected_count = (expected_count + 32'd1) % 32'd256;
    end
    #1ps;
    assert (!$isunknown(count))
      else $fatal(1, "TEST_FAIL count contains X/Z at %0t", $time);
    assert (count === COUNTER_WIDTH'(expected_count))
      else $fatal(1, "TEST_FAIL scoreboard actual=%0d expected=%0d rst=%b time=%0t",
                  count, expected_count, rst, $time);
    checked_edges = checked_edges + 32'd1;
  end

  initial begin : stimulus
    rst = 1'b1;
    expected_count = 32'd0;
    checked_edges = 32'd0;
    reset_edges = 32'd0;
    wraps = 32'd0;
    last_posedge = 0ns;
    seed = 32'd20261020;
    random_cycles = 32'd128;
    random_signature = 32'd0;
    if ($value$plusargs("SEED=%d", seed)) begin end
    if ($value$plusargs("RANDOM_CYCLES=%d", random_cycles)) begin end
    assert (random_cycles <= 32'd4096)
      else $fatal(1, "TEST_FAIL RANDOM_CYCLES must be <= 4096");
    assert (SYS_CLK_HZ == 32'd100000000)
      else $fatal(1, "TEST_FAIL smoke clock must be 100 MHz");
    rng_state = seed;
    random_word = $urandom(rng_state);
    $display("TEST_BEGIN tb_smoke seed=%0d random_cycles=%0d", seed, random_cycles);

    repeat (3) @(negedge clk);
    assert (count === 8'd0) else $fatal(1, "TEST_FAIL startup reset");
    rst = 1'b0;
    $display("TEST_CASE_PASS startup_synchronous_reset");

    repeat (300) @(negedge clk);
    assert (wraps >= 32'd1) else $fatal(1, "TEST_FAIL wrap was not exercised");
    $display("TEST_CASE_PASS increment_and_wrap");

    // Reset asserted between edges must have no asynchronous effect.
    held_count = count;
    #1ns;
    rst = 1'b1;
    #1ns;
    assert (count === held_count)
      else $fatal(1, "TEST_FAIL reset behaved asynchronously");
    @(posedge clk);
    #2ps;
    assert (count === 8'd0) else $fatal(1, "TEST_FAIL reset at rising edge");
    @(negedge clk);
    rst = 1'b0;
    repeat (16) @(negedge clk);

    // A pulse entirely between rising edges must not reset the counter.
    held_count = count;
    #1ns;
    rst = 1'b1;
    #1ns;
    assert (count === held_count)
      else $fatal(1, "TEST_FAIL inter-edge reset pulse changed state");
    rst = 1'b0;
    $display("TEST_CASE_PASS synchronous_reset_edges_and_short_pulse");

    for (int unsigned index = 32'd0; index < random_cycles; index++) begin
      @(negedge clk);
      random_word = $urandom();
      random_signature = {random_signature[30:0], random_signature[31]} ^ random_word;
      rst = (random_word[2:0] == 3'b000);
    end
    @(negedge clk);
    rst = 1'b0;
    @(posedge clk);
    #2ps;
    assert (checked_edges >= (32'd321 + random_cycles))
      else $fatal(1, "TEST_FAIL scoreboard did not complete");
    assert (reset_edges >= 32'd4 && wraps >= 32'd1)
      else $fatal(1, "TEST_FAIL directed reset/wrap coverage incomplete");
    $display("TEST_CASE_PASS seeded_reset_regression");
    $display("TEST_PASS tb_smoke seed=%0d checked_edges=%0d reset_edges=%0d wraps=%0d random_signature=%08h",
             seed, checked_edges, reset_edges, wraps, random_signature);
    $finish;
  end

  initial begin : watchdog
    #50us;
    $fatal(1, "TEST_FAIL tb_smoke watchdog timeout");
  end
endmodule : tb_smoke
`default_nettype wire
