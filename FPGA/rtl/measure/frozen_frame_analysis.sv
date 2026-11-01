`default_nettype none
// Own the frozen BRAM read port until both summaries have completed. The UART
// sees this frame only afterwards, so results and samples always share identity.
module frozen_frame_analysis (
  input wire clk,rst,frame_ready,frame_diagnostic,
  input wire [63:0] first_timestamp,
  input wire scope_pkg::adc_sample_t threshold,
  input wire [12:0] hysteresis,
  output wire read_request,
  output wire [13:0] read_index,
  input wire read_valid,
  input wire [15:0] read_word,
  output wire done,
  output scope_pkg::measurement_result_t measurements,
  output wire measurement_error,
  output wire [127:0] saturation_bytes,
  output logic [767:0] spectrum_bytes
);
  timeunit 1ns; timeprecision 1ps;
  import scope_pkg::*;
  import spectrum_pkg::*;
  typedef enum logic [3:0] {BEGIN_MEASURE,MEASURE_READ,MEASURE_WAIT,
    BEGIN_FFT,FFT_READ,FFT_WAIT,HARM_READ,HARM_LOAD,HARM_SCAN,HARM_SQRT,HARM_WAIT,COMPLETE} state_t;
  state_t state;
  logic [13:0] index;
  logic pending,failed;
  logic [19:0] watchdog;
  wire reset_analysis=rst || !frame_ready;
  wire mready,mdone,merror;
  wire sready,sstart,svalid,serror;
  spectrum_result_t spectral_result;
  spectrum_bin_t bin_data;
  wire bin_valid;
  (* ram_style="block" *) logic [63:0] powers[0:511];
  logic [8:0] candidate_index;
  logic [63:0] power_word;
  logic [10:0] fundamental;
  logic [2:0] harmonic;
  logic [10:0] harmonic_bin;
  logic [63:0] harmonic_power;
  wire [32:0] root;
  wire root_done;
  wire [31:0] harmonic_center={18'd0,fundamental}*{29'd0,harmonic};
  assign read_request=!pending && ((state==MEASURE_READ && mready) || (state==FFT_READ && sready));
  assign read_index=index;
  assign done=state==COMPLETE;
  assign measurement_error=merror || failed;
  wire [14:0] scanned,saturated,events;
  frame_saturation_counter saturation(.clk(clk),.clear(reset_analysis),
    .accept(state==MEASURE_READ && pending && read_valid),.raw_code(read_word[11:0]),
    .samples(scanned),.saturated_samples(saturated),.events(events));
  assign saturation_bytes={17'd0,events,17'd0,saturated,17'd0,scanned,16'd0,
    6'd0,frame_diagnostic,(done && !measurement_error),8'd1};
  measurement_core measure(.clk(clk),.rst(reset_analysis),.start(state==BEGIN_MEASURE),
    .frame_length(18'd16384),.sample_rate_hz(32'd25000000),.threshold(threshold),.hysteresis(hysteresis),
    .sample_valid(state==MEASURE_READ && pending && read_valid),.sample_signed(adc_raw_to_signed(read_word[11:0])),
    .sample_timestamp(first_timestamp+{50'd0,index}),.sample_ready(mready),.busy(),
    .measurement_done(mdone),.measurement_valid(),.measurement_error(merror),.result(measurements));
  spectrum_analyzer spectrum(.clk(clk),.rst(reset_analysis),.module_enable(1'b1),
    .start(state==BEGIN_FFT),.start_ready(sstart),.cfg_hann(1'b1),.cfg_sample_rate(32'd25000000),
    .cfg_first_timestamp(first_timestamp),.cfg_source_first_index(18'd0),.cfg_threshold_q16(32'd131072),
    .sample_valid(state==FFT_READ && pending && read_valid),.sample_ready(sready),
    .sample_signed(adc_raw_to_signed(read_word[11:0])),.sample_otr(read_word[15]),
    .sample_timestamp(first_timestamp+{50'd0,index}),.sample_last(index==14'd1023),
    .metadata_valid(),.metadata_ready(1'b1),.metadata(),.bin_valid(bin_valid),.bin_ready(1'b1),.bin_data(bin_data),
    .result_valid(svalid),.result_ready(1'b1),.result(spectral_result),.config_error(serror),.cancelled());
  always_ff @(posedge clk) begin
    if(bin_valid && bin_data.index<11'd512) powers[bin_data.index[8:0]]<=bin_data.power;
    power_word<=powers[candidate_index];
  end
  spectrum_isqrt sqrt(.clk(clk),.rst(reset_analysis),.start(state==HARM_SQRT),
    .radicand(harmonic_power<<10),.busy(),.done(root_done),.rounded_root(root));
  always_ff @(posedge clk) begin
    if(reset_analysis)begin
      state<=BEGIN_MEASURE;index<=0;pending<=0;failed<=0;watchdog<=0;
      spectrum_bytes<='0;fundamental<=0;harmonic<=2;harmonic_bin<=0;harmonic_power<=0;candidate_index<=0;
    end else begin
      if(state!=COMPLETE)watchdog<=watchdog+1'b1;
      if(read_request)pending<=1;
      if(pending && read_valid)begin
        pending<=0;
        if(state==MEASURE_READ && index==14'd16383)state<=MEASURE_WAIT;
        else if(state==FFT_READ && index==14'd1023)state<=FFT_WAIT;
        else index<=index+1'b1;
      end
      case(state)
        BEGIN_MEASURE:state<=MEASURE_READ;
        MEASURE_WAIT:if(mdone)begin index<=0;state<=BEGIN_FFT;end
        BEGIN_FFT:if(sstart)state<=FFT_READ;
        FFT_WAIT:if(svalid)begin
          // LE v1 payload: status, geometry, dominant AC peak, H2..H5.
          spectrum_bytes[7:0]<=8'd1;
          spectrum_bytes[15:8]<={6'd0,spectral_result.clipped,spectral_result.measurement_valid};
          spectrum_bytes[47:32]<=16'd1024;spectrum_bytes[55:48]<=8'd1;
          spectrum_bytes[95:64]<=32'd0;
          spectrum_bytes[111:96]<={5'd0,spectral_result.peak_bin};
          spectrum_bytes[159:128]<=spectral_result.frequency_hz;
          spectrum_bytes[191:160]<=spectral_result.amplitude_q16;
          spectrum_bytes[223:192]<=spectral_result.rms_q16;
          spectrum_bytes[255:224]<=spectral_result.dc_mean_q16;
          fundamental<=spectral_result.peak_bin;harmonic<=2;state<=HARM_READ;
        end
        HARM_READ:begin
          harmonic_bin<=harmonic_center[10:0];harmonic_power<=0;
          candidate_index<=9'(harmonic_center-1);
          if(fundamental>=11'd4 && harmonic_center<32'd511)state<=HARM_LOAD;
          else state<=HARM_SQRT;
        end
        HARM_LOAD:state<=HARM_SCAN;
        HARM_SCAN:begin
          if(power_word>harmonic_power)begin harmonic_power<=power_word;harmonic_bin<={2'd0,candidate_index};end
          if({23'd0,candidate_index}==harmonic_center+1)state<=HARM_SQRT;
          else begin candidate_index<=candidate_index+1'b1;state<=HARM_LOAD;end
        end
        HARM_SQRT:state<=HARM_WAIT;
        HARM_WAIT:if(root_done)begin
          spectrum_bytes[256+(32'(harmonic)-2)*128+:8]<=8'(harmonic);
          spectrum_bytes[264+(32'(harmonic)-2)*128+:8]<=8'(fundamental>=4 && harmonic_center<511);
          spectrum_bytes[272+(32'(harmonic)-2)*128+:16]<=16'(harmonic_bin);
          spectrum_bytes[288+(32'(harmonic)-2)*128+:32]<=32'((64'(harmonic_bin)*64'd25000000+64'd512)>>10);
          spectrum_bytes[320+(32'(harmonic)-2)*128+:32]<=root[31:0];
          if(harmonic==5)state<=COMPLETE;else begin harmonic<=harmonic+1'b1;state<=HARM_READ;end
        end
        default:begin end
      endcase
      if((watchdog==20'd999999 || serror) && state!=COMPLETE)begin
        failed<=1;spectrum_bytes<='0;spectrum_bytes[23:16]<=8'd1;state<=COMPLETE;
      end
    end
  end
endmodule
`default_nettype wire

