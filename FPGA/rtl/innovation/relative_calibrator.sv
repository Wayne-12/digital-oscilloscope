`default_nettype none
// Fit y(Q16 ADC codes) = gain(Q20 ADC/DAC)*x(integer DAC offset)+offset.
// <=32 points, |x|<=8192, |y|<=2048*65536: signed 64-bit intermediates
// need <56 bits including the Q16->Q20 shift. Nearest, ties away from zero.
module relative_calibrator(
  input wire clk,rst,module_enable,start,
  input wire [5:0] cfg_points,
  input wire [31:0] cfg_nominal_gain_q20,
  output wire start_ready,point_ready,
  input wire point_valid,
  input wire signed [13:0] point_x,
  input wire signed [31:0] point_mean_q16,
  output logic done,fit_valid,fit_error,
  output logic signed [31:0] gain_q20,offset_q16,correction_q20
);
  timeunit 1ns;timeprecision 1ps;
  typedef enum logic [3:0] {IDLE,POINTS,PREP,GAIN_START,GAIN_WAIT,OFFSET_START,OFFSET_WAIT,CORR_START,CORR_WAIT,FINISH} state_t;
  state_t state;
  logic [5:0] n,count;
  logic [31:0] nominal;
  // Bounds for 32 points: |sum x|<=2^18, |sum yQ16|<=2^32,
  // sum x^2<=2^31, |sum x*yQ16|<=2^45. Extra sign/headroom bits below.
  logic signed [19:0] sx;
  logic signed [33:0] sy,sxx;
  logic signed [47:0] sxy;
  logic signed [63:0] x,y,gain_num,den,intercept_num,selected_num;
  logic [63:0] selected_den,quotient,remainder,rounded;
  wire divider_done,divider_busy;
  assign start_ready=state==IDLE && module_enable && !rst;
  assign point_ready=state==POINTS && module_enable && !rst;
  always_comb begin
    x=$signed({{50{point_x[13]}},point_x});y=$signed({{32{point_mean_q16[31]}},point_mean_q16});
    gain_num=($signed({58'd0,n})*sxy-sx*sy)<<<4;
    den=$signed({58'd0,n})*sxx-sx*sx;
    intercept_num=(sy<<<4)-$signed({{32{gain_q20[31]}},gain_q20})*sx;
    selected_num=gain_num;selected_den=64'(den);
    if(state==OFFSET_START || state==OFFSET_WAIT)begin selected_num=intercept_num;selected_den={58'd0,n}<<4;end
    if(state==CORR_START || state==CORR_WAIT)begin
      selected_num=$signed({32'd0,nominal})<<<20;
      if(gain_q20<32'sd0)selected_num=-selected_num;
      selected_den=gain_q20<32'sd0 ?64'(-$signed({{32{gain_q20[31]}},gain_q20})):64'($signed({{32{gain_q20[31]}},gain_q20}));
    end
    rounded=quotient+((remainder>=(selected_den>>1)+(selected_den&64'd1))?64'd1:64'd0);
  end
  measure_udiv divide(.clk(clk),.rst(rst || !module_enable),.start(state==GAIN_START || state==OFFSET_START || state==CORR_START),
    .dividend(selected_num<64'sd0 ?64'(-selected_num):64'(selected_num)),.divisor(selected_den),
    .busy(divider_busy),.done(divider_done),.quotient(quotient),.remainder(remainder));
  always_ff @(posedge clk)begin
    if(rst)begin
      state<=IDLE;n<=0;count<=0;nominal<=0;sx<=0;sy<=0;sxx<=0;sxy<=0;
      done<=0;fit_valid<=0;fit_error<=0;gain_q20<=0;offset_q16<=0;correction_q20<=0;
    end else begin
      done<=0;
      if(!module_enable)begin state<=IDLE;fit_valid<=0;fit_error<=0;gain_q20<=0;offset_q16<=0;correction_q20<=0;end
      else case(state)
        IDLE:if(start)begin
          fit_valid<=0;fit_error<=0;gain_q20<=0;offset_q16<=0;correction_q20<=0;
          if(cfg_points<6'd2 || cfg_points>6'd32 || cfg_nominal_gain_q20==0 || cfg_nominal_gain_q20>32'd1048576)begin fit_error<=1;state<=FINISH;end
          else begin n<=cfg_points;nominal<=cfg_nominal_gain_q20;count<=0;sx<=0;sy<=0;sxx<=0;sxy<=0;state<=POINTS;end
        end
        POINTS:if(point_valid)begin
          if(y< -64'sd134217728 || y>64'sd134152192)begin fit_error<=1;state<=FINISH;end
          else begin
            sx<=sx+x;sy<=sy+y;sxx<=sxx+x*x;sxy<=sxy+x*y;count<=count+6'd1;
            if(count==n-6'd1)state<=PREP;
          end
        end
        PREP:if(den<=64'sd0)begin fit_error<=1;state<=FINISH;end else state<=GAIN_START;
        GAIN_START:state<=GAIN_WAIT;
        GAIN_WAIT:if(divider_done)begin
          if(rounded<64'd16384 || rounded>64'd4194304)begin fit_error<=1;state<=FINISH;end
          else begin gain_q20<=selected_num<0 ? -32'(rounded):32'(rounded);state<=OFFSET_START;end
        end
        OFFSET_START:state<=OFFSET_WAIT;
        OFFSET_WAIT:if(divider_done)begin
          if(rounded>64'd134217728)begin fit_error<=1;state<=FINISH;end
          else begin offset_q16<=selected_num<0 ? -32'(rounded):32'(rounded);state<=CORR_START;end
        end
        CORR_START:state<=CORR_WAIT;
        CORR_WAIT:if(divider_done)begin
          if(rounded>64'd67108864)begin fit_error<=1;state<=FINISH;end
          else begin correction_q20<=selected_num<0 ? -32'(rounded):32'(rounded);fit_valid<=1;state<=FINISH;end
        end
        FINISH:begin done<=1;state<=IDLE;end
        default:begin fit_error<=1;state<=FINISH;end
      endcase
    end
  end
endmodule
`default_nettype wire
