`default_nettype none
module dds_safe_scenario(output logic done);
  timeunit 1ns; timeprecision 1ps;
  logic clk,arst,locked,module_enable;
  wire data_oe,dac_oe,adc_oe,capture,rst,qualified;
  wire [13:0] unused_mid,data,input_code,converted;
  wire [31:0] phase_value;
  wire sample_valid,iv,ov;
  wire [13:0] da;
  wire aclk,wr1,adcclk;
  scope_pkg::safe_state_t state;
  integer unsigned edges;
  integer starts,aborts,resets,lock_faults,observed;
  ideal_clock clock_source(.frequency_hz(32'd25000000),.clk(clk));
  scope_core safety(.clk_sample(clk),.arst(arst),.clock_locked(locked),
    .module_enable(module_enable),.clock_restart(1'b0),.dac_data_oe(data_oe),
    .dac_clk_oe(dac_oe),.adc_clk_oe(adc_oe),.capture_enable(capture),
    .dac_data(unused_mid),.state(state),.core_rst(rst),.enable_qualified(qualified));
  dds_core dut(.clk_dac(clk),.rst(rst),.enable(capture),.waveform(scope_pkg::DDS_SINE),
    .phase_inc(32'h10000000),.phase_offset(32'h40000000),.amplitude(16'd8191),
    .dc_offset(18'sd0),.dac_code(data),.sample_phase(phase_value),.sample_valid(sample_valid));
  scope_pin_model pins(.clk(clk),.dac_data(data),.dac_data_oe(data_oe),
    .dac_clk_oe(dac_oe),.adc_clk_oe(adc_oe),.dac_da(da),.dac_aclk(aclk),.dac_wr1(wr1),.adc_clk(adcclk));
  ad9767_model converter(.rst(arst||!locked),.bus_enable(dac_oe),.aclk(aclk),.wr1(wr1),
    .bclk(1'b0),.wr2(1'b0),.da(da),.input_code(input_code),.dac_code(converted),
    .input_valid(iv),.dac_valid(ov),.accepted_edges(edges));
  always @(posedge aclk)begin
    if(dac_oe&&!arst&&locked)begin
      observed++;
      if(!capture)assert(da===14'd8192)else $fatal(1,"TEST_FAIL DDS startup/stop midpoint");
    end
  end
  task automatic high_z;
    assert(da===14'bz && aclk===1'bz && wr1===1'bz && adcclk===1'bz)
      else $fatal(1,"TEST_FAIL DDS safety high Z");
  endtask
  task automatic await_run;
    for(integer wait_cycles=0;wait_cycles<400 && capture!==1'b1;wait_cycles++)@(posedge clk);
    assert(capture===1'b1)else $fatal(1,"TEST_FAIL DDS await RUN state=%0d arst=%b lock=%b reset=%b qualified=%b enable=%b starts=%0d",state,arst,locked,rst,qualified,module_enable,starts);
    starts++;
    repeat(4)@(posedge clk);
    #2ns;assert(sample_valid && data!=14'd8192)else $fatal(1,"TEST_FAIL DDS RUN activity");
  endtask
  initial begin
    done=0;arst=1;locked=0;module_enable=0;
    starts=0;aborts=0;resets=0;lock_faults=0;observed=0;
    repeat(4)@(negedge clk);#2ps;high_z();
    locked=1;arst=0;
    for(integer i=0;i<12;i++)begin
      module_enable=1;await_run();
      // Different offsets within a cycle, away from the previous hold aperture.
      #(3.0ns+realtime'(i)*0.71ns);
      if(i%2==0)begin arst=1;resets++;end
      else begin locked=0;lock_faults++;end
      #2ps;high_z();
      repeat(3)@(negedge clk);
      #2ns;arst=0;locked=1;
      await_run();
      @(posedge clk);#3ns;module_enable=0;aborts++;
      repeat(6)@(negedge clk);#2ps;high_z();
      assert(state==scope_pkg::SAFE_HIZ)else $fatal(1,"TEST_FAIL DDS shutdown deadline");
    end
    // Abort the two DAC startup phases, the ADC wait, and RUN with DDS present.
    for(integer target=1;target<=5;target++)begin
      module_enable=1;
      for(integer c=0;c<400 && state!=scope_pkg::safe_state_t'(4'(target));c++)@(posedge clk);
      assert(state==scope_pkg::safe_state_t'(4'(target)))else $fatal(1,"TEST_FAIL DDS target state %0d got %0d",target,state);
      #3ns;module_enable=0;aborts++;
      repeat(6)@(negedge clk);#2ps;high_z();
    end
    assert(starts==24 && aborts==17 && resets==6 && lock_faults==6 && observed>6000)
      else $fatal(1,"TEST_FAIL DDS safety coverage starts=%0d aborts=%0d observed=%0d",starts,aborts,observed);
    $display("DDS_SAFETY_PASS startups=%0d aborts=%0d reset_faults=%0d lock_faults=%0d accepted_edges=%0d errors=0",starts,aborts,resets,lock_faults,observed);
    done=1;
  end
endmodule
`default_nettype wire
