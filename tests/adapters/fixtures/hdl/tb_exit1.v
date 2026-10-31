`timescale 1ns / 1ps

module tb_exit1;
  reg clk = 0;
  reg rst_n = 0;
  wire [3:0] count;

  counter dut (.clk(clk), .rst_n(rst_n), .count(count));

  always #5 clk = ~clk;

  initial begin
    #12 rst_n = 1;
    #100;
    $display("TB_EXIT1 count=%0d", count);
    $finish(1);
  end
endmodule
