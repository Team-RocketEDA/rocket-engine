`timescale 1ns / 1ps

// Writes outside the workdir: proves sandbox confinement (or its absence).
module tb_escape;
  integer f;
  initial begin
    f = $fopen("/tmp/rocketeda_escape_probe", "w");
    $fwrite(f, "pwned");
    $fclose(f);
    $display("TB_ESCAPE done");
    $finish;
  end
endmodule
