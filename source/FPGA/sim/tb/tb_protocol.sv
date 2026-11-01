`default_nettype none
// Codec unit only. Python checks every offered header, payload and wire byte.
module tb_protocol;
  timeunit 1ns;timeprecision 1ps;
  import protocol_pkg::*;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,iv=0,ready=0;logic [7:0] data=0;
  wire ir,hv,hr,pv,pr,ov,done;wire [7:0] payload,wire_byte;
  frame_header_t header;parser_errors_t errors;wire [31:0] good;
  frame_rx #(.TIMEOUT_CYCLES(100)) receiver(.clk(clk),.rst(rst),.in_valid(iv),.in_data(data),.in_ready(ir),
    .header_valid(hv),.header_ready(hr),.header(header),.payload_valid(pv),.payload_ready(pr),.payload_data(payload),.errors(errors),.good_frames(good));
  frame_tx transmitter(.clk(clk),.rst(rst),.header_valid(hv),.header_ready(hr),.header(header),
    .payload_valid(pv),.payload_ready(pr),.payload_data(payload),.out_valid(ov),.out_ready(ready),.out_data(wire_byte),.done(done));
  byte unsigned expected[0:2097151],accepted[0:2097151];
  int seed=20261020,output_count=0,payload_count=0,header_count=0,expected_size,accepted_size,frames,ec,el,ev,et,bulk;
  int fd,hd,meta,trace,rc,op,arg;logic [31:0] rng;
  logic stalled=0;logic [7:0] held;
  string vectors,traces;
  always @(negedge clk)begin
    if(rst)ready=0;
    else begin rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};ready=rng[2:0]!=3'd0;end
  end
  always @(posedge clk)if(!rst)begin
    int k,s,n;logic [63:0] ts;logic [31:0] rate,ti;logic [15:0] flags;
    if(stalled)assert(ov && wire_byte===held)else $fatal(1,"PROTOCOL_STABILITY");
    stalled=ov && !ready;held=wire_byte;
    if(hv && hr)begin
      rc=$fscanf(hd,"%h %h %h %h %h %h %h",k,s,n,ts,rate,ti,flags);
      assert(rc==7 && header.kind==8'(k) && header.seq==16'(s) && header.length==16'(n) && header.timestamp==ts &&
        header.sample_rate==rate && header.trigger_index==ti && header.flags==flags)else $fatal(1,"PROTOCOL_HEADER_SCOREBOARD index=%0d",header_count);
      header_count++;
    end
    if(pv && pr)begin
      assert(payload_count<accepted_size && payload===accepted[payload_count])else $fatal(1,"PROTOCOL_PAYLOAD_SCOREBOARD index=%0d",payload_count);
      payload_count++;
    end
    if(ov && ready)begin
      assert(output_count<expected_size && wire_byte===expected[output_count])else $fatal(1,"PROTOCOL_WIRE_SCOREBOARD index=%0d",output_count);
      $fwrite(trace,"%02x\n",wire_byte);output_count++;
    end
  end
  initial begin
    assert($value$plusargs("VECTOR_DIR=%s",vectors) && $value$plusargs("TRACE_DIR=%s",traces))else $fatal(1,"PROTOCOL_PATHS");
    if($value$plusargs("SEED=%d",seed))begin end
    rng=32'(seed)|32'd1;
    meta=$fopen({vectors,"/counts.txt"},"r");assert(meta)else $fatal(1,"PROTOCOL_COUNTS");
    rc=$fscanf(meta,"%d %d %d %d %d %d %d %d",expected_size,accepted_size,frames,ec,el,ev,et,bulk);
    assert(rc==8 && bulk>=1048576)else $fatal(1,"PROTOCOL_BULK");$fclose(meta);
    $readmemh({vectors,"/expected.hex"},expected,0,expected_size-1);
    $readmemh({vectors,"/accepted.hex"},accepted,0,accepted_size-1);
    if($test$plusargs("INJECT_PROTOCOL_FAULT"))expected[0]^=8'h01;
    fd=$fopen({vectors,"/actions.txt"},"r");hd=$fopen({vectors,"/headers.txt"},"r");trace=$fopen({traces,"/protocol.hex"},"w");
    assert(fd && hd && trace)else $fatal(1,"PROTOCOL_FILES");
    repeat(8)@(negedge clk);rst=0;
    while(!$feof(fd))begin
      rc=$fscanf(fd,"%d %d",op,arg);if(rc!=2)break;
      case(op)
        0:begin iv=1;data=8'(arg);do @(posedge clk);while(!ir);@(negedge clk);iv=0;end
        1:repeat(arg)@(negedge clk);
        2:begin wait(output_count>=arg);@(negedge clk);end
        8:begin
          repeat(150)@(negedge clk);
          assert(output_count==expected_size && payload_count==accepted_size && header_count==frames && good==32'(frames) &&
            errors.crc==32'(ec) && errors.length==32'(el) && errors.version==32'(ev) && errors.timeout==32'(et))else
            $fatal(1,"PROTOCOL_FINAL_COUNTS bytes=%0d frames=%0d errors=%h",output_count,header_count,errors);
          $fclose(fd);$fclose(hd);$fclose(trace);
          $display("TEST_PASS tb_protocol seed=%0d bulk=%0d frames=%0d errors=0",seed,bulk,frames);$finish;
        end
        default:$fatal(1,"PROTOCOL_ACTION");
      endcase
    end
    $fatal(1,"PROTOCOL_MISSING_END");
  end
  initial begin #500ms;$fatal(1,"PROTOCOL_WATCHDOG");end
endmodule
`default_nettype wire
