`timescale 1 ns / 1 ps
// VALIDATE-D verdict monitor for the vendored picorv32 test_ez
// bench. The vendor bench (testbench_ez.v) runs a fixed 1000 cycles
// and $finishes with no pass/fail of its own, so behavioral breaks
// would be silent: this monitor samples the finished state just
// before the bench $finish (11000 ns) and $fatal fires on anything
// but a clean run — trap raised, or the ez loop counter (memory at
// 0x3fc, index 255; good runs reach 44) below 10. Silent on good
// runs: vendor traffic and finish are byte-identical with or
// without it. Comparisons use !== so X states fail, never pass.
module picorv32_monitor;
   initial begin
      #10500;
      if (testbench.trap !== 1'b0) begin
         $fatal(1, "picorv32 trap raised during test_ez");
      end
      if ((testbench.memory[255] >= 32'd10) !== 1'b1) begin
         $fatal(1, "picorv32 test_ez made no progress (counter below 10)");
      end
   end
endmodule
