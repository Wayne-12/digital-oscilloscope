`default_nettype none
// PHY only: no packet parser, command engine or acquisition backend.
module tb_uart_phy;
  timeunit 1ns;timeprecision 1ps;
  localparam realtime BIT_NS=1000000000.0/115200.0;
  logic clk=0;always #5ns clk=~clk;
  logic rst=1,rx=1,iv=0;
  logic [7:0] data=0;
  wire ready,tx,done,busy,ov;
  wire [7:0] received;
  wire [31:0] framing,false_starts;
  uart_tx transmitter(.clk(clk),.rst(rst),.in_valid(iv),.in_data(data),.in_ready(ready),.tx(tx),.done(done),.busy(busy));
  uart_rx receiver(.clk(clk),.rst(rst),.rx(rx),.out_valid(ov),.out_data(received),.framing_errors(framing),.false_starts(false_starts));
  logic [7:0] expected[0:63];
  int seed=20261020,rx_count=0,tx_count=0,cycles=0,start_cycle=0,timing_checks=0;
  logic [31:0] rng;
  logic tx_finished=0,rx_finished=0,previous_busy=0;
  logic [3:0] previous_index=0;
  always @(posedge clk)begin
    cycles++;
    if(!rst && ov)begin
      assert(rx_count<64 && received===expected[rx_count])else $fatal(1,"UART_PHY_RX_SCOREBOARD index=%0d",rx_count);
      rx_count++;
    end
    #1ps;
    if(!rst)begin
      if(busy && !previous_busy)start_cycle=cycles;
      else if(previous_busy && (!busy || transmitter.index!=previous_index))begin
        int n;n=busy?int'(transmitter.index):10;
        assert(cycles-start_cycle==(n*100000000+115199)/115200)else $fatal(1,"UART_PHY_DIVIDER bit=%0d",n);
        timing_checks++;
      end
    end
    previous_busy=busy;previous_index=transmitter.index;
  end
  initial begin:decode
    logic [7:0] word;
    wait(!rst);
    forever begin
      @(negedge tx);#(BIT_NS/2.0);assert(tx===0)else $fatal(1,"UART_PHY_START");
      for(int b=0;b<8;b++)begin #(BIT_NS);word[b]=tx;end
      #(BIT_NS);assert(tx===1)else $fatal(1,"UART_PHY_STOP");
      assert(tx_count<64 && word===expected[tx_count])else $fatal(1,"UART_PHY_TX_SCOREBOARD index=%0d",tx_count);
      tx_count++;
    end
  end
  task automatic send(input logic [7:0] word,input realtime period,input bit good_stop=1);
    rx=0;#(period);
    for(int b=0;b<8;b++)begin rx=word[b];#(period);end
    rx=good_stop;#(period);rx=1;
  endtask
  initial begin
    if($value$plusargs("SEED=%d",seed))begin end
    rng=32'(seed)|32'd1;
    for(int i=0;i<64;i++)begin rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};expected[i]=rng[7:0];end
    repeat(8)@(negedge clk);rst=0;
    fork
      begin
        for(int i=0;i<64;i++)begin
          @(negedge clk);while(!ready)@(negedge clk);
          iv=1;data=expected[i];@(negedge clk);iv=0;
        end
        wait(done);tx_finished=1;
      end
      begin
        #(2*BIT_NS);rx=0;#2000ns;rx=1;#(2*BIT_NS);
        assert(false_starts==1)else $fatal(1,"UART_PHY_FALSE_START");
        send(8'he1,BIT_NS,0);rx=0;#(2*BIT_NS);rx=1;#(2*BIT_NS);
        for(int i=0;i<64;i++)send(expected[i],i<22?BIT_NS:(i<44?BIT_NS*1.02:BIT_NS*0.98));
        #(2*BIT_NS);rx_finished=1;
      end
    join
    wait(tx_count==64 && rx_count==64);
    assert(tx_finished && rx_finished && framing==1 && false_starts==1 && timing_checks==640)else $fatal(1,"UART_PHY_COUNTS");
    $display("TEST_PASS tb_uart_phy seed=%0d tx=64 rx=64 timing_checks=640 errors=0",seed);$finish;
  end
  initial begin #20ms;$fatal(1,"UART_PHY_WATCHDOG");end
endmodule
`default_nettype wire
