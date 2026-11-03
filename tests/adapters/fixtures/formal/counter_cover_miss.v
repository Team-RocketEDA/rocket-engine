module counter_cover_miss (
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
        if (f_past_valid)
            cover(count == 4'd5 && count == 4'd6);
    end
endmodule
