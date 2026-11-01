`default_nettype none
module tb_fft_wrapper;
  timeunit 1ns; timeprecision 1ps;
  logic clk=1'b0;
  always #5ns clk=~clk;
  logic rst, enable, start, inverse, in_valid, in_last, out_ready;
  wire start_ready, in_ready, out_valid, out_last, done, cancelled, error;
  logic signed [15:0] in_real, in_imag;
  wire signed [31:0] out_real, out_imag;
  wire [10:0] out_bin;
  fft_ip_wrapper dut(.clk(clk),.rst(rst),.module_enable(enable),.start(start),.start_ready(start_ready),
    .cfg_inverse(inverse),.in_valid(in_valid),.in_ready(in_ready),.in_real(in_real),.in_imag(in_imag),.in_last(in_last),
    .out_valid(out_valid),.out_ready(out_ready),.out_real(out_real),.out_imag(out_imag),.out_bin(out_bin),.out_last(out_last),
    .done(done),.cancelled(cancelled),.protocol_error(error));
  integer xr[0:1023],xi[0:1023],gr[0:1023],gi[0:1023];
  integer seed,unused,cf,f,cid,inv,idx,a,b,rc,sent,received,cycles,trace_file,comparisons;
  integer unsigned rng;
  string vectors,expected,path;
  function automatic integer unsigned random_next(input integer unsigned x);
    integer unsigned y; begin y=x^(x<<13);y=y^(y>>17);random_next=y^(y<<5);end
  endfunction
  initial begin
    #100ms; $fatal(1,"FFT_WRAPPER_WATCHDOG");
  end
  initial begin
    rst=1;enable=1;start=0;inverse=0;in_valid=0;in_last=0;in_real=0;in_imag=0;out_ready=0;
    seed=20261020;unused=$value$plusargs("SEED=%d",seed);rng=32'(seed);
    if(!$value$plusargs("VECTOR_DIR=%s",vectors)||!$value$plusargs("EXPECTED_DIR=%s",expected)) $fatal(1,"FFT_PATHS");
    trace_file=$fopen("fft_raw.csv","w");$fdisplay(trace_file,"case_id,bin,real,imag");comparisons=0;
    repeat(6) @(negedge clk);rst=0;
    cf=$fopen({vectors,"/raw_cases.txt"},"r");if(!cf)$fatal(1,"RAW_CASE_OPEN");
    while(!$feof(cf))begin
      rc=$fscanf(cf,"%d %d\n",cid,inv);if(rc!=2)$fatal(1,"RAW_CASE_FORMAT");
      path=$sformatf("%s/raw_%0d.txt",vectors,cid);f=$fopen(path,"r");if(!f)$fatal(1,"RAW_INPUT_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d %d\n",idx,a,b);assert(rc==3&&idx==n)else $fatal(1,"RAW_INPUT_FORMAT");xr[n]=a;xi[n]=b;end
      $fclose(f);path=$sformatf("%s/raw_%0d.txt",expected,cid);f=$fopen(path,"r");if(!f)$fatal(1,"RAW_GOLD_OPEN");
      for(integer n=0;n<1024;n++)begin rc=$fscanf(f,"%d %d %d\n",idx,a,b);assert(rc==3&&idx==n)else $fatal(1,"RAW_GOLD_FORMAT");gr[n]=a;gi[n]=b;end
      $fclose(f);
      while(!start_ready)@(negedge clk);
      inverse=1'(inv);start=1;@(negedge clk);start=0;sent=0;received=0;cycles=0;
      while(received<1024)begin
        rng=random_next(rng);out_ready=(rng[2:0]!=3'd0);
        // Once asserted, an input beat is held until accepted.
        if(!in_valid&&sent<1024&&rng[5:3]!=3'd0)begin in_valid=1;in_real=16'(xr[sent]);in_imag=16'(xi[sent]);in_last=(sent==1023);end
        @(posedge clk);
        if(in_valid&&in_ready)begin sent++;end
        if(out_valid&&out_ready)begin
          assert(out_bin==11'(received)&&out_last==(received==1023))else $fatal(1,"RAW_ORDER");
          assert(($signed(out_real)-gr[received]<=128)&&($signed(out_real)-gr[received]>=-128)&&
                 ($signed(out_imag)-gi[received]<=128)&&($signed(out_imag)-gi[received]>=-128))
            else $fatal(1,"RAW_DFT_MISMATCH case=%0d bin=%0d got=%0d,%0d gold=%0d,%0d",cid,received,out_real,out_imag,gr[received],gi[received]);
          $fdisplay(trace_file,"%0d,%0d,%0d,%0d",cid,received,out_real,out_imag);received++;comparisons++;
        end
        assert(!error)else $fatal(1,"RAW_PROTOCOL");
        // Remember acceptance before changing signals on the next falling edge.
        a=in_valid&&in_ready;
        @(negedge clk);if(a!=0)in_valid=0;
        cycles++;assert(cycles<100000)else $fatal(1,"RAW_CASE_TIMEOUT");
      end
      in_valid=0;out_ready=0;$display("FFT_RAW_CASE_PASS case=%0d inverse=%0d bins=1024",cid,inv);
    end
    $fclose(cf);$fclose(trace_file);
    $display("TEST_PASS tb_fft_wrapper seed=%0d cases=5 bins=%0d errors=0",seed,comparisons);$finish;
  end
endmodule
`default_nettype wire
