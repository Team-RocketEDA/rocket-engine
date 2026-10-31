# adapters/meow — Meow EME smoke

Smallest honest EME circuit (MEOW-LIVE): a 500x220nm Si strip
on SiO2 at 1550nm, 2 modes solved with meow's tidy3d FDE
backend, cascaded over a 10um cell with meow's SAX EME
backend. `run_eme_smoke` returns `{meow_version,
tidy3d_version, wl_um, widths_um[], cell_length_um, num_modes,
neff_re[], neff_im[], transmission, reflection, s21_phase_rad,
ports}` as plain floats; the version fields name the proven
solver pair per run.

Verified against meow 0.15.0 over tidy3d 2.10.0 (uv.lock
pins). The matched guide transmits T=1.0/R=0.0; an abrupt
0.5->1.0um width step drops the fundamental to T=0.877 with
R>0 — the good-vs-bad signal. A meow-less interpreter raises
`missing_dependency`, never a fake verdict.

Local-only: engine code never imports the tidy3d client (the
backend version is read from installed metadata), and the
smoke path runs with `socket.connect` amputated in
`tests/adapters/test_meow.py`. The full on-device-vs-cloud
verdict lives in `docs/tickets/MEOW-LIVE.md`. A full
`deck.tool: meow` Engine adapter is follow-up, out of scope
for this smoke.
