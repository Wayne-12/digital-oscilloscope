`default_nettype none
module uart_transport #(parameter int unsigned CLOCK_HZ=100000000,BAUD=115200,FIFO_ADDR_BITS=8)(
  input wire logic clk,rst,rx,tx_valid,rx_ready,
  input wire logic [7:0] tx_data,
  output wire logic tx,tx_ready,rx_valid,
  output wire logic [7:0] rx_data,
  output logic [31:0] rx_overruns,tx_stall_cycles,
  output wire logic [31:0] framing_errors,false_starts
);
  timeunit 1ns;timeprecision 1ps;
  wire logic incoming,rx_space,serial_ready,queued;
  wire logic [7:0] received,outgoing;
  wire logic [FIFO_ADDR_BITS:0] rx_count,tx_count;
  wire logic tx_done,tx_busy;
  uart_rx #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD)) receiver(.clk(clk),.rst(rst),.rx(rx),.out_valid(incoming),.out_data(received),.framing_errors(framing_errors),.false_starts(false_starts));
  byte_fifo #(.ADDR_BITS(FIFO_ADDR_BITS)) receive_queue(.clk(clk),.rst(rst),.in_valid(incoming),.in_data(received),.in_ready(rx_space),.out_ready(rx_ready),.out_valid(rx_valid),.out_data(rx_data),.count(rx_count));
  byte_fifo #(.ADDR_BITS(FIFO_ADDR_BITS)) transmit_queue(.clk(clk),.rst(rst),.in_valid(tx_valid),.in_data(tx_data),.in_ready(tx_ready),.out_ready(serial_ready),.out_valid(queued),.out_data(outgoing),.count(tx_count));
  uart_tx #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD)) transmitter(.clk(clk),.rst(rst),.in_valid(queued),.in_data(outgoing),.in_ready(serial_ready),.tx(tx),.done(tx_done),.busy(tx_busy));
  always_ff @(posedge clk)begin
    if(rst)begin rx_overruns<=0;tx_stall_cycles<=0;end
    else begin
      if(incoming && !rx_space)rx_overruns<=rx_overruns+32'd1;
      if(tx_valid && !tx_ready)tx_stall_cycles<=tx_stall_cycles+32'd1;
    end
  end
endmodule
`default_nettype wire
