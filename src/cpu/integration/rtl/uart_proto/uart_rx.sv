`default_nettype none
module uart_rx #(parameter int unsigned CLOCK_HZ=100000000,BAUD=115200)(
  input wire logic clk,rst,rx,
  output logic out_valid,output logic [7:0] out_data,
  output logic [31:0] framing_errors,false_starts
);
  timeunit 1ns;timeprecision 1ps;
  typedef enum logic [2:0] {IDLE,START,DATA,STOP,WAIT_HIGH} state_t;
  state_t state;
  (* ASYNC_REG="TRUE" *) logic rx_meta,rx_sync;
  logic [31:0] phase;
  logic [32:0] advanced;
  logic [7:0] shift;
  logic [2:0] index;
  always_comb advanced={1'b0,phase}+(state==START?33'(2*BAUD):33'(BAUD));
  initial assert(BAUD>0 && CLOCK_HZ>=16*BAUD)else $fatal(1,"UART_RX_PARAMETER_FAIL");
  always_ff @(posedge clk)begin
    if(rst)begin rx_meta<=1;rx_sync<=1;end
    else begin rx_meta<=rx;rx_sync<=rx_meta;end
  end
  always_ff @(posedge clk)begin
    if(rst)begin state<=IDLE;phase<=0;shift<=0;index<=0;out_valid<=0;out_data<=0;framing_errors<=0;false_starts<=0;end
    else begin
      out_valid<=0;
      case(state)
        IDLE: if(!rx_sync)begin state<=START;phase<=0;end
        WAIT_HIGH: if(rx_sync)state<=IDLE;
        default: if(advanced>=33'(CLOCK_HZ))begin
          phase<=32'(advanced-33'(CLOCK_HZ));
          case(state)
            START: if(!rx_sync)begin state<=DATA;index<=0;phase<=0;end
                   else begin state<=IDLE;false_starts<=false_starts+32'd1;end
            DATA: begin shift[index]<=rx_sync;if(index==3'd7)state<=STOP;else index<=index+3'd1;end
            STOP: if(rx_sync)begin out_valid<=1;out_data<=shift;state<=IDLE;end
                  else begin framing_errors<=framing_errors+32'd1;state<=WAIT_HIGH;end
            default: state<=IDLE;
          endcase
        end else phase<=advanced[31:0];
      endcase
    end
  end
endmodule
`default_nettype wire
