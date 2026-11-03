`timescale 1ns / 1ps

module tb_error;
  reg clk = 0;
  reg rst_n = 0;
  wire [3:0] count;

  counter dut (.clk(clk), .rst_n(rst_n), .count(count));

  always #5 clk = ~clk;

  initial begin
    #12 rst_n = 1;
    #100;
    if (count !== 4'd7) begin
      $display("MISMATCH count=%0d want 7", count);
      $error("counter sequence wrong (non-fatal)");
    end
    $display("TB_DONE count=%0d", count);
    $finish;
  end
endmodule
