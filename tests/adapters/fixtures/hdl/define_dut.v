module define_dut (
    output wire [3:0] value
);
`ifdef PROBE_TEN
  assign value = 4'd10;
`else
  assign value = 4'd0;
`endif
endmodule
