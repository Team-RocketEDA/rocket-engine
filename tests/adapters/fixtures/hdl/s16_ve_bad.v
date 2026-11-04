module s16_ve_bad (input wire clk, output reg [3:0] q)
  always @(posedge clk) begin
    q <= q + 4'd1;
  end
endmodule
