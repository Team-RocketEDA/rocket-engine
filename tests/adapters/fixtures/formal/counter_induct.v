module counter_induct (
    input wire clk,
    input wire rst,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'd0;
        else
            count <= count + 1'b1;
    end

    reg f_past_valid;
    initial f_past_valid = 0;
    always @(posedge clk)
        f_past_valid <= 1;
    always @(*) begin
        if (!f_past_valid)
            assume(rst);
    end
    always @(posedge clk) begin
        if (f_past_valid && !rst)
            assert(count != 4'd0 || $past(rst));
    end
endmodule
