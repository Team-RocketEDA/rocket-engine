library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity tb_good is
end entity tb_good;
architecture sim of tb_good is
  signal clk : std_logic := '0';
  signal rst : std_logic := '1';
  signal q : unsigned(3 downto 0);
begin
  dut : entity work.counter port map (clk => clk, rst => rst, q => q);
  clock : process
  begin
    for i in 0 to 59 loop
      wait for 5 ns;
      clk <= not clk;
    end loop;
    wait;
  end process clock;
  stim : process
  begin
    wait for 25 ns;
    rst <= '0';
    wait for 100 ns;
    assert q /= "0000" report "counter stuck" severity error;
    report "PASS done" severity note;
    wait;
  end process stim;
end architecture sim;
