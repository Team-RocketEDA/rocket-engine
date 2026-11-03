// Known-bad property over the SERV bit-serial ALU (W=1): the
// same antecedent as serv_alu_prop.v with a negated consequent,
// so sby must fail with a counterexample trace.
module serv_alu_bad (
    input wire clk,
    input wire i_en,
    input wire i_cnt0,
    input wire i_sub,
    input wire [1:0] i_bool_op,
    input wire i_cmp_eq,
    input wire i_cmp_sig,
    input wire [2:0] i_rd_sel,
    input wire i_rs1,
    input wire i_op_b,
    input wire i_buf
);
    wire o_cmp;
    wire o_rd;

    serv_alu dut (
        .clk(clk),
        .i_en(i_en),
        .i_cnt0(i_cnt0),
        .o_cmp(o_cmp),
        .i_sub(i_sub),
        .i_bool_op(i_bool_op),
        .i_cmp_eq(i_cmp_eq),
        .i_cmp_sig(i_cmp_sig),
        .i_rd_sel(i_rd_sel),
        .i_rs1(i_rs1),
        .i_op_b(i_op_b),
        .i_buf(i_buf),
        .o_rd(o_rd)
    );

    always @(posedge clk) begin
        if (i_rd_sel == 3'b000 && i_buf == 1'b0)
            assert(o_rd == 1'b1);
    end
endmodule
