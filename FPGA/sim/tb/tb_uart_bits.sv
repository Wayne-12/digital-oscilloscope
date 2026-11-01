`default_nettype none
module tb_uart_bits;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import protocol_pkg::*;
  localparam realtime BIT_NS=1000000000.0/115200.0;
  logic clk=0;always #5 clk=~clk;
  logic rst=1,rx=1,gate_rx=0;
  wire logic tx,tx_valid,tx_ready,rx_valid,core_ready;
  wire logic [7:0] tx_data,rx_data;
  wire logic [31:0] rx_overruns,tx_stall_cycles,framing_errors,false_starts;
  uart_transport #(.FIFO_ADDR_BITS(2)) transport(.clk(clk),.rst(rst),.rx(rx),.tx(tx),.tx_valid(tx_valid),.tx_ready(tx_ready),.tx_data(tx_data),
    .rx_valid(rx_valid),.rx_ready(gate_rx && core_ready),.rx_data(rx_data),.rx_overruns(rx_overruns),.tx_stall_cycles(tx_stall_cycles),.framing_errors(framing_errors),.false_starts(false_starts));
  wire parser_errors_t parser_errors;
  wire logic [31:0] good_frames,unknown_commands,command_errors;
  scope_protocol_core dut(.awg_play_index(10'd0),.awg_play_value(),.awg_selected(),
    .clk(clk),.rst(rst),.spectrum_bytes(768'd0),.saturation_bytes(128'd0),.diagnostic_mode(),.in_valid(gate_rx && rx_valid),.in_ready(core_ready),.in_data(rx_data),.out_valid(tx_valid),.out_ready(tx_ready),.out_data(tx_data),
    .uart_framing_errors(framing_errors),.rx_overruns(rx_overruns),.capture_busy(1'b0),.capture_ready(1'b1),.frame_available(1'b1),.backend_error(1'b0),
    .backend_timestamp(64'hfffffffffffffff0),.backend_rate(32'd25000000),.backend_trigger_index(32'd8192),.backend_length(32'd16384),
    .measurements(measurement_result_t'('0)),.measurement_error(1'b0),.parser_errors(parser_errors),.good_frames(good_frames),.unknown_commands(unknown_commands),.command_errors(command_errors),.last_request_header(),
    .single_pulse(),.stop_pulse(),.release_pulse(),.acquire_enable(),.capture_mode(),.auto_timeout(),.record_length(),.pre_samples(),.trigger_config(),.dds_wave(),.dds_enable(),
    .dds_phase_inc(),.dds_phase_offset(),.dds_amplitude(),.dds_dc_offset(),.sample_request(),.sample_index(),.sample_ready(1'b0),.sample_valid(1'b0),.sample_word(16'd0));
  byte unsigned inputs[0:1023],expected[0:1023];
  int unsigned input_size,expected_size,received=0,rx_count=0,timing_checks=0,rx_checks=0,sample_checks=0,cycle=0,start_cycle=0;
  bit sender_active=0;
  realtime sender_start=0,sender_period=0;
  int trace,rc,meta;
  string vectors=".",traces=".";
  logic previous_busy=0;logic [3:0] previous_index=0;
  always @(posedge clk)begin
    cycle++;
    if(!rst && sender_active && transport.receiver.state==3'd2 && transport.receiver.advanced>=33'd100000000)begin
      realtime elapsed;
      elapsed=$realtime-sender_start;
      assert(elapsed>(real'(transport.receiver.index)+1.25)*sender_period && elapsed<(real'(transport.receiver.index)+1.75)*sender_period)
        else $fatal(1,"UART_RX_SAMPLE_POINT_ASSERT bit=%0d elapsed=%0t",transport.receiver.index,elapsed);
      sample_checks++;
    end
    if(!rst && gate_rx && rx_valid && core_ready)begin
      if(rx_count<4)assert(rx_data==8'(17+rx_count))else $fatal(1,"UART_RX_FIFO_ORDER_ASSERT");
      else assert(rx_count-4<input_size && rx_data===inputs[rx_count-4])else $fatal(1,"UART_RX_BIT_SCOREBOARD %0d actual=%02x",rx_count-4,rx_data);
      rx_count++;rx_checks++;
    end
    #0.001;
    if(!rst)begin
      if(transport.transmitter.busy && !previous_busy)start_cycle=cycle;
      else if(previous_busy && (!transport.transmitter.busy || transport.transmitter.index!=previous_index))begin
        int n,elapsed,ideal;
        n=transport.transmitter.busy?int'(transport.transmitter.index):10;
        elapsed=cycle-start_cycle;ideal=(n*100000000+115199)/115200;
        assert(elapsed==ideal)else $fatal(1,"UART_FRACTIONAL_BIT_ASSERT n=%0d cycles=%0d expected=%0d",n,elapsed,ideal);
        timing_checks++;
      end
    end
    previous_busy=transport.transmitter.busy;previous_index=transport.transmitter.index;
  end
  // Decode TX pins with an independent real-time 8N1 receiver.
  initial begin:decode
    logic [7:0] data;
    wait(!rst);
    forever begin
      @(negedge tx);#(BIT_NS/2.0);assert(tx===1'b0)else $fatal(1,"UART_TX_START_ASSERT");
      for(int b=0;b<8;b++)begin #(BIT_NS);data[b]=tx;end
      #(BIT_NS);assert(tx===1'b1)else $fatal(1,"UART_TX_STOP_ASSERT");
      assert(received<expected_size && data===expected[received])else $fatal(1,"UART_TX_BIT_SCOREBOARD index=%0d expected=%02x actual=%02x",received,expected[received],data);
      $fwrite(trace,"%02x\n",data);received++;
    end
  end
  task automatic send_byte(input logic [7:0] value,input realtime period,input bit good_stop=1);
    sender_start=$realtime;sender_period=period;sender_active=1;rx=0;#(period);
    for(int b=0;b<8;b++)begin rx=value[b];#(period);end
    rx=good_stop;#(period);rx=1;sender_active=0;
  endtask
  initial begin:run
    if($value$plusargs("VECTOR_DIR=%s",vectors))begin end
    if($value$plusargs("TRACE_DIR=%s",traces))begin end
    meta=$fopen({vectors,"/bit_counts.txt"},"r");assert(meta)else $fatal(1,"UART_BIT_COUNTS_OPEN");
    rc=$fscanf(meta,"%d %d",input_size,expected_size);assert(rc==2)else $fatal(1,"UART_BIT_COUNTS_READ");$fclose(meta);
    $readmemh({vectors,"/bit_input.hex"},inputs,0,input_size-1);$readmemh({vectors,"/bit_expected.hex"},expected,0,expected_size-1);
    trace=$fopen({traces,"/uart_bits.hex"},"w");assert(trace)else $fatal(1,"UART_BIT_TRACE_OPEN");
    repeat(12)@(negedge clk);rst=0;#(2*BIT_NS);
    // RX cannot stop a wire sender: prove exact overflow count, then recover.
    for(int i=0;i<8;i++)send_byte(8'(17+i),BIT_NS);
    #(BIT_NS);assert(rx_overruns==4)else $fatal(1,"UART_OVERRUN_COUNT_ASSERT %0d",rx_overruns);
    gate_rx=1;#(2*BIT_NS);
    rx=0;#2000;rx=1;#(2*BIT_NS);
    assert(false_starts==1)else $fatal(1,"UART_FALSE_START_ASSERT %0d",false_starts);
    send_byte(8'he1,BIT_NS,0);rx=0;#(2*BIT_NS);rx=1;#(2*BIT_NS);
    assert(framing_errors==1)else $fatal(1,"UART_STOP_ERROR_ASSERT %0d",framing_errors);
    for(int i=0;i<input_size;i++)begin
      // Entire frames at nominal baud, +2% bit period and -2% bit period.
      send_byte(inputs[i],i<32?BIT_NS:(i<60?BIT_NS*1.02:BIT_NS*0.98));
    end
    wait(received==expected_size);#(2*BIT_NS);
    assert(rx_count==input_size+4 && good_frames==3 && parser_errors=='0 && unknown_commands==0 && command_errors==0 &&
      rx_overruns==4 && false_starts==1 && framing_errors==1 && tx_stall_cycles>0 && timing_checks==10*expected_size && sample_checks==8*(input_size+9))
      else $fatal(1,"UART_BIT_FINAL_ASSERT rx=%0d frames=%0d errors=%h stalls=%0d timing=%0d",rx_count,good_frames,parser_errors,tx_stall_cycles,timing_checks);
    $fclose(trace);$display("TEST_PASS tb_uart_bits rx_bytes=%0d tx_bytes=%0d timing_checks=%0d sample_checks=%0d overflow=4 framing=1 false_start=1 errors=0",rx_count,received,timing_checks,sample_checks);$finish;
  end
  initial begin #100000000;$fatal(1,"UART_BIT_WATCHDOG received=%0d rx=%0d frames=%0d",received,rx_count,good_frames);end
endmodule
`default_nettype wire
