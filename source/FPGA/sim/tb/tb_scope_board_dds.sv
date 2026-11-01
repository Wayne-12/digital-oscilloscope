`default_nettype none
module tb_scope_board_dds;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;
  logic clk=0,rst=1,enable=0;always #20ns clk=~clk;
  dds_wave_t waveform=DDS_SINE;
  logic [31:0] phase_inc=0,phase_offset=0;
  logic [15:0] amplitude=0;
  logic signed [17:0] dc_offset=0;
  wire [13:0] code,reference_code;
  logic [13:0] history[0:2];int compared=0;
  scope_board_dds dut(.clk_dac(clk),.rst(rst),.enable(enable),.waveform(waveform),
    .awg_selected(1'b0),.awg_play_value(16'sd0),.awg_play_index(),
    .phase_inc(phase_inc),.phase_offset(phase_offset),.amplitude(amplitude),.dc_offset(dc_offset),.dac_code(code));
  dds_core reference_dds(.clk_dac(clk),.rst(rst),.enable(enable),.waveform(waveform),
    .phase_inc(phase_inc),.phase_offset(phase_offset),.amplitude(amplitude),.dc_offset(dc_offset),
    .dac_code(reference_code),.sample_phase(),.sample_valid());
  initial begin
    for(int wave_index=0;wave_index<4;wave_index++)begin
      for(int config_index=0;config_index<16;config_index++)begin
        @(posedge clk);rst=1;enable=0;repeat(3)@(posedge clk);
        waveform=dds_wave_t'(wave_index);
        case(config_index%4)
          0:amplitude=0;1:amplitude=1;2:amplitude=819;3:amplitude=16383;
        endcase
        case(config_index/4)
          0:dc_offset=0;1:dc_offset=-18'sd131072;2:dc_offset=18'sd131071;3:dc_offset=-18'sd1234;
        endcase
        phase_inc=32'h00400000;phase_offset=32'h3456789a;
        for(int k=0;k<3;k++)history[k]=14'd8192;
        rst=0;enable=1;
        for(int n=0;n<1032;n++)begin
          @(posedge clk);
          if(n>=5)begin
            assert(code===history[2])else $fatal(1,"BOARD_DDS_DIFFER wave=%0d config=%0d n=%0d got=%0d expected=%0d",wave_index,config_index,n,code,history[2]);
            compared++;
          end
          history[2]=history[1];history[1]=history[0];history[0]=reference_code;
        end
        enable=0;@(posedge clk);assert(code==14'd8192)else $fatal(1,"BOARD_DDS_DISABLE");
      end
    end
    $display("TEST_PASS tb_scope_board_dds compared=%0d errors=0",compared);$finish;
  end
  initial begin #5ms;$fatal(1,"BOARD_DDS_WATCHDOG");end
endmodule
`default_nettype wire
