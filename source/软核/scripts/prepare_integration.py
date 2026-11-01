"""Create an isolated RTL snapshot; never edits the working scope implementation."""
from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parents[1]
project=root.parent
source=project/'FPGA'/'rtl'
dest=root/'integration'/'rtl'
dest.mkdir(parents=True,exist_ok=True)
manifest={}
for p in source.rglob('*.sv'):
    target=dest/p.relative_to(source)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,target)
    manifest[str(p.relative_to(project))]=hashlib.sha256(p.read_bytes()).hexdigest()
endpoint=(source/'uart_proto/scope_uart_endpoint.sv').read_text(encoding='utf-8')
endpoint=endpoint.replace('module scope_uart_endpoint #','module scope_cpu_endpoint #')
begin=endpoint.index('  uart_transport #')
end=endpoint.index('  scope_protocol_core #',begin)
endpoint=endpoint[:begin]+'''
  wire host_valid,host_ready,response_valid,response_ready;
  wire [7:0] host_data,response_data;
  wire io_strobe,io_read,io_write,io_ready;
  wire [31:0] io_address,io_wdata,io_rdata;
  wire [3:0] io_be;
  scope_microblaze cpu(.Clk(clk),.Reset(rst),
    .IO_addr_strobe(io_strobe),.IO_read_strobe(io_read),.IO_write_strobe(io_write),
    .IO_address(io_address),.IO_byte_enable(io_be),.IO_write_data(io_wdata),
    .IO_read_data(io_rdata),.IO_ready(io_ready));
  scope_cpu_mailbox mailbox(.clk(clk),.rst(rst),
    .io_strobe(io_strobe),.io_read(io_read),.io_write(io_write),.io_ready(io_ready),
    .io_address(io_address),.io_wdata(io_wdata),.io_rdata(io_rdata),.io_be(io_be),
    .host_valid(host_valid),.host_ready(host_ready),.host_data(host_data),
    .response_valid(response_valid),.response_ready(response_ready),.response_data(response_data),
    .backend_valid(tx_byte_valid),.backend_ready(tx_byte_ready),.backend_data(tx_byte),
    .request_valid(rx_byte_valid),.request_ready(rx_byte_ready),.request_data(rx_byte));
  uart_transport #(.CLOCK_HZ(CLOCK_HZ),.BAUD(BAUD),.FIFO_ADDR_BITS(10)) transport(
    .clk(clk),.rst(rst),.rx(uart_rx_pin),.tx(uart_tx_pin),
    .tx_valid(response_valid),.tx_ready(response_ready),.tx_data(response_data),
    .rx_valid(host_valid),.rx_ready(host_ready),.rx_data(host_data),
    .rx_overruns(rx_overruns),.tx_stall_cycles(tx_stall_cycles),
    .framing_errors(uart_framing_errors),.false_starts(false_starts));
''' + endpoint[end:]
(root/'rtl/scope_cpu_endpoint.sv').write_text(endpoint,encoding='utf-8')
top=dest/'top/scope_board_top.sv'
s=top.read_text(encoding='utf-8').replace('module scope_board_top #','module scope_cpu_board_top #')
s=s.replace('UART_BAUD=115200','UART_BAUD=921600')
s=s.replace('scope_uart_endpoint #','scope_cpu_endpoint #')
# A distinct software/hardware build identity; never masquerade as shipped image.
s=s.replace("32'hA4261027","32'hA4261028")
top.write_text(s,encoding='utf-8')
(root/'reports/source_snapshot.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(f'ISOLATED_SNAPSHOT_READY files={len(manifest)}')
clock=root/'integration/clock'
clock.mkdir(exist_ok=True)
for name in ('scope_clk_wiz.v','scope_clk_wiz_clk_wiz.v'):
    shutil.copy2(project/'FPGA/ip/scope_clk_wiz'/name,clock/name)
shutil.copy2(project/'FPGA/constraints/scope_board_25m.xdc',root/'integration/scope_board_25m.xdc')
shutil.copy2(project/'FPGA/scripts/ensure_scope_fft_ip.tcl',root/'scripts/ensure_scope_fft_ip.tcl')
