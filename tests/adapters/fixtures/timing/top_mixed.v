// top_mixed.v — TIMING-STA M11 fixture: digital block + analog boundary.
//
// The digital block is serv_top, whose mapped netlist the live tests
// stage at run time (vendored SERV RTL through YosysSynthAdapter, so
// the cells under test are always genuine). This file only wraps it:
// every serv_top port (default parameters, no RISCV_FORMAL) is
// exposed 1:1 at the top boundary beside the analog stub.
//
// analog_boundary models the analog macro with NO timing arcs — the
// macro delivers no .lib here — so its pins are structurally
// unconstrained and must surface in check_setup evidence, never
// assumed. top_mixed.sdc constrains the digital boundary except for
// the deliberate gaps (rdata0_in, rdata1_in, wdata0_out,
// wdata1_out) plus the analog pins.
`default_nettype none

module analog_boundary (
    input  wire adc_trig,
    input  wire clk,
    output wire dac_data,
    output wire adc_ready
);
  // No arcs by design (see above): STA must report these pins as
  // unconstrained findings, never invent timing through them.
endmodule

module top_mixed (
    input  wire        clk_in,
    input  wire        rst_in,
    input  wire        timer_irq_in,
    input  wire        rf_ready_in,
    input  wire        rdata0_in,
    input  wire        rdata1_in,
    input  wire [31:0] ibus_rdt_in,
    input  wire        ibus_ack_in,
    input  wire [31:0] dbus_rdt_in,
    input  wire        dbus_ack_in,
    input  wire        ext_ready_in,
    input  wire [31:0] ext_rd_in,
    input  wire        adc_trig_in,
    output wire        rf_rreq_out,
    output wire        rf_wreq_out,
    output wire [ 5:0] wreg0_out,
    output wire [ 5:0] wreg1_out,
    output wire        wen0_out,
    output wire        wen1_out,
    output wire        wdata0_out,
    output wire        wdata1_out,
    output wire [ 5:0] rreg0_out,
    output wire [ 5:0] rreg1_out,
    output wire [31:0] ibus_adr_out,
    output wire        ibus_cyc_out,
    output wire [31:0] dbus_adr_out,
    output wire [31:0] dbus_dat_out,
    output wire [ 3:0] dbus_sel_out,
    output wire        dbus_we_out,
    output wire        dbus_cyc_out,
    output wire [ 2:0] ext_funct3_out,
    output wire [31:0] ext_rs1_out,
    output wire [31:0] ext_rs2_out,
    output wire        mdu_valid_out,
    output wire        dac_data_out,
    output wire        adc_ready_out
);

  serv_top cpu (
      .clk(clk_in),
      .i_rst(rst_in),
      .i_timer_irq(timer_irq_in),
      .o_rf_rreq(rf_rreq_out),
      .o_rf_wreq(rf_wreq_out),
      .i_rf_ready(rf_ready_in),
      .o_wreg0(wreg0_out),
      .o_wreg1(wreg1_out),
      .o_wen0(wen0_out),
      .o_wen1(wen1_out),
      .o_wdata0(wdata0_out),
      .o_wdata1(wdata1_out),
      .o_rreg0(rreg0_out),
      .o_rreg1(rreg1_out),
      .i_rdata0(rdata0_in),
      .i_rdata1(rdata1_in),
      .o_ibus_adr(ibus_adr_out),
      .o_ibus_cyc(ibus_cyc_out),
      .i_ibus_rdt(ibus_rdt_in),
      .i_ibus_ack(ibus_ack_in),
      .o_dbus_adr(dbus_adr_out),
      .o_dbus_dat(dbus_dat_out),
      .o_dbus_sel(dbus_sel_out),
      .o_dbus_we(dbus_we_out),
      .o_dbus_cyc(dbus_cyc_out),
      .i_dbus_rdt(dbus_rdt_in),
      .i_dbus_ack(dbus_ack_in),
      .o_ext_funct3(ext_funct3_out),
      .i_ext_ready(ext_ready_in),
      .i_ext_rd(ext_rd_in),
      .o_ext_rs1(ext_rs1_out),
      .o_ext_rs2(ext_rs2_out),
      .o_mdu_valid(mdu_valid_out)
  );

  analog_boundary abound (
      .adc_trig(adc_trig_in),
      .clk(clk_in),
      .dac_data(dac_data_out),
      .adc_ready(adc_ready_out)
  );

endmodule
