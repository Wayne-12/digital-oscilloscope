`default_nettype none
module tb_awg;
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;import scope_pkg::*;
  logic clk=0,rst=1;always #20ns clk=~clk;
  logic hv=0,pv=0,rr=0,pr=0,rd=0;
  command_header_t header;
  wire hr,pready,rv,rpv;wire [7:0] response_payload;
  frame_header_t response;
  logic [7:0] bytes_in[0:1023],bytes_out[0:1023];
  wire [9:0] awg_play_index;wire signed [15:0] awg_play_value;
  wire awg_selected,dds_enable;wire [31:0] inc,phase;wire [15:0] amplitude;
  wire signed [17:0] offset;dds_wave_t wave;
  wire [13:0] dac;
  int pos=0,replies=0,checked=0;
  protocol_commands #(.SUPPORT_MULTIRES(1),.SUPPORT_AWG(1)) dut(
    .clk(clk),.rst(rst),.header_valid(hv),.payload_valid(pv),.header(header),.payload_data(bytes_in[pos]),
    .header_ready(hr),.payload_ready(pready),.response_valid(rv),.response_payload_valid(rpv),
    .response(response),.response_payload(response_payload),.response_ready(rr),.response_payload_ready(pr),.response_done(rd),
    .parser_errors('0),.good_frames(0),.uart_framing_errors(0),.rx_overruns(0),
    .capture_busy(1'b0),.capture_ready(1'b1),.frame_available(1'b0),.backend_error(1'b0),.wave_ready(1'b1),
    .backend_timestamp(64'd0),.backend_rate(25000000),.backend_trigger_index(0),.backend_length(16384),
    .measurements('0),.measurement_error(1'b0),.spectrum_bytes('0),.saturation_bytes('0),
    .diagnostic_mode(),.single_pulse(),.stop_pulse(),.release_pulse(),.acquire_enable(),
    .wave_request(),.wave_offset(),.wave_count(),.wave_sequence(),
    .envelope_request(),.envelope_buckets(),.envelope_sequence(),
    .record_length(),.pre_samples(),.capture_mode(),.auto_timeout(),.trigger_config(),
    .unknown_commands(),.command_errors(),
    .awg_play_index(awg_play_index),.awg_play_value(awg_play_value),.awg_selected(awg_selected),
    .dds_wave(wave),.dds_enable(dds_enable),.dds_phase_inc(inc),.dds_phase_offset(phase),
    .dds_amplitude(amplitude),.dds_dc_offset(offset));
  scope_board_dds player(.clk_dac(clk),.rst(rst),.enable(dds_enable),.waveform(wave),.phase_inc(inc),
    .phase_offset(phase),.amplitude(amplitude),.dc_offset(offset),.dac_code(dac),
    .awg_play_index(awg_play_index),.awg_play_value(awg_play_value),.awg_selected(awg_selected));
  function automatic integer value(input integer index);
    return ((index*73)%65535)-32767;
  endfunction
  task automatic request(input logic[7:0] kind,input integer length,input integer code);
    @(negedge clk);header='{kind:kind,seq:16'(replies),length:16'(length),flags:16'd0};hv=1;
    do @(posedge clk);while(!hr);
    @(negedge clk);hv=0;
    for(int i=0;i<length;i++)begin
      pos=i;pv=1;do @(posedge clk);while(!pready);@(negedge clk);
    end
    pv=0;wait(rv);assert(response.kind==(kind|8'h80))else $fatal(1,"AWG_RESPONSE_KIND");
    if(code>=0)assert(response.length==1 && response.flags==(code==0?FLAG_RESPONSE:FLAG_RESPONSE|FLAG_ERROR))else $fatal(1,"AWG_RESPONSE_FLAGS %0h",kind);
    @(negedge clk);rr=1;@(posedge clk);@(negedge clk);rr=0;pr=1;
    for(int i=0;i<response.length;i++)begin
      wait(rpv);bytes_out[i]=response_payload;@(posedge clk);@(negedge clk);
    end
    pr=0;rd=1;@(posedge clk);@(negedge clk);rd=0;
    if(code>=0)assert(bytes_out[0]==8'(code))else $fatal(1,"AWG_ACK kind=%0h got=%0d expected=%0d",kind,bytes_out[0],code);
    replies++;
  endtask
  task automatic word_in(input int at,input int val);
    bytes_in[at]=8'(val);bytes_in[at+1]=8'(val>>8);
  endtask
  task automatic upload;
    logic [15:0] crc;
    word_in(0,1024);word_in(2,0);request(CMD_AWG_BEGIN,4,0);crc=16'hffff;
    for(int start=0;start<1024;start+=256)begin
      word_in(0,start);
      for(int j=0;j<256;j++)begin
        word_in(2+j*2,value(start+j));
        crc=crc16_byte(crc16_byte(crc,8'(value(start+j))),8'(value(start+j)>>8));
      end
      request(CMD_AWG_CHUNK,514,0);
    end
    word_in(0,crc^16'h1);request(CMD_AWG_COMMIT,2,ERR_CONFIG);
    word_in(0,crc);request(CMD_AWG_COMMIT,2,0);
  endtask
  task automatic verify_table;
    for(int start=0;start<1024;start+=256)begin
      word_in(0,start);word_in(2,256);request(CMD_AWG_READ,4,-1);
      assert({bytes_out[1],bytes_out[0]}==start && {bytes_out[3],bytes_out[2]}==256)else $fatal(1,"AWG_READ_HEADER");
      for(int j=0;j<256;j++)assert($signed({bytes_out[5+j*2],bytes_out[4+j*2]})==value(start+j))else $fatal(1,"AWG_READ_VALUE index=%0d",start+j);
    end
  endtask
  initial begin
    header='0;for(int i=0;i<1024;i++)bytes_in[i]=0;
    repeat(4)@(negedge clk);rst=0;
    bytes_in[0]=1;request(CMD_AWG_SELECT,1,ERR_CONFIG);
    upload();verify_table();request(CMD_AWG_STATUS,0,-1);
    assert(bytes_out[0]==1 && bytes_out[1]==1 && {bytes_out[5],bytes_out[4]}==1024)else $fatal(1,"AWG_STATUS");
    // A rejected/partial replacement never changes the committed bank.
    word_in(0,1024);word_in(2,0);request(CMD_AWG_BEGIN,4,0);
    word_in(0,0);word_in(2,16'h8000);request(CMD_AWG_CHUNK,4,ERR_CONFIG);
    word_in(0,1);word_in(2,123);request(CMD_AWG_CHUNK,4,ERR_CONFIG);
    word_in(0,0);request(CMD_AWG_COMMIT,2,ERR_CONFIG);verify_table();
    bytes_in[0]=1;request(CMD_AWG_SELECT,1,0);
    for(int i=0;i<16;i++)bytes_in[i]=0;
    bytes_in[1]=1;word_in(2,24414);word_in(10,819);request(CMD_DDS,16,0);
    // Restart the DDS deterministically, then compare >2 table periods.
    @(negedge clk);rst=1;@(negedge clk);rst=0;
    upload();bytes_in[0]=1;request(CMD_AWG_SELECT,1,0);
    for(int i=0;i<16;i++)bytes_in[i]=0;
    bytes_in[1]=1;word_in(2,24414);word_in(10,819);
    // Track from the exact enable transition, independently of response time.
    fork
      request(CMD_DDS,16,0);
      begin: compare
        logic [31:0] acc;integer x,scaled,expected;
        wait(dds_enable);acc=0;
        for(int n=0;n<2070;n++)begin
          @(negedge clk);#1ns;
          if(n>=4)begin
            x=value(acc[31:22]);scaled=( (x<0?-x:x)*819+16383)/32767;
            expected=8192+(x<0?-scaled:scaled);
            assert(dac===14'(expected))else $fatal(1,"AWG_DAC n=%0d got=%0d expected=%0d",n,dac,expected);
            acc=acc+inc;checked++;
          end
        end
      end
    join
    word_in(0,1024);word_in(2,0);request(CMD_AWG_BEGIN,4,ERR_BUSY);
    $display("TEST_PASS tb_awg replies=%0d dac_codes=%0d errors=0",replies,checked);$finish;
  end
  initial begin #10ms;$fatal(1,"AWG_WATCHDOG");end
endmodule
`default_nettype wire
