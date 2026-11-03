`timescale 1ns / 1ps

module tb_define;
  wire [3:0] value;

  define_dut dut (.value(value));

  initial begin
    #10;
    if (value !== 4'd10) begin
      $display("MISMATCH value=%0d want 10", value);
      $fatal(1, "define probe wrong");
    end
    $display("TB_DEFINE value=%0d", value);
    $finish;
  end
endmodule
