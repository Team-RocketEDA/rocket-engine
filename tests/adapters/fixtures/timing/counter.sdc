# counter.sdc — TIMING-STA micro-SDC for the mapped counter.
#
# 10 ns clock plus input/output delays on every boundary pin
# EXCEPT `overflow`, which deliberately carries no output delay:
# the live test asserts `overflow` surfaces in the
# unconstrained-endpoint evidence, never silently assumed.

create_clock -name clk -period 10.0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks clk]
set_clock_transition 0.15 [get_clocks clk]
set_input_delay -clock clk -max 1.0 [get_ports {rst enable}]
set_input_delay -clock clk -min 0.2 [get_ports {rst enable}]
set_input_transition 0.3 [get_ports {rst enable}]
set_output_delay -clock clk -max 1.0 [get_ports {count[0] count[1] count[2] count[3]}]
set_output_delay -clock clk -min 0.2 [get_ports {count[0] count[1] count[2] count[3]}]
set_load 0.05 [get_ports {count[0] count[1] count[2] count[3] overflow}]
