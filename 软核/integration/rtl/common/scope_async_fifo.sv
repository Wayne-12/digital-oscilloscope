`default_nettype none
// Dual-clock RAM + registered FWFT output, Gray-pointer CDC. Both domains
// reset together before a session. RAM is not reset; ownership gates reads.
module scope_async_fifo #(parameter int unsigned WIDTH=34,ADDR_BITS=11)(
  input wire logic write_clk,write_rst,write_valid,
  input wire logic [WIDTH-1:0] write_data,
  output wire logic write_ready,
  input wire logic read_clk,read_rst,read_ready,
  output logic read_valid,
  output logic [WIDTH-1:0] read_data
);
  timeunit 1ns;timeprecision 1ps;
  (* ram_style="block" *) logic [WIDTH-1:0] memory[0:(1<<ADDR_BITS)-1];
  logic [ADDR_BITS:0] wb,wg,rb,rg,wn,wgn;
  (* ASYNC_REG="TRUE" *) logic [ADDR_BITS:0] rg_meta,rg_sync,wg_meta,wg_sync;
  logic full;
  assign write_ready=!full;
  always_comb begin
    wn=wb+{{ADDR_BITS{1'b0}},(write_valid && write_ready)};
    wgn=(wn>>1)^wn;
  end
  always_ff @(posedge write_clk)begin
    if(write_rst)begin wb<='0;wg<='0;rg_meta<='0;rg_sync<='0;full<=0;end
    else begin
      rg_meta<=rg;rg_sync<=rg_meta;wb<=wn;wg<=wgn;
      full<=wgn=={~rg_sync[ADDR_BITS:ADDR_BITS-1],rg_sync[ADDR_BITS-2:0]};
      if(write_valid && write_ready)memory[wb[ADDR_BITS-1:0]]<=write_data;
    end
  end
  always_ff @(posedge read_clk)begin
    if(read_rst)begin rb<='0;rg<='0;wg_meta<='0;wg_sync<='0;read_valid<=0;read_data<='0;end
    else begin
      wg_meta<=wg;wg_sync<=wg_meta;
      if(!read_valid || read_ready)begin
        if(rg!=wg_sync)begin
          read_data<=memory[rb[ADDR_BITS-1:0]];read_valid<=1;
          rb<=rb+{{ADDR_BITS{1'b0}},1'b1};rg<=((rb+{{ADDR_BITS{1'b0}},1'b1})>>1)^(rb+{{ADDR_BITS{1'b0}},1'b1});
        end else read_valid<=0;
      end
    end
  end
endmodule
`default_nettype wire
