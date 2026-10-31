# adapters/circulax — Circulax time-domain smoke

Smallest honest circulax circuit (CIRCULAX-LIVE): a V step driving
R + C to GND, compiled via kfnetlist and run with
`Circuit.transient` from a discharged start. `run_rc_step` returns
`{circulax_version, R, C, V, t_s[], vc_V[], final_V}` as plain
floats; `circulax_version` names the proven solver per run.

Verified against circulax 0.2.5 (uv.lock pin). Good RC (1k/1nF,
tau=1us) charges Vc(5us)=0.9933, past the 0.9 V threshold; slow RC
(100k/1nF) sits at 0.0488 and misses it — the good-vs-bad signal.
A circulax-less interpreter raises `missing_dependency`, never a
fake verdict. A full `deck.tool: circulax` Engine adapter is
follow-up, out of scope for this smoke.
