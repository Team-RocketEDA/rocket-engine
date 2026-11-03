`default_nettype none
// Committed stub: the vendored servant_tb.v needs vlog_tb_utils
// (a FuseSoC-side dependency that FIXTURE-FETCH does not vendor).
// servant_tb.v instantiates it with no connections, so an empty
// module satisfies elaboration; this harness replaces that
// testbench outright.
module vlog_tb_utils;
endmodule

// SERV hello regression harness (SIM-SKY130). Mirrors the
// vendored bench/servant_tb.v wiring (width 1, 57600 baud,
// 62 ns clock) with two additions: a memfile parameter so tests
// stage the firmware hex, and a watchdog so a sim that never
// reaches the firmware HALT ($finish in servile_mux) fails via
// $fatal instead of hanging the engine.
module serv_harness;
   parameter memfile = "hello_uart.hex";
   parameter memsize = 8192;
   parameter watchdog_units = 200000000;

   reg wb_clk = 1'b0;
   reg wb_rst = 1'b1;
   wire q;

   always #31 wb_clk <= !wb_clk;
   initial #62 wb_rst <= 1'b0;

   vlog_tb_utils vtu();
   uart_decoder #(57600) uart_decoder (q);

   servant_sim
     #(.memfile  (memfile),
       .memsize  (memsize),
       .width    (1),
       .with_csr (1))
   dut
     (.wb_clk (wb_clk),
      .wb_rst (wb_rst),
      .pc_adr (),
      .pc_vld (),
      .q      (q));

   initial begin
      #watchdog_units;
      $fatal(1, "watchdog expired, firmware never halted");
   end
endmodule
