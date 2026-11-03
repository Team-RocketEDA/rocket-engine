// Latch + undriven micro-fixture: `en` gates a level-sensitive latch
// for `q`, and `undriven_w` is read with no driver. Yosys must
// report both as warnings ("Latch inferred", "has no driver") while
// the synth itself still exits 0.
module latch_undriven (
    input  wire       en,
    input  wire [3:0] d,
    output reg  [3:0] q,
    output wire [3:0] q_or
);
  wire undriven_w;
  always @(*) begin
    if (en)
      q = d;
  end
  assign q_or = q | {3'b0, undriven_w};
endmodule
