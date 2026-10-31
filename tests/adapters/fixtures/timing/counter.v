// counter.v — TIMING-STA micro-RTL (mapped with real Yosys + sky130).
//
// 4-bit synchronous counter with enable and an overflow flag. The
// committed counter_mapped.v beside it is this file mapped through
// oss-cad-suite Yosys (`synth -top counter`, dfflibmap + abc with
// the ambient sky130_fd_sc_hd liberty), so the counter live tests
// run STA on genuine mapped cells, not hand-drawn instances.
`default_nettype none

module counter (
    input wire clk,
    input wire rst,
    input wire enable,
    output reg [3:0] count,
    output wire overflow
);

  assign overflow = &count;

  always @(posedge clk) begin
    if (rst) count <= 4'b0;
    else if (enable) count <= count + 1'b1;
  end

endmodule
