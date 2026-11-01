`default_nettype none
// SCAP v1, little endian. Header 128 bytes, interleaved B(14)/R(3) records,
// F(9) trailer with CRC32 of header+records and the two record counts.
// Interleaving is essential: blocking ROI until the last bucket would deadlock
// the existing single-pass reducer. Only one 14-byte record is buffered.
module capture_result_stream(
  input wire clk,rst,module_enable,start,
  output wire start_ready,
  input innovation_pkg::capture_result_meta_t cfg,
  input wire bucket_valid,
  output wire bucket_ready,
  input multires_pkg::envelope_bucket_t bucket,
  input wire roi_valid,
  output wire roi_ready,
  input multires_pkg::envelope_roi_t roi,
  input wire source_done,
  output wire out_valid,
  input wire out_ready,
  output logic [7:0] out_data,
  output logic done,error,cancelled,
  output logic [31:0] byte_count
);
  timeunit 1ns;timeprecision 1ps;
  import innovation_pkg::*;
  typedef enum logic [2:0] {IDLE,HEADER,SELECT_RECORD,RECORD,FOOTER} state_t;
  state_t state;
  capture_result_meta_t held;
  logic [6:0] position;
  logic [3:0] record_length;
  logic [111:0] record_data;
  logic [9:0] buckets_seen;
  logic [11:0] roi_seen;
  logic [31:0] crc;
  logic source_finished,prefer_roi;
  function automatic logic [31:0] crc_byte(input logic [31:0] c0,input logic [7:0] d);
    logic [31:0] c;begin c=c0^{24'd0,d};for(integer k=0;k<8;k++)c=(c>>1)^(c[0]?32'hedb88320:32'd0);return c;end
  endfunction
  function automatic logic [7:0] byte32(input logic [31:0] x,input logic [6:0] n);return 8'(x>>(32'(n)*32'd8));endfunction
  function automatic logic [7:0] byte64(input logic [63:0] x,input logic [6:0] n);return 8'(x>>(32'(n)*32'd8));endfunction
  function automatic logic [7:0] header_byte(input capture_result_meta_t h,input logic [6:0] p);
    case(p)
      0:return 8'h53;1:return 8'h43;2:return 8'h41;3:return 8'h50;4:return 8'd1;5:return 8'd0;6:return 8'd128;7:return 0;
      8,9,10,11:return byte32(h.result_id,p-7'd8);
      12,13,14,15:return byte32({14'd0,h.sample_count},p-7'd12);
      16,17,18,19:return byte32({14'd0,h.trigger_index},p-7'd16);
      20,21,22,23:return byte32({14'd0,h.trigger_index},p-7'd20);
      24,25,26,27:return byte32({14'd0,h.sample_count-h.trigger_index-18'd1},p-7'd24);
      28,29,30,31:return byte32(h.sample_rate,p-7'd28);
      32,33,34,35,36,37,38,39:return byte64(h.moments.first_timestamp,p-7'd32);
      40,41,42,43,44,45,46,47:return byte64(h.moments.first_timestamp+{46'd0,h.trigger_index},p-7'd40);
      48,49,50,51,52,53,54,55:return byte64(h.moments.last_timestamp,p-7'd48);
      56:return h.bucket_count[7:0];57:return {6'd0,h.bucket_count[9:8]};
      58:return h.roi_count[7:0];59:return {4'd0,h.roi_count[11:8]};
      60,61,62,63:return byte32({14'd0,h.roi_start},p-7'd60);
      64,65,66,67:return byte32(h.moments.raw_crc32,p-7'd64);
      68,69,70,71:return byte32({14'd0,h.moments.count},p-7'd68);
      72,73,74,75,76,77,78,79:return byte64(64'(h.moments.sum),p-7'd72);
      80,81,82,83,84,85,86,87:return byte64(h.moments.square_sum,p-7'd80);
      88:return h.moments.minimum[7:0];89:return {{3{h.moments.minimum[12]}},h.moments.minimum[12:8]};
      90:return h.moments.maximum[7:0];91:return {{3{h.moments.maximum[12]}},h.moments.maximum[12:8]};
      92,93,94,95:return byte32({14'd0,h.moments.otr_count},p-7'd92);
      96:return 8'd1; // exact whole-frame moments valid; no fabricated period.
      default:return 8'd0;
    endcase
  endfunction
  assign start_ready=module_enable && !rst && state==IDLE;
  assign out_valid=module_enable && !rst && (state==HEADER || state==RECORD || state==FOOTER);
  assign roi_ready=module_enable && !rst && state==SELECT_RECORD && roi_seen<held.roi_count && (!bucket_valid || prefer_roi);
  assign bucket_ready=module_enable && !rst && state==SELECT_RECORD && buckets_seen<held.bucket_count && (!roi_valid || !prefer_roi);
  always_comb begin
    out_data=0;
    if(state==HEADER)out_data=header_byte(held,position);
    if(state==RECORD)out_data=8'(record_data>>(32'(position)*32'd8));
    if(state==FOOTER)case(position)
      0:out_data=8'h46;
      1,2,3,4:out_data=byte32(~crc,position-7'd1);
      5:out_data=buckets_seen[7:0];6:out_data={6'd0,buckets_seen[9:8]};
      7:out_data=roi_seen[7:0];8:out_data={4'd0,roi_seen[11:8]};
      default:out_data=0;
    endcase
  end
  always_ff @(posedge clk)begin
    if(rst)begin
      state<=IDLE;held<='0;position<=0;record_length<=0;record_data<=0;buckets_seen<=0;roi_seen<=0;
      crc<=32'hffffffff;source_finished<=0;prefer_roi<=0;done<=0;error<=0;cancelled<=0;byte_count<=0;
    end else begin
      done<=0;error<=0;cancelled<=0;
      if(!module_enable)begin cancelled<=state!=IDLE;state<=IDLE;source_finished<=0;end
      else begin
        if(state!=IDLE && source_done)source_finished<=1;
        if(out_valid && out_ready)begin
          byte_count<=byte_count+32'd1;
          if(state!=FOOTER)crc<=crc_byte(crc,out_data);
          position<=position+7'd1;
          if(state==HEADER && position==7'd127)begin position<=0;state<=SELECT_RECORD;end
          if(state==RECORD && position=={3'd0,record_length}-7'd1)begin position<=0;state<=SELECT_RECORD;end
          if(state==FOOTER && position==7'd8)begin done<=1;state<=IDLE;end
        end
        if(state==IDLE && start)begin
          if(cfg.sample_count==0 || cfg.sample_count>18'd16384 || cfg.trigger_index>=cfg.sample_count || cfg.moments.count!=cfg.sample_count ||
            cfg.bucket_count==0 || cfg.bucket_count>10'd800 || {8'd0,cfg.bucket_count}>cfg.sample_count || cfg.sample_rate==0 ||
            {6'd0,cfg.roi_count}>cfg.sample_count || {1'b0,cfg.roi_start}+{7'd0,cfg.roi_count}>{1'b0,cfg.sample_count} ||
            cfg.moments.last_timestamp!=cfg.moments.first_timestamp+{46'd0,cfg.sample_count}-64'd1)error<=1;
          else begin held<=cfg;state<=HEADER;position<=0;buckets_seen<=0;roi_seen<=0;crc<=32'hffffffff;source_finished<=0;prefer_roi<=0;byte_count<=0;end
        end
        if(state==SELECT_RECORD)begin
          if(bucket_valid && bucket_ready)begin
            record_data<={7'd0,bucket.otr,6'd0,bucket.maximum_index,6'd0,bucket.minimum_index,
              {3{bucket.maximum[12]}},bucket.maximum,{3{bucket.minimum[12]}},bucket.minimum,6'd0,bucket.bucket_index,8'h42};
            record_length<=4'd14;position<=0;state<=RECORD;buckets_seen<=buckets_seen+10'd1;prefer_roi<=1;
          end else if(roi_valid && roi_ready)begin
            record_data<={88'd0,roi.raw_word,8'h52};record_length<=4'd3;position<=0;state<=RECORD;roi_seen<=roi_seen+12'd1;prefer_roi<=0;
          end else if(buckets_seen==held.bucket_count && roi_seen==held.roi_count && source_finished)begin position<=0;state<=FOOTER;end
        end
      end
    end
  end
  // translate_off
  always @(posedge clk)if(!rst && module_enable)begin
    if(bucket_valid && bucket_ready)assert(bucket.bucket_index==buckets_seen && bucket.minimum_index>=bucket.first_index && bucket.minimum_index<=bucket.last_index &&
      bucket.maximum_index>=bucket.first_index && bucket.maximum_index<=bucket.last_index && bucket.last_index<held.sample_count && bucket.minimum<=bucket.maximum)
      else $fatal(1,"INNOVATION_BUCKET_RECORD");
    if(roi_valid && roi_ready)assert(roi.roi_index==roi_seen && roi.frame_index==held.roi_start+{6'd0,roi_seen} &&
      roi.timestamp==held.moments.first_timestamp+{46'd0,roi.frame_index} && roi.raw_word[14:12]==0)
      else $fatal(1,"INNOVATION_ROI_RECORD");
  end
  // translate_on
endmodule
`default_nettype wire
