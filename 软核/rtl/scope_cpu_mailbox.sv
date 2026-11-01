`default_nettype none
// PG116 synchronous external I/O bus. Four independent byte FIFOs.
module scope_cpu_mailbox(
 input wire clk,rst,io_strobe,io_read,io_write,
 input wire [31:0] io_address,io_wdata,
 input wire [3:0] io_be,
 output logic [31:0] io_rdata,
 output wire io_ready,
 input wire host_valid,backend_valid,
 input wire [7:0] host_data,backend_data,
 output wire host_ready,backend_ready,
 output wire request_valid,response_valid,
 output wire [7:0] request_data,response_data,
 input wire request_ready,response_ready
);
 timeunit 1ns; timeprecision 1ps;
 wire [7:0] host_q,backend_q;
 wire host_q_valid,backend_q_valid,request_space,response_space;
 wire selected=io_address[31:8]==24'hc00000 && io_address[1:0]==0;
 wire [7:0] address=io_address[7:0];
 wire read_host=selected && address==8;
 wire read_backend=selected && address==16;
 wire write_request=selected && address==12 && io_be[0];
 wire write_response=selected && address==20 && io_be[0];
 // A transaction commits exactly on the strobe/ready edge. A stalled bus
 // holds address, data and strobes. No speculative FIFO pops.
 assign io_ready=io_strobe && !rst &&
  (!io_read || (!read_host || host_q_valid) && (!read_backend || backend_q_valid)) &&
  (!io_write || (!write_request || request_space) && (!write_response || response_space));
 wire commit=io_strobe && io_ready;
 logic [31:0] heartbeat;
 always_ff @(posedge clk) begin
  if(rst) heartbeat<=0;
  else if(commit && io_write && selected && address==24 && &io_be) heartbeat<=io_wdata;
 end
 always_comb begin
  io_rdata=0;
  if(selected) case(address)
   0:io_rdata=32'h53435031;
   4:io_rdata={28'd0,response_space,backend_q_valid,request_space,host_q_valid};
   8:io_rdata={24'd0,host_q};
   16:io_rdata={24'd0,backend_q};
   24:io_rdata=heartbeat;
   default:io_rdata=0;
  endcase
 end
 byte_fifo #(.ADDR_BITS(8)) host_rx(.clk(clk),.rst(rst),.in_valid(host_valid),.in_data(host_data),.in_ready(host_ready),
  .out_valid(host_q_valid),.out_data(host_q),.out_ready(commit && io_read && read_host),.count());
 byte_fifo #(.ADDR_BITS(8)) hw_tx(.clk(clk),.rst(rst),.in_valid(commit && io_write && write_request),.in_data(io_wdata[7:0]),.in_ready(request_space),
  .out_valid(request_valid),.out_data(request_data),.out_ready(request_ready),.count());
 byte_fifo #(.ADDR_BITS(8)) hw_rx(.clk(clk),.rst(rst),.in_valid(backend_valid),.in_data(backend_data),.in_ready(backend_ready),
  .out_valid(backend_q_valid),.out_data(backend_q),.out_ready(commit && io_read && read_backend),.count());
 byte_fifo #(.ADDR_BITS(8)) host_tx(.clk(clk),.rst(rst),.in_valid(commit && io_write && write_response),.in_data(io_wdata[7:0]),.in_ready(response_space),
  .out_valid(response_valid),.out_data(response_data),.out_ready(response_ready),.count());
endmodule
`default_nettype wire
