`timescale 1ns / 1ps

// Hangs forever: proves the adapter kills runaway sims (timeout).
module tb_hang;
  initial begin
    while (1) #1;
  end
endmodule
