`default_nettype none
module tb_multires;
  timeunit 1ns;timeprecision 1ps;
  import scope_pkg::*;import multires_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst=1,module_enable=0,start=0;
  wire logic start_ready,busy,metadata_valid,sample_request,bucket_valid,roi_valid,done,config_error,cancelled;
  frame_index_t cfg_sample_count=0,cfg_trigger_index=0;
  logic [9:0] cfg_bucket_count=800;
  logic [11:0] cfg_roi_count=1024;
  logic [63:0] cfg_first_timestamp=0;
  logic [31:0] cfg_sample_rate=25000000;
  wire envelope_metadata_t metadata;
  wire envelope_bucket_t bucket;
  wire envelope_roi_t roi;
  wire frame_index_t sample_index,consumed_samples;
  logic metadata_ready=0,bucket_ready=0,roi_ready=0,sample_ready=0,sample_valid=0;
  logic [15:0] sample_word=0;
  multires_envelope dut(.*);
  logic [15:0] memory[0:16383];
  int unsigned sample_hits[0:16383],bucket_hits[0:16383];
  int unsigned seed=20261020,random_state,cycles=0,header_stalls=0,bucket_stalls=0,roi_stalls=0,source_stalls=0;
  bit pause_header=0,pause_bucket=0,pause_roi=0,pause_source=0,pending=0,checking=0;
  int delay_override=-1;
  int unsigned delay_left=0,held_index=0,response_index=0;
  int unsigned n,b,effective,roi_first,roi_count,roi_trigger,trigger,rate,cid=0;
  logic [63:0] first_ts;
  int unsigned reads=0,responses=0,buckets=0,rois=0,headers=0,summed=0,cases=0;
  int unsigned total_samples=0,total_buckets=0,total_roi=0,errors_seen=0,cancels_seen=0;
  int fd,bf,rf,bt,rt,ct,rc;
  string vectors=".",expected=".",traces=".";
  bit held_metadata=0,held_bucket=0,held_roi=0,held_request=0;
  envelope_metadata_t previous_metadata;
  envelope_bucket_t previous_bucket;
  envelope_roi_t previous_roi;
  frame_index_t previous_index;
  always @(negedge clk)begin
    random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
    metadata_ready=!pause_header && random_state[2:0]!=0;
    bucket_ready=!pause_bucket && random_state[5:3]!=0;
    roi_ready=!pause_roi && random_state[8:6]!=0;
    sample_ready=!rst && !pending && !sample_valid && !pause_source && random_state[11:9]!=0;
  end
  // Independent variable-latency backend; response cannot be backpressured.
  always @(posedge clk)begin
    sample_valid<=0;
    if(rst)begin pending=0;delay_left=0;sample_word<=0;response_index<=0;end
    else begin
      if(pending)begin
        if(delay_left==0)begin sample_valid<=1;sample_word<=memory[held_index];response_index<=held_index;pending=0;end
        else delay_left--;
      end
      if(sample_request && sample_ready)begin
        assert(!pending && sample_index<18'd16384)else $fatal(1,"MULTIRES_TEST_MEMORY_RANGE");
        held_index=32'(sample_index);pending=1;delay_left=delay_override<0?32'(random_state[14:12]):32'(delay_override);
      end
    end
  end
  always @(posedge clk)begin:scoreboard
    int ei,lo,hi,count,mn,mx,mi,ma,otr,ri,fi,rs;
    logic [15:0] rw;logic [63:0] ts;
    int unsigned gb,gs,ge;
    cycles++;
    if(!rst && config_error)errors_seen++;
    if(!rst && cancelled)cancels_seen++;
    if(rst || !module_enable)begin held_metadata=0;held_bucket=0;held_roi=0;held_request=0;end
    else begin
      if(held_metadata)assert(metadata_valid && metadata===previous_metadata)else $fatal(1,"MULTIRES_METADATA_STABILITY");
      if(held_bucket)assert(bucket_valid && bucket===previous_bucket)else $fatal(1,"MULTIRES_BUCKET_STABILITY");
      if(held_roi)assert(roi_valid && roi===previous_roi)else $fatal(1,"MULTIRES_ROI_STABILITY");
      if(held_request)assert(sample_request && sample_index===previous_index)else $fatal(1,"MULTIRES_REQUEST_STABILITY");
      held_metadata=metadata_valid && !metadata_ready;previous_metadata=metadata;
      held_bucket=bucket_valid && !bucket_ready;previous_bucket=bucket;
      held_roi=roi_valid && !roi_ready;previous_roi=roi;
      held_request=sample_request && !sample_ready;previous_index=sample_index;
      if(held_metadata)header_stalls++;if(held_bucket)bucket_stalls++;if(held_roi)roi_stalls++;if(held_request)source_stalls++;
      if(checking)begin
        if(metadata_valid && metadata_ready)begin
          assert(headers==0 && metadata.sample_count==18'(n) && metadata.trigger_index==18'(trigger) &&
            metadata.requested_buckets==10'(b) && metadata.effective_buckets==10'(effective) && metadata.roi_start==18'(roi_first) &&
            metadata.roi_count==12'(roi_count) && metadata.roi_trigger_index==12'(roi_trigger) && metadata.first_timestamp==first_ts && metadata.sample_rate==32'(rate))
            else $fatal(1,"MULTIRES_HEADER_SCOREBOARD case=%0d",cid);
          headers++;
        end
        if(sample_request && sample_ready)begin
          assert(headers==1 && sample_index==18'(reads) && reads<n)else $fatal(1,"MULTIRES_REQUEST_SCOREBOARD case=%0d index=%0d expected=%0d",cid,sample_index,reads);
          reads++;
        end
        if(sample_valid && dut.state==4'd5)begin
          assert(response_index==responses && responses<n && sample_hits[responses]==0)else $fatal(1,"MULTIRES_SAMPLE_ONCE_SCOREBOARD case=%0d",cid);
          // Independent floor boundaries, without using RTL remainder arithmetic.
          gb=32'(dut.bucket_number);gs=gb*n/effective;ge=(gb+1)*n/effective;
          assert(responses>=gs && responses<ge && dut.acc_count==18'(responses-gs))else $fatal(1,"MULTIRES_SAMPLE_OWNER_SCOREBOARD case=%0d sample=%0d bucket=%0d",cid,responses,gb);
          sample_hits[responses]++;responses++;
        end
        if(bucket_valid && bucket_ready)begin
          rc=$fscanf(bf,"%d %d %d %d %d %d %d %d %d",ei,lo,hi,count,mn,mx,mi,ma,otr);
          assert(rc==9 && bucket.bucket_index==10'(ei) && bucket.first_index==18'(lo) && bucket.last_index==18'(hi) && bucket.sample_count==18'(count) &&
            bucket.minimum===13'(mn) && bucket.maximum===13'(mx) && bucket.minimum_index==18'(mi) && bucket.maximum_index==18'(ma) && bucket.otr==1'(otr))
            else $fatal(1,"MULTIRES_BUCKET_SCOREBOARD case=%0d bucket=%0d",cid,buckets);
          assert(ei==int'(buckets) && lo>=0 && hi<int'(n))else $fatal(1,"MULTIRES_BUCKET_RANGE_SCOREBOARD");
          for(int j=lo;j<=hi;j++)bucket_hits[j]++;
          summed+=count;buckets++;
          $fwrite(bt,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cid,ei,lo,hi,count,mn,mx,mi,ma,otr);
        end
        if(roi_valid && roi_ready)begin
          rc=$fscanf(rf,"%d %d %h %d %h",ri,fi,rw,rs,ts);
          assert(rc==5 && roi.roi_index==12'(ri) && roi.frame_index==18'(fi) && roi.raw_word===rw && roi.signed_sample===13'(rs) && roi.timestamp==ts)
            else $fatal(1,"MULTIRES_ROI_SCOREBOARD case=%0d point=%0d",cid,rois);
          assert(fi==int'(roi_first+rois) && ri==int'(rois) && roi.raw_word===memory[fi])else $fatal(1,"MULTIRES_ROI_ORIGINAL_INDEX_ASSERT");
          $fwrite(rt,"%0d,%0d,%0d,%04x,%0d,%016x\n",cid,ri,fi,rw,rs,ts);rois++;
        end
      end
    end
  end
  task automatic launch(input int samples,input int bucket_count_arg,input int requested_roi,input int tr);
    wait(start_ready);@(negedge clk);cfg_sample_count=18'(samples);cfg_bucket_count=10'(bucket_count_arg);cfg_roi_count=12'(requested_roi);cfg_trigger_index=18'(tr);start=1;
    @(negedge clk);start=0;
  endtask
  task automatic recovery;
    pause_header=0;pause_bucket=0;pause_roi=0;pause_source=0;delay_override=-1;
    launch(7,800,1024,3);wait(done);@(negedge clk);
    assert(consumed_samples==7 && metadata.effective_buckets==7 && metadata.roi_count==7)else $fatal(1,"MULTIRES_RECOVERY_ASSERT");
  endtask
  task automatic control_tests;
    int before_errors,before_cancels,target;bit reset_case;
    // Bad counts must be rejected before any memory access or division.
    for(int k=0;k<8;k++)begin
      before_errors=errors_seen;
      case(k)
        0:launch(0,800,1024,0);1:launch(16385,800,1024,0);2:launch(262143,800,1024,0);
        3:launch(10,0,1024,0);4:launch(10,801,1024,0);5:launch(10,800,511,0);
        6:launch(10,800,2049,0);7:launch(10,800,1024,10);
      endcase
      repeat(4)@(negedge clk);
      assert(errors_seen==before_errors+1 && !busy && !metadata_valid && !sample_request)else $fatal(1,"MULTIRES_CONFIG_REJECTION_ASSERT case=%0d",k);
    end
    recovery();
    // Cancel and coordinated reset at each functional phase, including both
    // independently blocked sinks. Old in-flight reads must drain on cancel.
    for(int mode=0;mode<2;mode++)for(int k=1;k<=7;k++)begin
      reset_case=mode==1;target=k==7?6:k;
      pause_header=target==3;pause_source=target==4;pause_bucket=k==6;pause_roi=k==7;delay_override=20;
      before_cancels=cancels_seen;
      launch(1600,800,1024,800);
      if(k==6)wait(dut.state==6 && bucket_valid);
      else if(k==7)wait(dut.state==6 && roi_valid);
      else wait(dut.state==target);
      #0.001;
      if(reset_case)rst=1;else module_enable=0;
      repeat(3)@(negedge clk);
      assert(!bucket_valid && !roi_valid && !metadata_valid && !sample_request)else $fatal(1,"MULTIRES_ABORT_OUTPUT_ASSERT phase=%0d",k);
      if(!reset_case && k==5)assert(busy && !start_ready)else $fatal(1,"MULTIRES_INFLIGHT_DRAIN_ASSERT");
      rst=0;module_enable=1;
      wait(start_ready);
      if(!reset_case)assert(cancels_seen==before_cancels+1)else $fatal(1,"MULTIRES_CANCEL_COUNT_ASSERT phase=%0d",k);
      recovery();
      $display("MULTIRES_CONTROL_POINT_PASS reset=%0d phase=%0d",mode,k);
    end
    $display("MULTIRES_CONTROL_PASS invalid=8 cancels=7 resets=7 recoveries=15 errors=0");
  endtask
  initial begin:run
    int requested_roi;string path;
    if($value$plusargs("SEED=%d",seed))begin end
    if($value$plusargs("VECTOR_DIR=%s",vectors))begin end
    if($value$plusargs("EXPECTED_DIR=%s",expected))begin end
    if($value$plusargs("TRACE_DIR=%s",traces))begin end
    random_state=32'(seed)|32'd1;
    fd=$fopen({vectors,"/cases.txt"},"r");bt=$fopen({traces,"/multires_buckets.csv"},"w");rt=$fopen({traces,"/multires_roi.csv"},"w");ct=$fopen({traces,"/multires_cases.csv"},"w");
    assert(fd && bt && rt && ct)else $fatal(1,"MULTIRES_FILE_OPEN");
    $fwrite(bt,"case,bucket,first,last,count,min,max,min_index,max_index,otr\n");$fwrite(rt,"case,roi_index,frame_index,word,signed,timestamp\n");
    $fwrite(ct,"case,samples,buckets,roi_samples,read_count,response_count,coverage_once\n");
    repeat(12)@(negedge clk);rst=0;module_enable=1;
    while(!$feof(fd))begin
      rc=$fscanf(fd,"%d %d %d %d %d %h %d %d %d %d %d",cid,n,b,requested_roi,trigger,first_ts,rate,effective,roi_first,roi_count,roi_trigger);
      if(rc!=11)break;
      path=$sformatf("%s/frame_%0d.hex",vectors,cid);$readmemh(path,memory,0,n-1);
      bf=$fopen($sformatf("%s/buckets_%0d.txt",expected,cid),"r");rf=$fopen($sformatf("%s/roi_%0d.txt",expected,cid),"r");assert(bf && rf)else $fatal(1,"MULTIRES_GOLDEN_OPEN");
      for(int i=0;i<n;i++)begin sample_hits[i]=0;bucket_hits[i]=0;end
      reads=0;responses=0;buckets=0;rois=0;headers=0;summed=0;checking=1;
      cfg_first_timestamp=first_ts;cfg_sample_rate=32'(rate);
      pause_header=1;pause_bucket=1;pause_roi=roi_count!=0;
      fork
        begin wait(metadata_valid);repeat(7)@(negedge clk);pause_header=0;end
        begin wait(bucket_valid);repeat(11)@(negedge clk);pause_bucket=0;end
        begin if(roi_count!=0)begin wait(roi_valid);repeat(13)@(negedge clk);pause_roi=0;end end
      join_none
      launch(n,b,requested_roi,trigger);
      wait(headers==1);@(negedge clk);
      // Mutation while busy proves configuration is snapshotted at start.
      cfg_sample_count=1;cfg_bucket_count=1;cfg_roi_count=0;cfg_trigger_index=0;cfg_first_timestamp=0;cfg_sample_rate=0;
      wait(done);@(negedge clk);wait fork;
      assert(reads==n && responses==n && consumed_samples==18'(n) && buckets==effective && rois==roi_count && summed==n && !config_error)
        else $fatal(1,"MULTIRES_FINAL_COUNTS case=%0d reads=%0d responses=%0d buckets=%0d roi=%0d",cid,reads,responses,buckets,rois);
      for(int i=0;i<n;i++)assert(sample_hits[i]==1 && bucket_hits[i]==1)else $fatal(1,"MULTIRES_COVERAGE_ONCE case=%0d index=%0d",cid,i);
      $fwrite(ct,"%0d,%0d,%0d,%0d,%0d,%0d,1\n",cid,n,buckets,rois,reads,responses);
      total_samples+=n;total_buckets+=buckets;total_roi+=rois;cases++;checking=0;$fclose(bf);$fclose(rf);
      $display("MULTIRES_CASE_PASS id=%0d samples=%0d buckets=%0d roi=%0d",cid,n,buckets,rois);
    end
    control_tests();
    assert(header_stalls>0 && bucket_stalls>0 && roi_stalls>0 && source_stalls>0)else $fatal(1,"MULTIRES_STALL_COVERAGE_ASSERT");
    $fclose(fd);$fclose(bt);$fclose(rt);$fclose(ct);
    $display("TEST_PASS tb_multires seed=%0d cases=%0d samples=%0d buckets=%0d roi=%0d errors=0",seed,cases,total_samples,total_buckets,total_roi);$finish;
  end
  initial begin #2000000000;$fatal(1,"MULTIRES_WATCHDOG case=%0d state=%0d index=%0d",cid,dut.state,sample_index);end
endmodule
`default_nettype wire
