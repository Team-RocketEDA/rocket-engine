# devsim — output dissection

Dissector ref: prior result 10 (text `handoff-973e053b2e0a055815cfcd21153e6a94d0ee99ceebe59b17ec6b19214170fd04-f68bf5d2207f070e156f6dfc14d3accb2eae118a9d696acf58594363b6bafbff.txt`, summary `handoff-63d776d0b3aff068101aff9852c215c0a5a09bcd533dcc062d5c26b6e4566f0b-f68bf5d2207f070e156f6dfc14d3accb2eae118a9d696acf58594363b6bafbff.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `e3a25f08c7f17cc6932624c12bf9f0f10d7f7cfd`
- Clone date: `2026-10-23`
- Pin: Clone: /tmp/rocket-tool-src/devsim/ SHA e3a25f08c7f17cc6932624c12bf9f0f10d7f7cfd, date 2026-10-23. Pin/version: 2.11.2 — rocket-engine/scripts/provision_toolchain.sh:94 DEVSIM_PIN="2.11.2", CMakeLists.txt:22 DEVSIM_VERSION_STRING "2.11.2" (matches clone). Docs HTML (/tmp/rocket-tool-docs/devsim-inde
- Doc/source URLs:
  - https://devsim.org/index.html

### Dissector header (verbatim, whitespace-trimmed)

```text
DEVSIM output dissection (REVIEW ONLY, no edits)
Clone: /tmp/rocket-tool-src/devsim/ SHA e3a25f08c7f17cc6932624c12bf9f0f10d7f7cfd, date 2026-10-23. Pin/version: 2.11.2 — rocket-engine/scripts/provision_toolchain.sh:94 DEVSIM_PIN="2.11.2", CMakeLists.txt:22 DEVSIM_VERSION_STRING "2.11.2" (matches clone). Docs HTML (/tmp/rocket-tool-docs/devsim-index.html, canonical https://devsim.org/index.html) is a landing page with no grammars; grammars below are from source + in-repo doc/devsim.pdf companion + testing/ usage.
```

## 1. Result channels

1. RESULT CHANNELS (one table)
DEVSIM has no CLI binary and no DB — it is a Python C-extension driven by user scripts; "result channels" = API returns + write_devices() files + stdout text.
| # | channel | producing call | filename/pattern | content |
|---|---|---|---|---|
| A1 | API float | get_contact_current / get_contact_charge(device,contact,equation) (MathCommands.cc:431) | n/a (return) | current (A) / charge (C) for one contact equation |
| A2 | API float list | get_node/edge/element/interface_model_values(device,region,name) (ModelCommands.cc:1193,~1267; DevsimDoc.cc:1506-1580) | n/a | per-node/per-edge/per-element values, region order |
| A3 | API str list | get_device_list, get_region_list, get_contact_list, get_*_model_list, get_equation_list, get_circuit_node_list/solution_list (CommandTable.cc) | n/a | inventory queries |
| A4 | API float | get_circuit_node_value(solution='dcop',node) (CircuitCommands.cc:549) | n/a | circuit node voltage/value incl. AC/noise solutions |
| A5 | API dict | get_matrix_and_rhs(format='csc'\|'csr') (MathCommands.cc:280-303; Newton.cc:521-595) | n/a | {static:{ai,ap,av,rhs}, dynamic:{...}, permutation:{row,copy}}; ai/ap=int index ptrs, av/rhs=float lists |
| A6 | API dict | solve(...,info=True) (MathCommands.cc:192; Newton.cc:613-866) | n/a | {iterations:[{iteration,devices?,circuit:{relative_error,absolute_error}}...], converged:bool, iteration:int, charge_error?} |
| F1 | restart file | write_devices(file=...,device?,type='devsim'\|default) (MeshingCommands.cc:814-816) | literal `file` arg; tests use *.msh (testing/mesh2d.py:99, mos_2d.py:88) | full mesh+model+equation state; reloadable via load_devices() |
| F2 | data file | write_devices(type='devsim_data') (MeshingCommands.cc:818) | literal `file` | mesh + node/edge solutions only (no equations) |
| F3 | VTK bundle | write_devices(type='vtk') (VTKWriter.cc:460-560) | <file>.vtm + <file>.visit + <file>_<i>.vtu per region (testing/dio2_element_2d.py:136) | XML UnstructuredGrid per region, zlib+base64 Float64 |
| F4 | Tecplot ASCII | write_devices(type='tecplot') (TecplotWriter.cc:622-782) | literal `file`; tests use *.tec (testing/mos_2d_create.py:207) | TITLE/VARIABLES/ZONE BLOCK data, 1 zone per region |
| S1 | stdout text | print_node/edge/element_values (ModelCommands.cc:1254-1265,1339-1349,1438-1479) | — | "<name>\n" + one %.5e value per line |
| S2 | stdout log | solve() iteration/circuit/device error lines (Newton.cc:882-910) | — | "Iteration: N", "  Circuit: RelError: x AbsError: y", per-device lines |
| S3 | exceptions | any command failure via SetErrorResult | — | Python exception text (NOT stdout); file-open failures surface here too |
No database, no .pos/Gmsh-POS writer, no gnuplot writer ("pos" hits in MeshingCommands.cc:188,249 are mesh-line position params, not outputs). Errors go to exceptions; OutputStream.cc:24-60 routes INFO/VERBOSE/ERROR/FATAL all to PySys stdout (only fallback "Could not find output channel!" touches real stderr).

## 2. Format grammars

2. FORMAT GRAMMARS
Units: user-defined by model equations; no unit tags in any format (mesh coords echoed as given, typically um; currents A, charges C, potentials V by equation definition).
(a) Tecplot ASCII (TecplotWriter.cc:622-782), default ostream precision (~6 sig figs; the setprecision(15) at :407 is commented out):
TITLE = "<device>"
VARIABLES = "x"[,"y"][,"z"], "<nodeModel>"... [", VARLOCATION=([k,...])=CELLCENTERED)" appended per ZONE line for element models]
ZONE T="<region>" NODES=<n>, ELEMENTS=<m>, DATAPACKING=BLOCK, ZONETYPE=FELINESEG|FETRIANGLE|FETETRAHEDRON
then one whitespace-separated BLOCK per variable (x, y?, z?, node models, scalar edge models, vector edge models expanded as <name>_x_onNode/_y/_z, cell-centered element models), then 1-based connectivity (edges: 2 ints/line :367; triangles 3 :379; tets 4 :392). Scalar-model name collisions across types warn on stdout (:490,568) and first type wins.
(b) VTK bundle (VTKWriter.cc:30-66,460-560), setprecision(15) scientific for XML scaffolding; arrays binary: <DataArray type="Float64" Name="<model>" [NumberOfComponents="k"] format="binary"> base64(zlib(raw LE doubles)) </DataArray> inside <Points>/<PointData>/<CellData>/<Cells> of <VTKFile type="UnstructuredGrid" ... compressor="vtkZLibDataCompressor">. <file>.vtm = vtkMultiBlockDataSet listing each <file>_<i>.vtu; <file>.visit = "!NBLOCKS <n>" + one vtu path per line. NOT legacy ParaView ASCII (see §3 correction).
(c) devsim restart (DevsimRestartWriter.cc) + devsim_data (DevsimWriter.cc), %.15e scientific (:135). begin_/end_ blocks: begin_device "<dev>" / begin_region "<r>" "<material>" / begin_coordinates (x\ty\tz per line) / begin_nodes (index/line) / begin_edges|triangles|tetrahedra (tab-sep 0-based indices) / begin_node_solution "<name>"|begin_edge_solution "<name>" (one value/line) / begin_contact "<c>" "<region>" "<mat>" + member begin_nodes lists. Restart adds equations/models/interface blocks (:99-162,211-293). Machine grammar = src/meshing/DevsimParser.y + DevsimScanner.l (also load path DevsimLoader.cc); mesh-only schema in GmshParser.y for the gmsh input side.
(d) API shapes: A2 lists are plain Python float lists in node/edge/element index order (SetListAsResult); A5 ai/ap = 0-based CSC (default CCM) or CSR index arrays; A6 iteration maps mirror the stdout log line-for-line.
Real repo examples (no golden .tec/.vtu blobs; goldenresults/ holds only README.txt): testing/mesh2d.py:99-103 write_devices .msh/.tec + include_test callback; testing/mos_2d.py:65,88 vtk + devsim; testing/cap2.py:362,366 print(get_matrix_and_rhs()), get_node_model_values(device,region,"Potential"); examples/diode/*.py + capacitance/cap1d.py show IV/CV loops reading A1/A2 per bias step.

## 3. Python bindings verdict

3. PYTHON BINDINGS (audit row: "native Python-scripted TCAD (solve/get_contact_charge/write_devices) | ParaView ASCII + restart" — CONFIRMED with one correction)
Import: `import devsim` (+ `from devsim import <cmd>` per testing/cap2.py:39-40); C-extension module (src/pythonapi/PythonCommands.cc:207-232, moduledef; Interpreter.cc:38), type stubs at dist/__init__.pyi. Returns natively: all of A1-A6 (floats, float/str lists, nested dicts of POD arrays) — nothing requires parsing. CORRECTION: "ParaView ASCII" is wrong for VTK: type='vtk' emits XML VTU (binary payloads) + .vtm + .visit; only type='tecplot' is ASCII (and it is Tecplot BLOCK ASCII, ParaView-readable but not "ParaView ASCII" legacy format). Execution model fits TOOL-OUTPUTS: driver script runs in a subprocess; bindings read results (in that script or a reader pass).

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE: effectively NONE for numeric results. Every numeric stdout line has an API twin: S1 print_* ⟷ A2 get_* (same GetScalarValues source); S2 iteration log ⟷ A6 solve(info=True) maps (PrintIteration/PrintCircuitErrors populate both, Newton.cc:882-910); S3 errors raise catchable exceptions with the message. Residual stdio-only content is cosmetic: iteration-log formatting, "Writing model X as <type>..." collision warnings (TecplotWriter.cc:490,568), "Could not open ..." strings (also returned as exceptions). AC/noise/transient values are retrievable via get_circuit_node_value/get_*_model_values after solve — no scrape needed.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS bindings > structured files > deterministic text)
1) Bindings: run user/devsim script in subprocess; driver calls A1/A2/A4/A5/A6 + solve(info=True) and dumps JSON — full fidelity, zero parsing. 2) VTK bundle: XML + base64/zlib Float64, parseable with stdlib (xml, zlib, base64, struct); filename glob <stem>.vtm + <stem>_*.vtu. 3) devsim/devsim_data restart: exact grammar in DevsimParser.y/DevsimScanner.l but heavier. 4) Tecplot ASCII last (6-sig-fig loss, name-collision coercion). Never scrape S1/S2. Verified at: clone e3a25f08 (2026-10-23) == pin 2.11.2 (provision_toolchain.sh:94, CMakeLists.txt:22, provision-sources.md §14 pip route); DEFER post_mvp-only per audit, so no adapter work until wave 4.

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
DEVSIM output dissection (REVIEW ONLY, no edits)
Clone: /tmp/rocket-tool-src/devsim/ SHA e3a25f08c7f17cc6932624c12bf9f0f10d7f7cfd, date 2026-10-23. Pin/version: 2.11.2 — rocket-engine/scripts/provision_toolchain.sh:94 DEVSIM_PIN="2.11.2", CMakeLists.txt:22 DEVSIM_VERSION_STRING "2.11.2" (matches clone). Docs HTML (/tmp/rocket-tool-docs/devsim-index.html, canonical https://devsim.org/index.html) is a landing page with no grammars; grammars below are from source + in-repo doc/devsim.pdf companion + testing/ usage.

1. RESULT CHANNELS (one table)
DEVSIM has no CLI binary and no DB — it is a Python C-extension driven by user scripts; "result channels" = API returns + write_devices() files + stdout text.
| # | channel | producing call | filename/pattern | content |
|---|---|---|---|---|
| A1 | API float | get_contact_current / get_contact_charge(device,contact,equation) (MathCommands.cc:431) | n/a (return) | current (A) / charge (C) for one contact equation |
| A2 | API float list | get_node/edge/element/interface_model_values(device,region,name) (ModelCommands.cc:1193,~1267; DevsimDoc.cc:1506-1580) | n/a | per-node/per-edge/per-element values, region order |
| A3 | API str list | get_device_list, get_region_list, get_contact_list, get_*_model_list, get_equation_list, get_circuit_node_list/solution_list (CommandTable.cc) | n/a | inventory queries |
| A4 | API float | get_circuit_node_value(solution='dcop',node) (CircuitCommands.cc:549) | n/a | circuit node voltage/value incl. AC/noise solutions |
| A5 | API dict | get_matrix_and_rhs(format='csc'\|'csr') (MathCommands.cc:280-303; Newton.cc:521-595) | n/a | {static:{ai,ap,av,rhs}, dynamic:{...}, permutation:{row,copy}}; ai/ap=int index ptrs, av/rhs=float lists |
| A6 | API dict | solve(...,info=True) (MathCommands.cc:192; Newton.cc:613-866) | n/a | {iterations:[{iteration,devices?,circuit:{relative_error,absolute_error}}...], converged:bool, iteration:int, charge_error?} |
| F1 | restart file | write_devices(file=...,device?,type='devsim'\|default) (MeshingCommands.cc:814-816) | literal `file` arg; tests use *.msh (testing/mesh2d.py:99, mos_2d.py:88) | full mesh+model+equation state; reloadable via load_devices() |
| F2 | data file | write_devices(type='devsim_data') (MeshingCommands.cc:818) | literal `file` | mesh + node/edge solutions only (no equations) |
| F3 | VTK bundle | write_devices(type='vtk') (VTKWriter.cc:460-560) | <file>.vtm + <file>.visit + <file>_<i>.vtu per region (testing/dio2_element_2d.py:136) | XML UnstructuredGrid per region, zlib+base64 Float64 |
| F4 | Tecplot ASCII | write_devices(type='tecplot') (TecplotWriter.cc:622-782) | literal `file`; tests use *.tec (testing/mos_2d_create.py:207) | TITLE/VARIABLES/ZONE BLOCK data, 1 zone per region |
| S1 | stdout text | print_node/edge/element_values (ModelCommands.cc:1254-1265,1339-1349,1438-1479) | — | "<name>\n" + one %.5e value per line |
| S2 | stdout log | solve() iteration/circuit/device error lines (Newton.cc:882-910) | — | "Iteration: N", "  Circuit: RelError: x AbsError: y", per-device lines |
| S3 | exceptions | any command failure via SetErrorResult | — | Python exception text (NOT stdout); file-open failures surface here too |
No database, no .pos/Gmsh-POS writer, no gnuplot writer ("pos" hits in MeshingCommands.cc:188,249 are mesh-line position params, not outputs). Errors go to exceptions; OutputStream.cc:24-60 routes INFO/VERBOSE/ERROR/FATAL all to PySys stdout (only fallback "Could not find output channel!" touches real stderr).

2. FORMAT GRAMMARS
Units: user-defined by model equations; no unit tags in any format (mesh coords echoed as given, typically um; currents A, charges C, potentials V by equation definition).
(a) Tecplot ASCII (TecplotWriter.cc:622-782), default ostream precision (~6 sig figs; the setprecision(15) at :407 is commented out):
TITLE = "<device>"
VARIABLES = "x"[,"y"][,"z"], "<nodeModel>"... [", VARLOCATION=([k,...])=CELLCENTERED)" appended per ZONE line for element models]
ZONE T="<region>" NODES=<n>, ELEMENTS=<m>, DATAPACKING=BLOCK, ZONETYPE=FELINESEG|FETRIANGLE|FETETRAHEDRON
then one whitespace-separated BLOCK per variable (x, y?, z?, node models, scalar edge models, vector edge models expanded as <name>_x_onNode/_y/_z, cell-centered element models), then 1-based connectivity (edges: 2 ints/line :367; triangles 3 :379; tets 4 :392). Scalar-model name collisions across types warn on stdout (:490,568) and first type wins.
(b) VTK bundle (VTKWriter.cc:30-66,460-560), setprecision(15) scientific for XML scaffolding; arrays binary: <DataArray type="Float64" Name="<model>" [NumberOfComponents="k"] format="binary"> base64(zlib(raw LE doubles)) </DataArray> inside <Points>/<PointData>/<CellData>/<Cells> of <VTKFile type="UnstructuredGrid" ... compressor="vtkZLibDataCompressor">. <file>.vtm = vtkMultiBlockDataSet listing each <file>_<i>.vtu; <file>.visit = "!NBLOCKS <n>" + one vtu path per line. NOT legacy ParaView ASCII (see §3 correction).
(c) devsim restart (DevsimRestartWriter.cc) + devsim_data (DevsimWriter.cc), %.15e scientific (:135). begin_/end_ blocks: begin_device "<dev>" / begin_region "<r>" "<material>" / begin_coordinates (x\ty\tz per line) / begin_nodes (index/line) / begin_edges|triangles|tetrahedra (tab-sep 0-based indices) / begin_node_solution "<name>"|begin_edge_solution "<name>" (one value/line) / begin_contact "<c>" "<region>" "<mat>" + member begin_nodes lists. Restart adds equations/models/interface blocks (:99-162,211-293). Machine grammar = src/meshing/DevsimParser.y + DevsimScanner.l (also load path DevsimLoader.cc); mesh-only schema in GmshParser.y for the gmsh input side.
(d) API shapes: A2 lists are plain Python float lists in node/edge/element index order (SetListAsResult); A5 ai/ap = 0-based CSC (default CCM) or CSR index arrays; A6 iteration maps mirror the stdout log line-for-line.
Real repo examples (no golden .tec/.vtu blobs; goldenresults/ holds only README.txt): testing/mesh2d.py:99-103 write_devices .msh/.tec + include_test callback; testing/mos_2d.py:65,88 vtk + devsim; testing/cap2.py:362,366 print(get_matrix_and_rhs()), get_node_model_values(device,region,"Potential"); examples/diode/*.py + capacitance/cap1d.py show IV/CV loops reading A1/A2 per bias step.

3. PYTHON BINDINGS (audit row: "native Python-scripted TCAD (solve/get_contact_charge/write_devices) | ParaView ASCII + restart" — CONFIRMED with one correction)
Import: `import devsim` (+ `from devsim import <cmd>` per testing/cap2.py:39-40); C-extension module (src/pythonapi/PythonCommands.cc:207-232, moduledef; Interpreter.cc:38), type stubs at dist/__init__.pyi. Returns natively: all of A1-A6 (floats, float/str lists, nested dicts of POD arrays) — nothing requires parsing. CORRECTION: "ParaView ASCII" is wrong for VTK: type='vtk' emits XML VTU (binary payloads) + .vtm + .visit; only type='tecplot' is ASCII (and it is Tecplot BLOCK ASCII, ParaView-readable but not "ParaView ASCII" legacy format). Execution model fits TOOL-OUTPUTS: driver script runs in a subprocess; bindings read results (in that script or a reader pass).

4. STDIO-ONLY RESIDUE: effectively NONE for numeric results. Every numeric stdout line has an API twin: S1 print_* ⟷ A2 get_* (same GetScalarValues source); S2 iteration log ⟷ A6 solve(info=True) maps (PrintIteration/PrintCircuitErrors populate both, Newton.cc:882-910); S3 errors raise catchable exceptions with the message. Residual stdio-only content is cosmetic: iteration-log formatting, "Writing model X as <type>..." collision warnings (TecplotWriter.cc:490,568), "Could not open ..." strings (also returned as exceptions). AC/noise/transient values are retrievable via get_circuit_node_value/get_*_model_values after solve — no scrape needed.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS bindings > structured files > deterministic text)
1) Bindings: run user/devsim script in subprocess; driver calls A1/A2/A4/A5/A6 + solve(info=True) and dumps JSON — full fidelity, zero parsing. 2) VTK bundle: XML + base64/zlib Float64, parseable with stdlib (xml, zlib, base64, struct); filename glob <stem>.vtm + <stem>_*.vtu. 3) devsim/devsim_data restart: exact grammar in DevsimParser.y/DevsimScanner.l but heavier. 4) Tecplot ASCII last (6-sig-fig loss, name-collision coercion). Never scrape S1/S2. Verified at: clone e3a25f08 (2026-10-23) == pin 2.11.2 (provision_toolchain.sh:94, CMakeLists.txt:22, provision-sources.md §14 pip route); DEFER post_mvp-only per audit, so no adapter work until wave 4.
```
