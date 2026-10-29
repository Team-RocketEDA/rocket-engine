`timescale 1ns / 1ps
// VALIDATE-M verdict bench for the vendored sdm_rx wrapper.
//
// The vendored cocotb TB (rtl/tb/test_sdm_rx.py, 5/5 green) needs
// cocotb + cocotbext-axi + numpy, which the engine HdlSimAdapter does
// not run. This bench reproduces its documented checks in plain
// Verilog without cocotb: ID/VERSION/OSR defaults, DC full scale
// OSR^3, alternating-pattern STATUS/W1C, and the committed PEX
// bitstream (pex_bits_clean.txt, the one-way seam handoff) ones
// density + counts. Bit-exact golden-model compares run in the
// Python test by parsing the PEX_DATA_* displays below.
module sdm_rx_bench;
   reg aclk = 1'b0;
   reg aresetn = 1'b0;
   reg bit_i = 1'b0;
   reg bit_ce = 1'b0;

   reg [7:0]  s_axil_awaddr = 8'd0;
   reg        s_axil_awvalid = 1'b0;
   wire       s_axil_awready;
   reg [31:0] s_axil_wdata = 32'd0;
   reg [3:0]  s_axil_wstrb = 4'hF;
   reg        s_axil_wvalid = 1'b0;
   wire       s_axil_wready;
   wire [1:0] s_axil_bresp;
   wire       s_axil_bvalid;
   reg        s_axil_bready = 1'b0;
   reg [7:0]  s_axil_araddr = 8'd0;
   reg        s_axil_arvalid = 1'b0;
   wire       s_axil_arready;
   wire [31:0] s_axil_rdata;
   wire [1:0] s_axil_rresp;
   wire       s_axil_rvalid;
   reg        s_axil_rready = 1'b0;

   sdm_rx dut (
      .aclk(aclk),
      .aresetn(aresetn),
      .bit_i(bit_i),
      .bit_ce(bit_ce),
      .s_axil_awaddr(s_axil_awaddr),
      .s_axil_awvalid(s_axil_awvalid),
      .s_axil_awready(s_axil_awready),
      .s_axil_wdata(s_axil_wdata),
      .s_axil_wstrb(s_axil_wstrb),
      .s_axil_wvalid(s_axil_wvalid),
      .s_axil_wready(s_axil_wready),
      .s_axil_bresp(s_axil_bresp),
      .s_axil_bvalid(s_axil_bvalid),
      .s_axil_bready(s_axil_bready),
      .s_axil_araddr(s_axil_araddr),
      .s_axil_arvalid(s_axil_arvalid),
      .s_axil_arready(s_axil_arready),
      .s_axil_rdata(s_axil_rdata),
      .s_axil_rresp(s_axil_rresp),
      .s_axil_rvalid(s_axil_rvalid),
      .s_axil_rready(s_axil_rready)
   );

   always #10 aclk = ~aclk;

   reg mem [0:2047];
   integer i;
   reg [31:0] val;
   reg [31:0] total;
   reg [31:0] ones;
   reg signed [31:0] dfast;
   reg signed [31:0] dprec;

   task axil_write(input [7:0] addr, input [31:0] data);
      integer guard;
      begin
         s_axil_awaddr = addr;
         s_axil_wdata = data;
         s_axil_wstrb = 4'hF;
         s_axil_awvalid = 1'b1;
         s_axil_wvalid = 1'b1;
         guard = 0;
         while (!(s_axil_awready && s_axil_wready)) begin
            @(posedge aclk);
            #1;
            guard = guard + 1;
            if (guard > 100) begin
               $fatal(1, "AXI write handshake timeout");
            end
         end
         @(posedge aclk);
         #1;
         s_axil_awvalid = 1'b0;
         s_axil_wvalid = 1'b0;
         guard = 0;
         while (!s_axil_bvalid) begin
            @(posedge aclk);
            #1;
            guard = guard + 1;
            if (guard > 100) begin
               $fatal(1, "AXI write response timeout");
            end
         end
         s_axil_bready = 1'b1;
         @(posedge aclk);
         #1;
         s_axil_bready = 1'b0;
      end
   endtask

   task axil_read(input [7:0] addr, output [31:0] data);
      integer guard;
      begin
         s_axil_araddr = addr;
         s_axil_arvalid = 1'b1;
         guard = 0;
         while (!s_axil_arready) begin
            @(posedge aclk);
            #1;
            guard = guard + 1;
            if (guard > 100) begin
               $fatal(1, "AXI read handshake timeout");
            end
         end
         @(posedge aclk);
         #1;
         s_axil_arvalid = 1'b0;
         guard = 0;
         while (!s_axil_rvalid) begin
            @(posedge aclk);
            #1;
            guard = guard + 1;
            if (guard > 100) begin
               $fatal(1, "AXI read response timeout");
            end
         end
         data = s_axil_rdata;
         s_axil_rready = 1'b1;
         @(posedge aclk);
         #1;
         s_axil_rready = 1'b0;
      end
   endtask

   initial begin
      #100;
      aresetn = 1'b1;
      @(posedge aclk);
      @(posedge aclk);

      axil_read(8'h00, val);
      if (val !== 32'h53444D31) begin
         $fatal(1, "ID mismatch");
      end
      $display("SDM_RX_ID %08X", val);
      axil_read(8'h04, val);
      if (val !== 32'h00000100) begin
         $fatal(1, "VERSION mismatch");
      end
      $display("SDM_RX_VERSION %04X", val[15:0]);
      axil_read(8'h0C, val);
      if (val[15:0] !== 16'd25) begin
         $fatal(1, "OSR_FAST default mismatch");
      end
      axil_read(8'h10, total);
      if (total[15:0] !== 16'd250) begin
         $fatal(1, "OSR_PREC default mismatch");
      end
      $display("SDM_RX_OSR %0d %0d", val[15:0], total[15:0]);

      axil_write(8'h08, 32'h3);
      @(posedge aclk);
      @(posedge aclk);
      for (i = 0; i < 200; i = i + 1) begin
         bit_i = 1'b1;
         bit_ce = 1'b1;
         @(posedge aclk);
         #1;
      end
      bit_ce = 1'b0;
      @(posedge aclk);
      #1;
      axil_read(8'h18, val);
      dfast = $signed(val);
      if (dfast !== 32'sd15625) begin
         $display("MISMATCH DC_DATA_FAST=%0d want 15625", dfast);
         $fatal(1, "DC full scale is not OSR^3");
      end
      $display("DC_DATA_FAST %0d", dfast);
      axil_read(8'h28, total);
      axil_read(8'h2C, ones);
      if (total !== 32'd200 || ones !== 32'd200) begin
         $fatal(1, "DC bits total/ones mismatch");
      end
      axil_read(8'h20, val);
      if (val !== 32'd8) begin
         $fatal(1, "DC count_fast mismatch");
      end

      axil_write(8'h08, 32'h3);
      @(posedge aclk);
      @(posedge aclk);
      for (i = 0; i < 200; i = i + 1) begin
         if (i[0] == 1'b0)
            bit_i = 1'b1;
         else
            bit_i = 1'b0;
         bit_ce = 1'b1;
         @(posedge aclk);
         #1;
      end
      bit_ce = 1'b0;
      @(posedge aclk);
      #1;
      axil_read(8'h14, val);
      if (!(val[0])) begin
         $fatal(1, "STATUS fast-valid not set");
      end
      axil_write(8'h14, 32'h1);
      axil_read(8'h14, val);
      if (val[0]) begin
         $fatal(1, "STATUS W1C did not clear");
      end
      axil_read(8'h28, total);
      axil_read(8'h2C, ones);
      if (total !== 32'd200 || ones !== 32'd100) begin
         $display("MISMATCH ALT total=%0d ones=%0d", total, ones);
         $fatal(1, "ALT bits total/ones mismatch");
      end

      $readmemb("pex_bits_clean.txt", mem);
      axil_write(8'h08, 32'h3);
      @(posedge aclk);
      @(posedge aclk);
      for (i = 0; i < 2048; i = i + 1) begin
         bit_i = mem[i];
         bit_ce = 1'b1;
         @(posedge aclk);
         #1;
      end
      bit_ce = 1'b0;
      @(posedge aclk);
      #1;
      axil_read(8'h28, total);
      axil_read(8'h2C, ones);
      if (total !== 32'd2048 || ones !== 32'd1013) begin
         $display("MISMATCH PEX_BITS total=%0d ones=%0d", total, ones);
         $fatal(1, "PEX ones density mismatch");
      end
      $display("PEX_BITS %0d %0d", total, ones);
      axil_read(8'h20, val);
      if (val !== 32'd81) begin
         $fatal(1, "PEX count_fast mismatch");
      end
      axil_read(8'h24, val);
      if (val !== 32'd8) begin
         $fatal(1, "PEX count_prec mismatch");
      end
      axil_read(8'h18, val);
      dfast = $signed(val);
      $display("PEX_DATA_FAST %0d", dfast);
      axil_read(8'h1C, val);
      dprec = $signed(val);
      $display("PEX_DATA_PREC %0d", dprec);

      $display("SDM_RX_PASS");
      $finish;
   end
endmodule
