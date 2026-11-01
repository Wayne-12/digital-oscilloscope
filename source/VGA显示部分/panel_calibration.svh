// Generated from the external-reference DC profile in root 校正参数.json.
localparam integer CAL_LOW=1637,CAL_HIGH=2462;
function automatic signed [15:0] to_mv(input [11:0] raw,input calibrated);
 reg signed [47:0] q;
 begin
  q=calibrated ? $signed({1'b0,raw})*-48'sd157392+48'sd323275645 :
    $signed({1'b0,raw})*(-48'sd160039)+48'sd327680000;
  to_mv=q<0 ? -((-q+32768)>>>16) : ((q+32768)>>>16);
 end
endfunction
