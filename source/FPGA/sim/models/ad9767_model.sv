`default_nettype none
// Dual-port MODE=1, A channel only. Verification reset flushes both latches;
// it is NOT an AD9767 hardware reset pin. B channel is tied off externally.
module ad9767_model #(
  parameter realtime SETUP_NS = 2.0ns,
  parameter realtime HOLD_NS = 1.5ns
)(
  input wire logic rst, bus_enable,
  input wire logic aclk, wr1, bclk, wr2,
  input wire logic [13:0] da,
  output logic [13:0] input_code, dac_code,
  output logic input_valid, dac_valid,
  output integer unsigned accepted_edges
);
  timeunit 1ns; timeprecision 1ps;
  realtime last_data_change, last_accept;
  realtime minimum_setup, minimum_hold;
  integer unsigned setup_checks, hold_checks, phase_checks;
  bit seen_data, seen_accept, first_input, first_output;
  // Monitor bookkeeping only; all functional latch state is explicitly reset.
  initial begin
    last_data_change=0.0; last_accept=0.0;
    minimum_setup=1.0e9;minimum_hold=1.0e9;
    setup_checks=0;hold_checks=0;phase_checks=0;
    seen_data=0; seen_accept=0; first_input=1; first_output=1;
    assert(SETUP_NS >= 2.0ns && HOLD_NS >= 1.5ns)
      else $fatal(1,"TEST_FAIL AD9767 invalid timing configuration");
  end
  always @(da) begin
    if (!rst && seen_accept) begin
      hold_checks++;
      if($realtime-last_accept<minimum_hold)minimum_hold=$realtime-last_accept;
      assert ($realtime-last_accept >= HOLD_NS)
        else $fatal(1,"TEST_FAIL AD9767 hold time at %0t",$time);
    end
    last_data_change=$realtime;
    seen_data=1;
  end
  always @(bclk or wr2 or rst) begin
    #1ps;
    assert (bclk === 1'b0 && wr2 === 1'b0)
      else $fatal(1,"TEST_FAIL AD9767 B clocks must be known zero");
  end
  always @(aclk or wr1) begin
    #1ps;
    if (!rst && bus_enable) begin
      phase_checks++;
      assert(aclk === wr1 && !$isunknown({aclk,wr1}))
        else $fatal(1,"TEST_FAIL AD9767 ACLK WR1 phase mismatch");
    end
  end
  always @(posedge wr1) begin
    if (!rst && bus_enable) begin
      assert (seen_data && !$isunknown(da) && $realtime-last_data_change >= SETUP_NS)
        else $fatal(1,"TEST_FAIL AD9767 setup time or unknown data at %0t",$time);
      setup_checks++;
      if($realtime-last_data_change<minimum_setup)minimum_setup=$realtime-last_data_change;
      last_accept=$realtime; seen_accept=1;
    end
  end
  // Simultaneous WRT/CLK: DAC latch receives the PREVIOUS input latch.
  always @(posedge wr1 or posedge rst or negedge bus_enable) begin
    if (rst || !bus_enable) begin
      input_code <= 14'd8192; input_valid <= 1'b0; first_input=1;
    end else begin
      if (first_input) begin
        assert(da === 14'd8192) else $fatal(1,"TEST_FAIL AD9767 first input not midpoint");
        first_input=0;
      end
      input_code <= da; input_valid <= 1'b1;
    end
  end
  always @(posedge aclk or posedge rst or negedge bus_enable) begin
    if (rst || !bus_enable) begin
      dac_code <= 14'd8192; dac_valid <= 1'b0; accepted_edges <= 0;
      first_output=1; if(rst) seen_accept=0;
    end else begin
      dac_code <= input_code; dac_valid <= input_valid;
      accepted_edges <= accepted_edges+1;
      if (input_valid && first_output) begin
        assert(input_code === 14'd8192) else $fatal(1,"TEST_FAIL AD9767 first DAC not midpoint");
        first_output=0;
      end
    end
  end
endmodule
`default_nettype wire
