`default_nettype none
module tb_uart_bytes;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import protocol_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst=1,in_valid=0,out_ready=0;
  logic [7:0] in_data=0;
  wire logic in_ready,out_valid;
  wire logic [7:0] out_data;
  wire logic capture_busy,capture_ready,frame_available,backend_error,measurement_error;
  wire logic [63:0] backend_timestamp;
  wire logic [31:0] backend_rate,backend_trigger_index,backend_length;
  wire measurement_result_t measurements;
  wire logic single_pulse,stop_pulse,release_pulse,acquire_enable;
  wire logic [17:0] record_length,pre_samples,sample_index;
  wire trigger_config_t trigger_config;
  wire dds_wave_t dds_wave;
  wire logic dds_enable;
  wire logic [31:0] dds_phase_inc,dds_phase_offset;
  wire logic [15:0] dds_amplitude;
  wire logic signed [17:0] dds_dc_offset;
  wire parser_errors_t parser_errors;
  wire frame_header_t last_request_header;
  wire logic [31:0] good_frames,unknown_commands,command_errors;
  wire logic sample_request,sample_ready,sample_valid;
  wire logic [15:0] sample_word;
  scope_protocol_core #(.RX_TIMEOUT_CYCLES(200)) dut(.*,
    .awg_play_index(10'd0),.awg_play_value(),.awg_selected(),
    .capture_mode(),.auto_timeout(),.spectrum_bytes(768'd0),.saturation_bytes(128'd0),.diagnostic_mode(),.uart_framing_errors(32'd0),.rx_overruns(32'd0));
  uart_capture_backend backend(.*);
  byte unsigned expected[0:2097151],accepted[0:2097151];
  int unsigned output_count=0,payload_count=0,header_count=0,stalls=0,cycles=0,pause_until=0;
  int unsigned expected_size,accepted_size,expected_frames,ec,el,ev,et,eu,ee,bulk,seed=20261020;
  int fd,hd,cf,trace,rc,op,arg;
  string vectors=".",traces=".";
  logic [31:0] random_state;
  logic held=0;logic [7:0] held_data=0;
  logic have_last=0;
  frame_header_t expected_last='0;
  int unsigned single_count=0,stop_count=0;
  always @(negedge clk)begin
    if(rst)out_ready=0;
    else begin
      random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
      out_ready=cycles>=pause_until && random_state[2:0]!=3'd0;
    end
  end
  always @(posedge clk)if(!rst)begin:monitor
    int k,s,n;logic [63:0] ts;logic [31:0] rate,ti;logic [15:0] flags;
    cycles=cycles+1;
    if(single_pulse)single_count++;
    if(stop_pulse)stop_count++;
    if(have_last)assert(last_request_header===expected_last)else $fatal(1,"UART_LAST_REQUEST_TRACE_ASSERT");
    if(held)assert(out_valid && out_data===held_data)else $fatal(1,"UART_OUTPUT_STABILITY_ASSERT");
    held=out_valid && !out_ready;held_data=out_data;
    if(in_valid && !in_ready)stalls++;
    assert(dut.receiver.count<=2048)else $fatal(1,"UART_QUEUE_COUNT_ASSERT");
    if(out_valid && out_ready)begin
      assert(output_count<expected_size && out_data===expected[output_count])
        else $fatal(1,"UART_BYTE_SCOREBOARD index=%0d expected=%02x actual=%02x",output_count,expected[output_count],out_data);
      $fwrite(trace,"%02x\n",out_data);output_count++;
    end
    if(dut.parsed_valid && dut.parsed_ready)begin
      rc=$fscanf(hd,"%h %h %h %h %h %h %h",k,s,n,ts,rate,ti,flags);
      assert(rc==7 && dut.parsed.kind==8'(k) && dut.parsed.seq==16'(s) && dut.parsed.length==16'(n) &&
        dut.parsed.timestamp==ts && dut.parsed.sample_rate==rate && dut.parsed.trigger_index==ti && dut.parsed.flags==flags)
        else $fatal(1,"UART_INPUT_HEADER_SCOREBOARD index=%0d",header_count);
      header_count++;
      have_last=1;expected_last=dut.parsed;
    end
    if(dut.parsed_payload_valid && dut.parsed_payload_ready)begin
      assert(payload_count<accepted_size && dut.parsed_payload===accepted[payload_count])else $fatal(1,"UART_INPUT_PAYLOAD_SCOREBOARD %0d",payload_count);
      payload_count++;
    end
  end
  initial begin:run
    int ln,pre,w,en,inc,ph,am,dc;int meta;
    if($value$plusargs("SEED=%d",seed))begin end
    if($value$plusargs("VECTOR_DIR=%s",vectors))begin end
    if($value$plusargs("TRACE_DIR=%s",traces))begin end
    random_state=32'(seed)|32'd1;
    meta=$fopen({vectors,"/counts.txt"},"r");assert(meta!=0)else $fatal(1,"UART_COUNTS_OPEN");
    rc=$fscanf(meta,"%d %d %d %d %d %d %d %d %d %d",expected_size,accepted_size,expected_frames,ec,el,ev,et,eu,ee,bulk);assert(rc==10)else $fatal(1,"UART_COUNTS_READ");$fclose(meta);
    $readmemh({vectors,"/expected.hex"},expected,0,expected_size-1);$readmemh({vectors,"/accepted_payload.hex"},accepted,0,accepted_size-1);
    fd=$fopen({vectors,"/actions.txt"},"r");hd=$fopen({vectors,"/headers.txt"},"r");cf=$fopen({vectors,"/configs.txt"},"r");trace=$fopen({traces,"/uart_bytes.hex"},"w");
    assert(fd && hd && cf && trace)else $fatal(1,"UART_FILE_OPEN");
    repeat(12)@(negedge clk);rst=0;
    while(!$feof(fd))begin
      rc=$fscanf(fd,"%d %d",op,arg);if(rc!=2)break;
      case(op)
        0:begin
          in_valid=1;in_data=8'(arg);
          do @(posedge clk);while(!in_ready);
          @(negedge clk);in_valid=0;
        end
        1:repeat(arg)@(negedge clk);
        2:begin wait(output_count>=arg);@(negedge clk);end
        4:begin wait(frame_available && measurements.stats_valid);@(negedge clk);end
        5:begin
          rc=$fscanf(cf,"%d %d %d %d %d %d %d %d",ln,pre,w,en,inc,ph,am,dc);
          assert(rc==8 && record_length==18'(ln) && pre_samples==18'(pre) && dds_wave==dds_wave_t'(w) && dds_enable==1'(en) &&
            dds_phase_inc==32'(inc) && dds_phase_offset==32'(ph) && dds_amplitude==16'(am) && dds_dc_offset==18'(dc))
            else $fatal(1,"UART_CONFIG_SCOREBOARD index=%0d",arg);
        end
        6:pause_until=cycles+arg;
        8:begin
          repeat(500)@(negedge clk);
          assert(output_count==expected_size && payload_count==accepted_size && header_count==expected_frames && good_frames==expected_frames)
            else $fatal(1,"UART_FINAL_COUNTS out=%0d/%0d payload=%0d/%0d frames=%0d/%0d good=%0d",output_count,expected_size,payload_count,accepted_size,header_count,expected_frames,good_frames);
          assert(parser_errors.crc==ec && parser_errors.length==el && parser_errors.version==ev && parser_errors.timeout==et && unknown_commands==eu && command_errors==ee)
            else $fatal(1,"UART_ERROR_COUNTS crc=%0d length=%0d version=%0d timeout=%0d unknown=%0d commands=%0d",parser_errors.crc,parser_errors.length,parser_errors.version,parser_errors.timeout,unknown_commands,command_errors);
          assert(stalls>0 && single_count==3 && stop_count==2 && !backend_error)else $fatal(1,"UART_COVERAGE_ASSERT stalls=%0d single=%0d stop=%0d",stalls,single_count,stop_count);
          $fclose(trace);$fclose(fd);$fclose(hd);$fclose(cf);
          $display("TEST_PASS tb_uart_bytes seed=%0d bulk=%0d frames=%0d output_bytes=%0d stalls=%0d errors=0",seed,bulk,header_count,output_count,stalls);$finish;
        end
        default:$fatal(1,"UART_BAD_ACTION %0d",op);
      endcase
    end
    $fatal(1,"UART_ACTIONS_NO_END");
  end
  initial begin #1000000000;$fatal(1,"UART_BYTE_WATCHDOG out=%0d frames=%0d state=%0d cap=%0d",output_count,header_count,dut.receiver.state,backend.cap_state);end
endmodule
`default_nettype wire
