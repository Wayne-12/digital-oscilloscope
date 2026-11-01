`default_nettype none
module tb_scope_board #(parameter integer TEST_BAUD=1152000,
  parameter logic [31:0] TEST_BUILD=32'hA3261027);
  timeunit 1ns;timeprecision 1ps;
  localparam realtime BIT_NS=1.0e9/TEST_BAUD;
  logic clk=0,reset_n=0,module_switch=1,rx=1;
  always #5ns clk=~clk;
  wire tx,aclk,wr1,adc_clk;wire [13:0]da;wire[3:0]led;
  wire[11:0]adc_raw;wire adc_otr,adc_valid;
  scope_board_top #(.ENABLE_DEBOUNCE_CYCLES(16),.UART_BAUD(TEST_BAUD),.FIRMWARE_BUILD(TEST_BUILD)) dut(
    .sys_clk_100(clk),.reset_n(reset_n),.module_switch(module_switch),
    .fpga_uart_rx_n5(rx),.fpga_uart_tx_t4(tx),.adc_data(adc_raw),.adc_otr(adc_otr),
    .dac_da(da),.dac_aclk(aclk),.dac_wr1(wr1),.adc_clk(adc_clk),.status_led(led));
  wire[13:0]dac_input,dac_output;wire di_valid,do_valid;wire[31:0]dac_edges;
  ad9767_model dac(.rst(!reset_n),.bus_enable(dut.dac_data_oe&&dut.dac_clk_oe),
    .aclk(aclk),.wr1(wr1),.bclk(1'b0),.wr2(1'b0),.da(da),
    .input_code(dac_input),.dac_code(dac_output),.input_valid(di_valid),.dac_valid(do_valid),.accepted_edges(dac_edges));
  wire signed[31:0]ideal;wire ch_valid,ch_clip,force_en,force_val;
  loopback_channel_model channel(.clk_sample(dut.clk_sample),.rst(!reset_n),
    .dac_code(dac_output),.dac_valid(do_valid),.noise_seed(32'd42),.force_otr_enable(1'b0),.force_otr_value(1'b0),
    .ideal_sample(ideal),.sample_valid(ch_valid),.channel_clipped(ch_clip),
    .adc_force_otr_enable(force_en),.adc_force_otr_value(force_val));
  // The model's reset is a verification flush, sampled on its clock. Keep it
  // asserted through the first physical ADC edge because the DUT correctly
  // presents no ADC clock during board reset. The 256-edge DUT warm-up then
  // discards all model pipeline initialization, as it does on real hardware.
  logic adc_model_started=0;
  always @(posedge adc_clk or negedge reset_n)
    if(!reset_n)adc_model_started<=0;else adc_model_started<=1;
  ad9226_model adc(.adc_clk(adc_clk),.rst(!reset_n||!adc_model_started),.ideal_sample(ideal),.noise_seed(32'd42),
    .force_otr_enable(force_en),.force_otr_value(force_val),.raw_code(adc_raw),.otr(adc_otr),.output_valid(adc_valid));
  string folder=".";bit boot_only,multires_test,analysis_test,modes_test,saturation_test;int trace,live,frozen,commands,rc,fd,fft_trace,lengths[0:63];
  always @(posedge dut.clk_sample) if(fft_trace && dut.analysis.bin_valid)
    $fwrite(fft_trace,"%0d,%0d,%0d,%0d\n",dut.metadata.first_timestamp,
      dut.analysis.bin_data.index,dut.analysis.bin_data.real_part,dut.analysis.bin_data.imag_part);
  byte command_bytes[0:127];int received=0,packet_pos=0,payload_size=0;
  logic [7:0] packet[0:1051];logic[7:0]byte_rx;logic[11:0]previous_raw;logic previous_otr;
  always @(posedge dut.clk_sample)begin previous_raw=adc_raw;previous_otr=adc_otr;end
  always @(negedge dut.clk_sample)if(reset_n&&dut.live_valid&&dut.cap_busy)begin
    assert(!$isunknown({dut.live_raw,dut.live_otr,dut.live_timestamp}))
      else $fatal(1,"BOARD_ADC_UNKNOWN_AFTER_WARMUP");
    assert(dut.live_raw===previous_raw && dut.live_otr===previous_otr)
      else $fatal(1,"BOARD_ADC_CAPTURE_MISMATCH");
    $fwrite(live,"%0d,%0h,%0d\n",dut.live_timestamp,dut.live_raw,dut.live_otr);
  end
  initial forever begin
    @(negedge tx);#(BIT_NS*1.5);
    for(int b=0;b<8;b++)begin byte_rx[b]=tx;#(BIT_NS);end
    assert(tx===1'b1)else $fatal(1,"BOARD_UART_STOP_BIT");
    $fwrite(trace,"%02x\n",byte_rx);
    packet[packet_pos]=byte_rx;packet_pos++;
    if(packet_pos==8)begin
      payload_size=int'({packet[7],packet[6]});
      assert(payload_size<=1024)else $fatal(1,"BOARD_UART_PAYLOAD_LENGTH %0d",payload_size);
    end
    if(packet_pos>=28 && packet_pos==28+payload_size)begin
      assert(packet[0]==8'h55&&packet[1]==8'haa&&payload_size<=1024)else $fatal(1,"BOARD_UART_HEADER");
      received++;packet_pos=0;
    end
  end
  task automatic send(input int index,input int replies);
    string path;int before_count;
    path=$sformatf("%s/cmd_%0d.hex",folder,index);$readmemh(path,command_bytes,0,lengths[index]-1);
    before_count=received;
    for(int j=0;j<lengths[index];j++)begin
      rx=0;#(BIT_NS);
      for(int b=0;b<8;b++)begin rx=command_bytes[j][b];#(BIT_NS);end
      rx=1;#(BIT_NS);
    end
    wait(received==before_count+replies);#(BIT_NS*2);commands++;
    $display("BOARD_COMMAND_DONE index=%0d packets=%0d",index,received);
  endtask
  task automatic send_only(input int index);
    string path;
    path=$sformatf("%s/cmd_%0d.hex",folder,index);$readmemh(path,command_bytes,0,lengths[index]-1);
    for(int j=0;j<lengths[index];j++)begin
      rx=0;#(BIT_NS);
      for(int b=0;b<8;b++)begin rx=command_bytes[j][b];#(BIT_NS);end
      rx=1;#(BIT_NS);
    end
  endtask
  initial begin
    boot_only=$test$plusargs("BOOT_PRESET_ONLY");
    multires_test=$test$plusargs("MULTIRES_TEST");
    analysis_test=$test$plusargs("ANALYSIS_TEST");
    modes_test=$test$plusargs("CAPTURE_MODES_TEST");
    saturation_test=$test$plusargs("SATURATION_TEST");
    if($value$plusargs("VECTOR_DIR=%s",folder))begin end
    fd=$fopen({folder,"/lengths.txt"},"r");assert(fd!=0)else $fatal(1,"BOARD_VECTOR_OPEN");
    for(int i=0;i<(saturation_test?47:(modes_test?27:(multires_test?30:(analysis_test?21:12))));i++)begin rc=$fscanf(fd,"%d",lengths[i]);assert(rc==1)else $fatal(1,"BOARD_VECTOR_LENGTH");end
    $fclose(fd);trace=$fopen({folder,"/uart.hex"},"w");live=$fopen({folder,"/live.csv"},"w");commands=0;
    fft_trace=$fopen({folder,"/fft_bins.csv"},"w");
    #200ns;reset_n=1;wait(dut.clock_locked);#3000ns;
    assert(da===14'hzzzz&&aclk===1'bz&&wr1===1'bz&&adc_clk===1'bz)else $fatal(1,"BOARD_HIGH_SWITCH_BOOT_ENABLED");
    assert(dut.dds_enable && dut.dds_phase_inc==32'd17179869 && dut.dds_amplitude==16'd819 &&
      dut.dds_phase_offset==0 && dut.dds_dc_offset==0 && dut.dds_wave==scope_pkg::DDS_SINE &&
      dut.trigger_config.kind==scope_pkg::TRIG_RISE && dut.trigger_config.threshold==13'sd4 &&
      dut.trigger_config.hysteresis==13'd2)
      else $fatal(1,"BOARD_BOOT_PRESET_MISMATCH");
    $display("BOARD_BOOT_PRESET_PASS dds=100kHz_10percent trigger_codes=4 hysteresis_codes=2 outputs=HIZ");
    send(0,1);send(1,1);send(2,1);
    module_switch=0;#3000ns;module_switch=1;wait(dut.safe_capture);#1000ns;
    if(saturation_test)begin
      send(12,1);send(13,1);send(14,1);
      for(int mode=0;mode<4;mode++)begin
        int base,expected_samples,expected_events;bit prior,hit;logic [15:0] word_value;
        base=15+mode*8;
        send(base,1);send(base+1,1);wait(dut.frame_available);
        frozen=$fopen($sformatf("%s/saturation_frame_%0d.hex",folder,mode),"w");
        expected_samples=0;expected_events=0;prior=0;
        for(int i=0;i<16384;i++)begin
          word_value=dut.memory.storage.memory[(int'(dut.metadata.start_address)+i)%16384];
          $fwrite(frozen,"%04x\n",word_value);
          hit=(word_value[11:0]==0 || word_value[11:0]==4095);
          if(hit)expected_samples++;if(hit && !prior)expected_events++;prior=hit;
        end
        $fclose(frozen);
        assert(dut.saturation_bytes[63:32]==16384 &&
          dut.saturation_bytes[95:64]==expected_samples && dut.saturation_bytes[127:96]==expected_events)
          else $fatal(1,"BOARD_SATURATION_COUNT mode=%0d",mode);
        assert(dut.saturation_bytes[9]==(mode!=0))else $fatal(1,"DIAGNOSTIC_TAG");
        send(base+2,1);send(base+3,1);send(base+4,1);send(base+5,1);send(base+6,1);send(base+7,1);
        assert(dut.diagnostic_mode==0)else $fatal(1,"STOP_DID_NOT_CLEAR_DIAGNOSTIC");
      end
      module_switch=0;#10000ns;
      assert(da===14'hzzzz&&adc_clk===1'bz)else $fatal(1,"SATURATION_DISABLE_NOT_HIZ");
      $fclose(trace);$fclose(live);$fclose(fft_trace);
      $display("TEST_PASS tb_scope_board_saturation frames=4 full_words=65536 count_summary_repeat_roi_stop_hiz=PASS");$finish;
    end
    if(modes_test)begin
      // AUTO must produce a record despite an impossible rising threshold.
      send(12,1);send(13,1);send(14,1);send(15,1);send(16,1);
      wait(dut.frame_available);
      assert(dut.metadata.mode==scope_pkg::CAP_AUTO && dut.metadata.automatic_trigger)
        else $fatal(1,"AUTO_NOT_TIMEOUT");
      begin
        logic [63:0] first_time;first_time=dut.metadata.first_timestamp;
        #200us;
        assert(dut.metadata.first_timestamp==first_time && dut.frame_available)
          else $fatal(1,"AUTO_OVERWROTE_UNCONSUMED_RECORD");
        send(17,1);wait(!dut.frame_available);wait(dut.frame_available);
        assert(dut.metadata.first_timestamp!=first_time && dut.metadata.automatic_trigger)
          else $fatal(1,"AUTO_NOT_REARMED");
      end
      send(18,1);send(19,1);send(20,1);
      #1ms;
      assert(dut.cap_busy && !dut.frame_available)else $fatal(1,"NORMAL_FREERUN");
      send(21,1);send(22,1);send(23,1);wait(dut.frame_available);
      assert(dut.metadata.mode==scope_pkg::CAP_NORMAL && !dut.metadata.automatic_trigger)
        else $fatal(1,"NORMAL_NOT_EDGE");
      send(24,1);wait(!dut.frame_available);wait(dut.frame_available);
      assert(dut.metadata.mode==scope_pkg::CAP_NORMAL)else $fatal(1,"NORMAL_REARM");
      send(18,1);send(25,1);wait(!dut.frame_available);wait(dut.frame_available);
      assert(dut.metadata.mode==scope_pkg::CAP_SINGLE)else $fatal(1,"SINGLE_MODE");
      begin
        logic [63:0] single_time;single_time=dut.metadata.first_timestamp;
        #1ms;
        assert(dut.metadata.first_timestamp==single_time && dut.frame_available && !dut.cap_busy)
          else $fatal(1,"SINGLE_NOT_HOLD");
      end
      send(26,1);send(18,1);
      module_switch=0;#10000ns;
      assert(da===14'hzzzz&&adc_clk===1'bz)else $fatal(1,"MODES_DISABLE_NOT_HIZ");
      $fclose(trace);$fclose(live);
      $display("TEST_PASS tb_scope_board_capture_modes AUTO_timeout NORMAL_wait edge rearm SINGLE_hold STOP HIZ");$finish;
    end
    if(!boot_only)begin send(3,1);send(4,1);send(5,1);send(6,1);end
    send(7,1);
    wait(dut.frame_available);
    // Observation only: preserve every frozen BRAM word, then independently
    // verify first/last address translation through the physical UART pins.
    frozen=$fopen({folder,"/frozen.hex"},"w");
    for(int i=0;i<16384;i++)$fwrite(frozen,"%04x\n",dut.memory.storage.memory[(int'(dut.metadata.start_address)+i)%16384]);
    $fclose(frozen);
    send(8,1);send(9,1);send(10,1);
    if(multires_test)begin
      send(12,1);send(13,4);send(14,2);send(15,3);
      send(16,1);send(17,1);send(18,1);send(19,1);
      // Cancel after the first packet has committed. A STOP received while
      // its declared payload is in flight must finish that packet's CRC.
      send_only(20);
      wait(dut.uart.protocol.g_envelope.envelope.state==5);
      begin
        int prior_packets;prior_packets=received;
        send_only(21);wait(received==prior_packets+2);#(BIT_NS*2);
      end
      send(22,1);send(23,1);
      send(24,1);send(25,1);send(26,1);send(27,1);send(28,1);send(29,1);
    end
    if(analysis_test)begin
      send(12,1);send(13,1);send(14,1);send(15,1);send(16,1);
      send(17,1);wait(!dut.frame_available);wait(dut.frame_available);
      frozen=$fopen({folder,"/frozen2.hex"},"w");
      for(int i=0;i<16384;i++)$fwrite(frozen,"%04x\n",dut.memory.storage.memory[(int'(dut.metadata.start_address)+i)%16384]);
      $fclose(frozen);
      send(18,3);send(19,1);send(20,1);
    end
    send(11,1);
    module_switch=0;#10000ns;
    assert(da===14'hzzzz&&aclk===1'bz&&wr1===1'bz&&adc_clk===1'bz)else $fatal(1,"BOARD_DISABLE_NOT_HIZ");
    $fclose(trace);$fclose(live);
    if(analysis_test)$display("TEST_PASS tb_scope_board_analysis commands=%0d packets=%0d errors=0",commands,received);
    else if(multires_test)$display("TEST_PASS tb_scope_board_multires commands=%0d packets=%0d frame=16384 errors=0",commands,received);
    else if(boot_only)$display("TEST_PASS tb_scope_board_boot commands=%0d packets=%0d frame=16384 errors=0",commands,received);
    else $display("TEST_PASS tb_scope_board commands=%0d packets=%0d frame=16384 errors=0",commands,received);
    $finish;
  end
  initial begin #(TEST_BAUD==115200?2000000000ns:200000000ns);$fatal(1,"BOARD_WATCHDOG commands=%0d received=%0d",commands,received);end
endmodule
`default_nettype wire
