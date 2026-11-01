`default_nettype none
// Byte-level PC commands drive the real protocol RTL and the verification-only
// DAC -> channel -> ADC -> capture backend. The PC oracle audits the output.
module tb_system_case #(parameter int CASE_ID=0);
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import protocol_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,in_valid=0,out_ready=1,emergency_enable=1;
  logic [7:0] in_data=0;
  wire logic in_ready,out_valid;wire logic [7:0]out_data;
  wire logic capture_busy,capture_ready,frame_available,backend_error,measurement_error;
  wire logic [63:0]backend_timestamp;wire logic [31:0]backend_rate,backend_trigger_index,backend_length;
  wire measurement_result_t measurements;
  wire logic single_pulse,stop_pulse,release_pulse,acquire_enable;
  wire logic [17:0]record_length,pre_samples,sample_index;
  wire trigger_config_t trigger_config;wire dds_wave_t dds_wave;
  wire logic dds_enable;wire logic [31:0]dds_phase_inc,dds_phase_offset;
  wire logic [15:0]dds_amplitude;wire logic signed [17:0]dds_dc_offset;
  wire parser_errors_t parser_errors;wire frame_header_t last_request_header;
  wire logic [31:0]good_frames,unknown_commands,command_errors;
  wire logic sample_request,sample_ready,sample_valid;wire logic [15:0]sample_word;
  wire safe_state_t safe_state;wire logic safe_capture,safe_dac_data_oe,safe_dac_clk_oe,safe_adc_clk_oe;
  wire [13:0]pin_dac;wire pin_aclk,pin_wr1,pin_adc_clk;
  wire logic live_valid,live_otr,measurement_done,measurement_valid;
  wire logic [11:0]live_raw;wire logic [63:0]live_timestamp;
  wire logic [31:0]effective_phase_inc;
  // Legacy connected cases exercise standard DDS. AWG is disabled for this
  // adapter; its port must still be explicitly connected after the interface
  // extension. The dedicated tb_awg verifies table playback and commands.
  scope_protocol_core #(.RX_TIMEOUT_CYCLES(2000)) dut(.*,
    .awg_play_index(10'd0),.awg_play_value(),.awg_selected(),
    .capture_mode(),.auto_timeout(),.spectrum_bytes(768'd0),.saturation_bytes(128'd0),.diagnostic_mode(),.uart_framing_errors(32'd0),.rx_overruns(32'd0));
  system_capture_backend #(.CASE_ID(CASE_ID)) backend(.*,.clk_sys(clk));
  byte unsigned command_bytes[0:63];int unsigned command_lengths[0:8];
  int unsigned command_count=0,response_count=0,output_count=0,live_count=0;
  int unsigned response_size=0,response_position=0;
  logic [7:0] length_lo;
  string vector_dir=".",trace_dir=".";
  int unsigned seed=20261020;integer fd,trace,live_trace,measure_trace,rc;
  integer injected_fault=0;
  bit saw_run=0,saw_mid=0,saw_hiz=0,saw_otr=0;
  always @(posedge clk)if(!rst)begin
    if(out_valid&&out_ready)begin
      $fwrite(trace,"%02x\n",out_data);
      if(response_position==0)assert(out_data==8'h55)else $fatal(1,"SYSTEM_FRAME_MAGIC0 byte=%0d",output_count);
      if(response_position==1)assert(out_data==8'haa)else $fatal(1,"SYSTEM_FRAME_MAGIC1 byte=%0d",output_count);
      if(response_position==6)length_lo=out_data;
      if(response_position==7)response_size=28+int'(length_lo)+256*int'(out_data);
      response_position++;
      output_count++;
      if(response_size!=0&&response_position==response_size)begin
        response_count++;response_position=0;response_size=0;
      end
    end
  end
  // Log exactly the samples accepted by the measurement RTL, before NBA.
  always @(posedge backend.clk_adc)if(!rst&&live_valid&&backend.measure_ready)
    $fwrite(measure_trace,"%0d,%03x,%0d\n",live_timestamp,live_raw,live_otr);
  always @(negedge backend.clk_adc)if(!rst)begin
    if(live_valid)begin
      $fwrite(live_trace,"%0d,%03x,%0d\n",live_timestamp,live_raw,live_otr);
      live_count++;
      if(live_otr)saw_otr=1;
    end
    if(safe_state==RUN)saw_run=1;
    if(safe_state==SAFE_HIZ)begin
      saw_hiz=1;
      assert(pin_dac===14'hzzzz&&pin_aclk===1'bz&&pin_wr1===1'bz&&pin_adc_clk===1'bz)
        else $fatal(1,"SYSTEM_HIZ_ASSERT case=%0d",CASE_ID);
    end
    if(safe_dac_data_oe&&!saw_mid)begin
      assert(pin_dac==14'd8192)else $fatal(1,"SYSTEM_FIRST_MID_ASSERT case=%0d code=%0d",CASE_ID,pin_dac);
      saw_mid=1;
    end
    assert(!backend_error)else $fatal(1,"SYSTEM_BACKEND_ERROR case=%0d",CASE_ID);
  end
  task automatic send_command(input int unsigned index);
    string path;int response_before;
    path=$sformatf("%s/cmd_%0d.hex",vector_dir,index);
    $readmemh(path,command_bytes,0,command_lengths[index]-1);
    response_before=response_count;
    for(int unsigned j=0;j<command_lengths[index];j++)begin
      @(negedge clk);in_data=command_bytes[j];in_valid=1;
      do @(posedge clk);while(!in_ready);
      @(negedge clk);in_valid=0;
    end
    wait(response_count==response_before+1);
    command_count++;
    @(negedge clk);
  endtask
  initial begin
    if($value$plusargs("VECTOR_DIR=%s",vector_dir))begin end
    if($value$plusargs("TRACE_DIR=%s",trace_dir))begin end
    if($value$plusargs("SEED=%d",seed))begin end
    if($value$plusargs("FAULT=%d",injected_fault))begin end
    fd=$fopen({vector_dir,"/lengths.txt"},"r");assert(fd!=0)else $fatal(1,"SYSTEM_LENGTH_OPEN");
    for(int i=0;i<9;i++)begin rc=$fscanf(fd,"%d",command_lengths[i]);assert(rc==1)else $fatal(1,"SYSTEM_LENGTH_READ %0d",i);end
    $fclose(fd);
    trace=$fopen({trace_dir,"/system_uart.hex"},"w");
    live_trace=$fopen({trace_dir,"/system_live.csv"},"w");
    measure_trace=$fopen({trace_dir,"/system_measure.csv"},"w");
    assert(trace!=0&&live_trace!=0&&measure_trace!=0)else $fatal(1,"SYSTEM_TRACE_OPEN");
    repeat(12)@(negedge clk);rst=0;
    for(int i=0;i<5;i++)begin
      send_command(i);
      if(injected_fault!=0 && i==0)$fatal(1,"SYSTEM_INJECTED_FAILURE case=%0d",CASE_ID);
    end
    wait(frame_available);
    wait(measurement_done||measurements.stats_valid);
    repeat(8)@(negedge clk);
    assert(backend_length==32'd16384)
      else $fatal(1,"SYSTEM_FRAME_LENGTH case=%0d actual=%0d",CASE_ID,backend_length);
    assert(backend_trigger_index==32'(pre_samples))
      else $fatal(1,"SYSTEM_TRIGGER_INDEX case=%0d actual=%0d expected=%0d",CASE_ID,backend_trigger_index,pre_samples);
    for(int i=5;i<8;i++)send_command(i);
    if(CASE_ID==7)begin
      emergency_enable=0;
      wait(safe_state==SAFE_HIZ);repeat(4)@(negedge clk);
      assert(pin_dac===14'hzzzz&&!safe_capture)else $fatal(1,"SYSTEM_EMERGENCY_HIZ");
      emergency_enable=1;
      wait(safe_state==RUN);
    end
    send_command(8);
    wait(safe_state==SAFE_HIZ);repeat(4)@(negedge clk);
    assert(saw_hiz&&saw_mid&&saw_run&&command_count==9&&response_count==9&&good_frames==9)
      else $fatal(1,"SYSTEM_COMPLETION_ASSERT case=%0d commands=%0d responses=%0d good=%0d",CASE_ID,command_count,response_count,good_frames);
    if(CASE_ID==6)assert(saw_otr)else $fatal(1,"SYSTEM_OTR_MISSING");
    if(CASE_ID!=6)assert(!saw_otr)else $fatal(1,"SYSTEM_UNEXPECTED_OTR case=%0d",CASE_ID);
    $fclose(trace);$fclose(live_trace);$fclose(measure_trace);
    $display("TEST_PASS tb_system_case case=%0d seed=%0d commands=%0d responses=%0d live=%0d frame=%0d trigger=%0d otr=%0d errors=0",
      CASE_ID,seed,command_count,response_count,live_count,backend_length,backend_trigger_index,saw_otr);
    $finish;
  end
  initial begin #50000000ns;$fatal(1,"SYSTEM_WATCHDOG case=%0d responses=%0d frame=%0d live=%0d state=%0d",CASE_ID,response_count,frame_available,live_count,safe_state);end
endmodule
`default_nettype wire
