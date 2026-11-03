# femwell — output dissection

Dissector ref: prior result 5 (text `handoff-de01cc64ffa105316af7294e941da64eda00939d5be4702be13934610c4e76f0-b3082a4e70217300d1a41cc85e6b10aff9db3ecbb6b38e3884dd036da7faf61a.txt`, summary `handoff-28ebc2673eea78fb6acce36f8adb4e298bc8d7234f842ad84606a5a2df78dd7f-70a1668d2d8b404b0795485374498104c766310af8968f69a8ecfb385b186ecc.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `be2c54763f6215757fd2dac543c9385a82ca5b26`
- Clone date: `2026-03-06`
- Pin: not stated
- Doc/source URLs:
  - https://HelgeGehring.github.io/femwell/
  - https://github.com/HelgeGehring/femwell

### Dissector header (verbatim, whitespace-trimmed)

```text
FEMWELL output-capability dissection (REVIEW ONLY, no edits)

Clone: /tmp/rocket-tool-src/femwell/ @ SHA be2c54763f6215757fd2dac543c9385a82ca5b26, date 2026-03-06 (git log -1 --format=%cs). Docs HTML present: /tmp/rocket-tool-docs/femwell-index.html (Femwell sphinx-book index, links to install.html, photonics/electronics examples, benchmarks). Upstream: https://github.com/HelgeGehring/femwell, docs https://HelgeGehring.github.io/femwell/.
```

## 1. Result channels

1. RESULT CHANNELS (femwell is a pure Python library; NO console_scripts/entry-points in pyproject.toml, NO CLI, NO database, NO Touchstone/HDF5/VTK writers in lib code)

| # | Channel | Producing call / flag | Artifact / pattern | Notes |
|---|---|---|---|---|
| A | In-process API returns (PRIMARY) | `femwell.maxwell.waveguide.compute_modes(...)`, `solve_periodic`, `solve_thermal`, `solve_thermal_transient`, `solve_coulomb` (coulomb + tcad), `solve_magnetostatic_2D`, `fefd.compute_modes`, `inplane.compute_modes`, `fiber.*`, `Mode.calculate_*` | Python objects: `Modes`/`Mode` dataclasses, `(skfem.Basis, np.ndarray)` tuples, floats/complex scalars, `meshio.Mesh` | All real results leave this way |
| B | Optional mesh file | `filename=` kwarg of `mesh_from_Dict` (mesh/mesh.py:177-178), `mesh_from_OrderedDict` (mesh/mesh.py:442-443; legacy mesh.py:389-390), `mesh_waveguide(filename,...)` (waveguide.py:15,56) | user-chosen path, conventionally `mesh.msh` (gmsh MSH format via `gmsh.write`) | INTERMEDIATE input mesh, not a result; written only if filename passed |
| C | Solver-cache files | `solver_cached(solver_orig, cache_path)` wrapper (solver.py:145-187) | `{cache_path}/{md5hex}/{n}/0.npz`, `1.npz` (scipy sparse), `params.npz`, `result.npz` (npz archives) | opt-in memoization, not a documented result API |
| D | Matplotlib figures (in-memory) | `Mode.show()` (maxwell/waveguide.py:381-437, calls plt.show), `Mode.plot/plot_component/plot_intensity`, `plot_mode()` (:785-847), `plot_periodic` (mode_solver_2d_periodic.py:66), `visualization.plot_domains/plot_subdomain_boundaries`, `Basis.plot(...).show()` in demos | `Figure`/`Axes`/image handles; nothing written to disk (zero `savefig` in lib) | caller may savefig itself |
| E | stdout text (demo/debug only) | `print(modes)`, `print(modes[0].te_fraction)` (maxwell/waveguide.py:917-918, __main__); `Mode.__repr__`/`Modes.__repr__` (:161-162,:516-518); `print(sign)` tcad.py:66; assorted __main__ prints (thermal.py:204, fefd_2d.py:112-114, magnetostatic.py:169-172); gmsh chatter unless verbose=False | free-form text | NO machine grammar; nothing result-bearing exists ONLY here (all printed values are attributes of returned objects) |
| F | Demo-only XDMF | legacy `femwell/mesh.py:506,512` inside `if __name__=="__main__"` (`meshio.write("facet_mesh.xdmf"/"mesh.msh"...)`); COMMENTED OUT in current mesh/mesh.py:625,631 | `mesh.xdmf`, `facet_mesh.xdmf` | not reachable from library API |
| G | Temp mesh round-trip (internal) | mesh_from_OrderedDict mesh/mesh.py:450-453 writes `{tmpdir}/mesh.msh`, `meshio.read`s it, dir deleted | N/A (ephemeral) | invisible to caller; returns meshio.Mesh |

## 2. Format grammars

2. FORMAT GRAMMARS (parser-author detail per channel)

A1. `compute_modes(basis_epsilon_r, epsilon_r, wavelength, *, mu_r, num_modes, order, metallic_boundaries, radius, n_guess, solver)` (maxwell/waveguide.py:528-654) -> `Modes(modes=[Mode...])`.
`Mode` dataclass (:37-52): frequency:float Hz; k:complex propagation const (sqrt of eigenval lam, :645); basis_epsilon_r:Basis; epsilon_r:NDArray (complex, P0 dofs); basis:Basis (ElementTriN1*ElementTriP1 order=1, N2*P2 order=2); E,H:NDArray complex (power-normalized to 1 via overlap integral, :631-639). Derived: omega=2*pi*f (:54-57); k0=omega/c (:59-62); wavelength=c/f (:64-67); n_eff=k/k0 complex — loss lives in imag part (:69-72). `Modes.n_effs` -> np.ndarray (:523-525). Units: SI implied by inputs (caller passes wavelength in um-as-1.0 scale, e.g. `wavelength=1.55*scale`, :908-916; epsilon dimensionless). Scalar methods: te_fraction/tm_fraction/transversality floats (:112-160); calculate_overlap/complex (:699-759, 0.5*cross(E,H) functional); calculate_power (:218-223); calculate_confinement_factor (:225-249, SI: c*eps0*integral); calculate_propagation_loss(distance) dB (:215-216: `-20/ln10*k0*imag(n_eff)*distance`); calculate_effective_area m^2-scale (:181-213); calculate_pertubated_neff (:251-258); calculate_intensity -> (Basis DG-P1, NDArray) (:260-280, `0.5*Re(Ex*Hy-Ey*Hx)`); poynting/Sx/Sy/Sz (:74-110); eval_error_estimator -> per-element np array (:473-502).
Real example (docs/photonics/examples/waveguide_modes.py:85): `print(f"Effective refractive index: {mode.n_eff:.4f}")`; repr shape: `Mode(k: ..., n_eff:...)`, `Modes(modes=(\n\tMode...\n))`. vary_width.py:64: `all_neffs[i]=np.real([mode.n_eff for mode in modes])`; GVD example :117 appends `np.real(mode.n_eff)` over wavelength sweep; propagation_loss.py:161 uses `modes[0].n_eff.imag`.

A2. Field-solver tuple convention — every PDE solver returns `(skfem.Basis, np.ndarray)`:
- thermal.solve_thermal (thermal.py:22-90): (basis P1/P2/P3, temperature dofs, K). Inputs W/m·K, S/m, A, fixed {facet:value}.
- thermal_transient.solve_thermal_transient (:15-100): (basis, list[ndarray] temperatures incl. t0, Crank-Nicolson theta=0.5).
- coulomb.solve_coulomb (coulomb.py:19-33), tcad.solve_coulomb (tcad.py:11-61), tcad.solve_continuity_equations (tcad.py:64-~136): (P1 basis, potential/carrier dofs).
- magnetostatic.solve_magnetostatic_2D (magnetostatic.py:33-61): (basis, vector-potential A dofs).
- fefd.compute_modes (fefd.py:22-44): (basis, FE solution vector x of driven (A+C)x=source system).
- inplane.compute_modes (mode_solver_inplane.py:21-77): `(np.sqrt(lams), basis, xs)` tuple (ks, basis, eigenvectors) — NOTE different shape (3-tuple, NO Modes wrapper).
- periodic.solve_periodic (mode_solver_2d_periodic.py:11-63): `(ks, basis_phi, phis)` 3-tuple, ks=eigenvalues (20 requested, LM around sigma), phis columns.
- fiber.py: `zr/mfr_at/r_at/e_field_gaussian` return floats/complex (SI: m); `overlap(basis,E_i,E_j)` (:35-46) returns float |int/sqrt| in [0,1].
- schrodinger/1d/2d-quadratic/fefd_2d modules are bare scripts (module-level solve + .show()), no reusable function API.
There is NO xarray/Dataset anywhere (repo-wide regex search: zero hits); pandas appears ONLY in docs examples (calculate_GVD.py:27, benchmarks/mode_solver*.py:29) for caller-side post-processing, never returned by the library.

B. Mesh file grammar: gmsh MSH 4.x ASCII (written by `gmsh.write`, version = installed gmsh>=4.13.1 per pyproject). Physical names = OrderedDict/Dict keys (e.g. core/clad/box). Schema owned by gmsh, not this repo. meshio.read returns Mesh(points, cells, cell_data, field_data). Demo default `mesh.msh` literal appears in ~12 __main__ blocks (e.g. thermal.py:158-160 `Mesh.load("mesh.msh")`).

C. Cache grammar: scipy.sparse .npz (CSR pickles of K,M) + `params.npz` (kwargs dict) + `result.npz` (positional solver outputs, `*result`). Key = md5(matrix0.data+matrix1.data+str(kwargs)) hex dir. No stability contract; internal.

D. Plot grammar: none (pixels). `plot_component(field in {E,H}, component in {x,y,z,n,t}, part in {real,imag,abs}|callable)` returns Axes; `plot_mode` returns (fig, axs 1x3 Ex/Ey/Ez or 1x2 vector); `plot_intensity(normalize=True)` returns (fig,ax), intensity/max. Titles `f"${title}_{component}$"`, `f"{field}{component} ({conv}. part)"`.

E. stdout grammar: none stable. `Modes.__repr__` joins child reprs newline+tab. thermal.py:204 demo: `f"Phase shift: {2*pi/1.55*(neffs[-1]-neffs[0])*320}"`. tcad.py:66 prints bare `-1`/`1`.

## 3. Python bindings verdict

3. PYTHON BINDINGS: the library IS the binding — 100% Python, `import femwell.<module>` (top `femwell/__init__.py` exports only `__version__`; `femwell.mesh` exports mesh_from_OrderedDict/mesh_from_Dict/MeshTracker, mesh/__init__.py; maxwell/__init__.py EMPTY — must `from femwell.maxwell.waveguide import compute_modes, Mode, Modes`). Deps: scikit-fem>=8.1.0, gmsh>=4.13.1, pygmsh, matplotlib, meshwell==2.0.0 (pyproject). AUDIT ROW VERDICT: CONFIRMED with two corrections: (a) focus hint "xarray/datasets" is WRONG — returns are numpy ndarrays + skfem Basis + frozen dataclasses, no xarray/pandas in lib; (b) "plots" are in-memory matplotlib objects, never files. Audit row (tool-bindings-audit.md:89): femwell UNPINNED, native Python FEM (scikit-fem based), in-API fields/modes, DEFER (post_mvp; pin on adopt) — accurate.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE: NONE that matters. Every printed number (n_eff, te_fraction, phase shift, overlap, sign) is an attribute/return of an in-process object. Stdout exists only in __main__ demos and one debug print (tcad.py:66). gmsh mesher chatter is suppressible (verbose=False default; redirect_stdout in mesh round-trip :450). No adapter ever needs to scrape stdout.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference bindings > structured files > deterministic text):
Rank 1 (only sane path): BINDINGS — subprocess driver script that imports femwell, runs compute_modes/solvers, and emits a JSON envelope of {n_effs (re/im), k, te_fraction, power, confinement, loss_dB, effective_area, field-dof arrays or interpolated grids} + mesh metadata. Execution stays subprocess per audit rule; READING via API. No text grammar to research.
Rank 2 (fallback, lossy): mesh.msh via filename= (gmsh MSH 4.x, third-party schema) — carries geometry only, not mode results; never sufficient alone.
Rank 3: none — stdout scraping explicitly NOT recommended (no stable grammar, nothing exclusive).
PIN/VERSION EVIDENCE (verified at): provision_toolchain.sh contains NO femwell pin (absent from pins, checks, installers — full-file read); tool-bindings-audit.md:89 + :200-201 list femwell UNPINNED / "pin on adopt", DEFER post_mvp; repo pyproject.toml: name femwell version 0.0.1, meshwell==2.0.0, scikit-fem>=8.1.0, gmsh>=4.13.1. Adapter work is gated on choosing a pin (recommend SHA be2c547 + PyPI version check at adoption time).

## Weak-evidence gaps (flagged by dissector)

- | E | stdout text (demo/debug only) | `print(modes)`, `print(modes[0].te_fraction)` (maxwell/waveguide.py:917-918, __main__); `Mode.__repr__`/`Modes.__repr__` (:161-162,:516-518); `print(sign)` tcad.py:66; assorted __main__ prints (thermal.py:204, fefd_2d.py:1
- 4. STDIO-ONLY RESIDUE: NONE that matters. Every printed number (n_eff, te_fraction, phase shift, overlap, sign) is an attribute/return of an in-process object. Stdout exists only in __main__ demos and one debug print (tcad.py:66). gmsh mesher chatter is suppre
- 3. PYTHON BINDINGS: the library IS the binding — 100% Python, `import femwell.<module>` (top `femwell/__init__.py` exports only `__version__`; `femwell.mesh` exports mesh_from_OrderedDict/mesh_from_Dict/MeshTracker, mesh/__init__.py; maxwell/__init__.py EMPTY
- PIN/VERSION EVIDENCE (verified at): provision_toolchain.sh contains NO femwell pin (absent from pins, checks, installers — full-file read); tool-bindings-audit.md:89 + :200-201 list femwell UNPINNED / "pin on adopt", DEFER post_mvp; repo pyproject.toml: name f

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
FEMWELL output-capability dissection (REVIEW ONLY, no edits)

Clone: /tmp/rocket-tool-src/femwell/ @ SHA be2c54763f6215757fd2dac543c9385a82ca5b26, date 2026-03-06 (git log -1 --format=%cs). Docs HTML present: /tmp/rocket-tool-docs/femwell-index.html (Femwell sphinx-book index, links to install.html, photonics/electronics examples, benchmarks). Upstream: https://github.com/HelgeGehring/femwell, docs https://HelgeGehring.github.io/femwell/.

1. RESULT CHANNELS (femwell is a pure Python library; NO console_scripts/entry-points in pyproject.toml, NO CLI, NO database, NO Touchstone/HDF5/VTK writers in lib code)

| # | Channel | Producing call / flag | Artifact / pattern | Notes |
|---|---|---|---|---|
| A | In-process API returns (PRIMARY) | `femwell.maxwell.waveguide.compute_modes(...)`, `solve_periodic`, `solve_thermal`, `solve_thermal_transient`, `solve_coulomb` (coulomb + tcad), `solve_magnetostatic_2D`, `fefd.compute_modes`, `inplane.compute_modes`, `fiber.*`, `Mode.calculate_*` | Python objects: `Modes`/`Mode` dataclasses, `(skfem.Basis, np.ndarray)` tuples, floats/complex scalars, `meshio.Mesh` | All real results leave this way |
| B | Optional mesh file | `filename=` kwarg of `mesh_from_Dict` (mesh/mesh.py:177-178), `mesh_from_OrderedDict` (mesh/mesh.py:442-443; legacy mesh.py:389-390), `mesh_waveguide(filename,...)` (waveguide.py:15,56) | user-chosen path, conventionally `mesh.msh` (gmsh MSH format via `gmsh.write`) | INTERMEDIATE input mesh, not a result; written only if filename passed |
| C | Solver-cache files | `solver_cached(solver_orig, cache_path)` wrapper (solver.py:145-187) | `{cache_path}/{md5hex}/{n}/0.npz`, `1.npz` (scipy sparse), `params.npz`, `result.npz` (npz archives) | opt-in memoization, not a documented result API |
| D | Matplotlib figures (in-memory) | `Mode.show()` (maxwell/waveguide.py:381-437, calls plt.show), `Mode.plot/plot_component/plot_intensity`, `plot_mode()` (:785-847), `plot_periodic` (mode_solver_2d_periodic.py:66), `visualization.plot_domains/plot_subdomain_boundaries`, `Basis.plot(...).show()` in demos | `Figure`/`Axes`/image handles; nothing written to disk (zero `savefig` in lib) | caller may savefig itself |
| E | stdout text (demo/debug only) | `print(modes)`, `print(modes[0].te_fraction)` (maxwell/waveguide.py:917-918, __main__); `Mode.__repr__`/`Modes.__repr__` (:161-162,:516-518); `print(sign)` tcad.py:66; assorted __main__ prints (thermal.py:204, fefd_2d.py:112-114, magnetostatic.py:169-172); gmsh chatter unless verbose=False | free-form text | NO machine grammar; nothing result-bearing exists ONLY here (all printed values are attributes of returned objects) |
| F | Demo-only XDMF | legacy `femwell/mesh.py:506,512` inside `if __name__=="__main__"` (`meshio.write("facet_mesh.xdmf"/"mesh.msh"...)`); COMMENTED OUT in current mesh/mesh.py:625,631 | `mesh.xdmf`, `facet_mesh.xdmf` | not reachable from library API |
| G | Temp mesh round-trip (internal) | mesh_from_OrderedDict mesh/mesh.py:450-453 writes `{tmpdir}/mesh.msh`, `meshio.read`s it, dir deleted | N/A (ephemeral) | invisible to caller; returns meshio.Mesh |

2. FORMAT GRAMMARS (parser-author detail per channel)

A1. `compute_modes(basis_epsilon_r, epsilon_r, wavelength, *, mu_r, num_modes, order, metallic_boundaries, radius, n_guess, solver)` (maxwell/waveguide.py:528-654) -> `Modes(modes=[Mode...])`.
`Mode` dataclass (:37-52): frequency:float Hz; k:complex propagation const (sqrt of eigenval lam, :645); basis_epsilon_r:Basis; epsilon_r:NDArray (complex, P0 dofs); basis:Basis (ElementTriN1*ElementTriP1 order=1, N2*P2 order=2); E,H:NDArray complex (power-normalized to 1 via overlap integral, :631-639). Derived: omega=2*pi*f (:54-57); k0=omega/c (:59-62); wavelength=c/f (:64-67); n_eff=k/k0 complex — loss lives in imag part (:69-72). `Modes.n_effs` -> np.ndarray (:523-525). Units: SI implied by inputs (caller passes wavelength in um-as-1.0 scale, e.g. `wavelength=1.55*scale`, :908-916; epsilon dimensionless). Scalar methods: te_fraction/tm_fraction/transversality floats (:112-160); calculate_overlap/complex (:699-759, 0.5*cross(E,H) functional); calculate_power (:218-223); calculate_confinement_factor (:225-249, SI: c*eps0*integral); calculate_propagation_loss(distance) dB (:215-216: `-20/ln10*k0*imag(n_eff)*distance`); calculate_effective_area m^2-scale (:181-213); calculate_pertubated_neff (:251-258); calculate_intensity -> (Basis DG-P1, NDArray) (:260-280, `0.5*Re(Ex*Hy-Ey*Hx)`); poynting/Sx/Sy/Sz (:74-110); eval_error_estimator -> per-element np array (:473-502).
Real example (docs/photonics/examples/waveguide_modes.py:85): `print(f"Effective refractive index: {mode.n_eff:.4f}")`; repr shape: `Mode(k: ..., n_eff:...)`, `Modes(modes=(\n\tMode...\n))`. vary_width.py:64: `all_neffs[i]=np.real([mode.n_eff for mode in modes])`; GVD example :117 appends `np.real(mode.n_eff)` over wavelength sweep; propagation_loss.py:161 uses `modes[0].n_eff.imag`.

A2. Field-solver tuple convention — every PDE solver returns `(skfem.Basis, np.ndarray)`:
- thermal.solve_thermal (thermal.py:22-90): (basis P1/P2/P3, temperature dofs, K). Inputs W/m·K, S/m, A, fixed {facet:value}.
- thermal_transient.solve_thermal_transient (:15-100): (basis, list[ndarray] temperatures incl. t0, Crank-Nicolson theta=0.5).
- coulomb.solve_coulomb (coulomb.py:19-33), tcad.solve_coulomb (tcad.py:11-61), tcad.solve_continuity_equations (tcad.py:64-~136): (P1 basis, potential/carrier dofs).
- magnetostatic.solve_magnetostatic_2D (magnetostatic.py:33-61): (basis, vector-potential A dofs).
- fefd.compute_modes (fefd.py:22-44): (basis, FE solution vector x of driven (A+C)x=source system).
- inplane.compute_modes (mode_solver_inplane.py:21-77): `(np.sqrt(lams), basis, xs)` tuple (ks, basis, eigenvectors) — NOTE different shape (3-tuple, NO Modes wrapper).
- periodic.solve_periodic (mode_solver_2d_periodic.py:11-63): `(ks, basis_phi, phis)` 3-tuple, ks=eigenvalues (20 requested, LM around sigma), phis columns.
- fiber.py: `zr/mfr_at/r_at/e_field_gaussian` return floats/complex (SI: m); `overlap(basis,E_i,E_j)` (:35-46) returns float |int/sqrt| in [0,1].
- schrodinger/1d/2d-quadratic/fefd_2d modules are bare scripts (module-level solve + .show()), no reusable function API.
There is NO xarray/Dataset anywhere (repo-wide regex search: zero hits); pandas appears ONLY in docs examples (calculate_GVD.py:27, benchmarks/mode_solver*.py:29) for caller-side post-processing, never returned by the library.

B. Mesh file grammar: gmsh MSH 4.x ASCII (written by `gmsh.write`, version = installed gmsh>=4.13.1 per pyproject). Physical names = OrderedDict/Dict keys (e.g. core/clad/box). Schema owned by gmsh, not this repo. meshio.read returns Mesh(points, cells, cell_data, field_data). Demo default `mesh.msh` literal appears in ~12 __main__ blocks (e.g. thermal.py:158-160 `Mesh.load("mesh.msh")`).

C. Cache grammar: scipy.sparse .npz (CSR pickles of K,M) + `params.npz` (kwargs dict) + `result.npz` (positional solver outputs, `*result`). Key = md5(matrix0.data+matrix1.data+str(kwargs)) hex dir. No stability contract; internal.

D. Plot grammar: none (pixels). `plot_component(field in {E,H}, component in {x,y,z,n,t}, part in {real,imag,abs}|callable)` returns Axes; `plot_mode` returns (fig, axs 1x3 Ex/Ey/Ez or 1x2 vector); `plot_intensity(normalize=True)` returns (fig,ax), intensity/max. Titles `f"${title}_{component}$"`, `f"{field}{component} ({conv}. part)"`.

E. stdout grammar: none stable. `Modes.__repr__` joins child reprs newline+tab. thermal.py:204 demo: `f"Phase shift: {2*pi/1.55*(neffs[-1]-neffs[0])*320}"`. tcad.py:66 prints bare `-1`/`1`.

3. PYTHON BINDINGS: the library IS the binding — 100% Python, `import femwell.<module>` (top `femwell/__init__.py` exports only `__version__`; `femwell.mesh` exports mesh_from_OrderedDict/mesh_from_Dict/MeshTracker, mesh/__init__.py; maxwell/__init__.py EMPTY — must `from femwell.maxwell.waveguide import compute_modes, Mode, Modes`). Deps: scikit-fem>=8.1.0, gmsh>=4.13.1, pygmsh, matplotlib, meshwell==2.0.0 (pyproject). AUDIT ROW VERDICT: CONFIRMED with two corrections: (a) focus hint "xarray/datasets" is WRONG — returns are numpy ndarrays + skfem Basis + frozen dataclasses, no xarray/pandas in lib; (b) "plots" are in-memory matplotlib objects, never files. Audit row (tool-bindings-audit.md:89): femwell UNPINNED, native Python FEM (scikit-fem based), in-API fields/modes, DEFER (post_mvp; pin on adopt) — accurate.

4. STDIO-ONLY RESIDUE: NONE that matters. Every printed number (n_eff, te_fraction, phase shift, overlap, sign) is an attribute/return of an in-process object. Stdout exists only in __main__ demos and one debug print (tcad.py:66). gmsh mesher chatter is suppressible (verbose=False default; redirect_stdout in mesh round-trip :450). No adapter ever needs to scrape stdout.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference bindings > structured files > deterministic text):
Rank 1 (only sane path): BINDINGS — subprocess driver script that imports femwell, runs compute_modes/solvers, and emits a JSON envelope of {n_effs (re/im), k, te_fraction, power, confinement, loss_dB, effective_area, field-dof arrays or interpolated grids} + mesh metadata. Execution stays subprocess per audit rule; READING via API. No text grammar to research.
Rank 2 (fallback, lossy): mesh.msh via filename= (gmsh MSH 4.x, third-party schema) — carries geometry only, not mode results; never sufficient alone.
Rank 3: none — stdout scraping explicitly NOT recommended (no stable grammar, nothing exclusive).
PIN/VERSION EVIDENCE (verified at): provision_toolchain.sh contains NO femwell pin (absent from pins, checks, installers — full-file read); tool-bindings-audit.md:89 + :200-201 list femwell UNPINNED / "pin on adopt", DEFER post_mvp; repo pyproject.toml: name femwell version 0.0.1, meshwell==2.0.0, scikit-fem>=8.1.0, gmsh>=4.13.1. Adapter work is gated on choosing a pin (recommend SHA be2c547 + PyPI version check at adoption time).
```
