# kfactory — output dissection

Dissector ref: prior result 16 (text `handoff-7d18ab755100c25b04ba5d34bbc0504f7536c68ee40201711c19c902cf5e6cfe-6bf4e036456253b169c69446f97f8c68b2c8e91d085b5991d0213370214f8d91.txt`, summary `handoff-ff4ec9eddc539d2b4d37098a08dae75f5c58baa16a1e5bdbbfa8cc1d13c76489-6bf4e036456253b169c69446f97f8c68b2c8e91d085b5991d0213370214f8d91.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `380796e9b38d8461869cc3e8e93d0f5aa3ff8c1c`
- Clone date: `2026-10-23`
- Pin: CLONE: /tmp/rocket-tool-src/kfactory @ SHA 380796e9b38d8461869cc3e8e93d0f5aa3ff8c1c, date 2026-10-23. pyproject version 3.5.0 (pyproject.toml:7,208). Deps: klayout>=0.30.12,<0.31 (pyproject.toml:24), kfnetlist>=0.3 (pyproject.toml:23). Pin evidence: PyPI kfactory 3.5.0 requires_dist matches (https:/
- Doc/source URLs:
  - https://gdsfactory.github.io/kfactory/latest/
  - https://pypi.org/pypi/kfactory/json

### Dissector header (verbatim, whitespace-trimmed)

```text
kfactory OUTPUT DISSECTION (review-only)

CLONE: /tmp/rocket-tool-src/kfactory @ SHA 380796e9b38d8461869cc3e8e93d0f5aa3ff8c1c, date 2026-10-23. pyproject version 3.5.0 (pyproject.toml:7,208). Deps: klayout>=0.30.12,<0.31 (pyproject.toml:24), kfnetlist>=0.3 (pyproject.toml:23). Pin evidence: PyPI kfactory 3.5.0 requires_dist matches (https://pypi.org/pypi/kfactory/json). Audit row said "3.0.4 locked (transitive), klayout>=0.30.9" — STALE: clone is 3.5.0, floor is now 0.30.12. Satisfied by provision KLAYOUT_PIN=0.30.12 (provision_toolchain.sh:70-72). DOCS: /tmp/rocket-tool-docs/kfactory-index.html is a 374-byte redirect stub -> fell back to upstream https://gdsfactory.github.io/kfactory/latest/ (+ /schematics/netlist/, /utilities/session_cache/).

kfactory is a pure Python library on the KLayout C++ engine (import klayout.db as kdb, lay, rdb in __init__.py:11-13). There is no batch-report mode; every result channel is an API call or a file the API writes.
```

## 1. Result channels

1. RESULT CHANNELS

| # | Channel | Producing call/flag | Filename pattern | Kind |
|---|---|---|---|---|
| F1 | GDSII/OASIS layout file | KCell.write / KCLayout.write / DKCell.write / VKCell.write (kcell.py:1428, layout.py:2559, kcell.py:3630); format auto from extension via set_format_from_filename | caller-chosen; CLI: build/mask/<cell>.{oas,gds,gds.gz}, <lib>.{oas,...}, <cell>_STATIC.<sfx>, <cell>_NOCONT.<sfx> (cli/build.py) | file |
| F2 | GDS bytes in memory | KCell.write_bytes / KCLayout.write_bytes -> bytes (kcell.py:1491, layout.py:2632) | n/a (OASIS bytes) | API return |
| F3 | LayoutToNetlist object (.l2n-serializable) | KCell.l2n_ports / l2n_elec -> kdb.LayoutToNetlist (kcell.py:2181,2225); show() accepts .l2n files (kcell.py:3761) | caller-chosen *.l2n via kdb API | API return |
| F4 | Netlist dict + JSON | KCell.netlist() -> dict[str, kfnetlist.Netlist] (kcell.py:2255); Netlist.to_json() -> str; get_optical_nets -> list[Net] (kcell.py:2284) | caller-chosen *.json | API return/file |
| F5 | Schematic JSON/YAML | TSchematic pydantic model_dump_json / YAML round-trip; kf.read_schematic(path, unit) (schematic.py:3073); from_pic_yml (schematic.py:2329) | caller-chosen *.yaml/*.json (pic.yml style) | API return/file |
| F6 | KCell YAML (geometry dump) | TKCell.to_yaml/from_yaml ruamel representer (kcell.py:3237, ~3200) | caller-chosen *.yaml | API return/file |
| F7 | Report DB (DRC/connectivity) | KCell.connectivity_check -> rdb.ReportDatabase (kcell.py:2497); checks.port_mismatch_check / dangling_ports_check / instance_overlap_check / shape_instance_overlap_check (checks.py:259,602,715,774); persist via klayout rdb.ReportDatabase.save | caller-chosen *.lyrdb/*.rdb | API return/file |
| F8 | Region (DRC-fix residue) | utils/violations.fix_spacing_*_tiled -> kdb.Region (utils/violations.py) | n/a | API return |
| F9 | XOR diff cell | utils/difftest.xor(old,new) -> DKCell (+ raises GeometryDifferenceError) (utils/difftest.py:20) | n/a | API return/exc |
| F10 | Session cache dir | kf.save_session(cell?, session_dir) (session_cache.py:90; exported __init__.py:56) | <session>/<kcl>/cells.gds.gz + factories.pkl + cross_sections.pkl + asymmetrical_cross_sections.pkl + ../kcl_dependencies.json | files |
| F11 | show/plot side effects | kf.show(...)->None via klive socket + temp OAS/GDS (kcell.py:3761); KCell.plot/show (kcell.py:1004,1043,3462,3498) via KLive/matplotlib | temp files (deleted), no stable names | socket/GUI |
| S1 | stdout/stderr logs | loguru logger (conf.py:20) + rich console (conf.py:243): logger.{debug,warning,critical} e.g. cli/build.py, session_cache.py; *.print() helpers (port.py:766, ports/pins/instances print()) | n/a | stdio |
| S2 | CLI stdout/exit | `kf` entry (pyproject scripts.kf=kfactory.cli:app, cli/__init__.py:13): `kf build <file.py::func> [-o DIR] [--suffix oas|gds|gds.gz] [--write-static] [--write-nocontext] [--no-show]`; `kf show <file>`; `--version` | (writes F1) | stdio+files |
| DB | none | no database channel | — | — |

## 2. Format grammars

2. FORMAT GRAMMARS

G1 GDSII/OASIS (F1/F2/F10 cells.gds.gz). Writer is KLayout kdb (Cell.write/Layout.write_bytes); kfactory only sets options via save_layout_options() (utilities.py:41): write_context_info, gds2_write_cell_properties/file_properties/timestamps, max_cellname_length (CLI default 99), multi_xy_records, max_vertex_count (CLI default 4000), all from kf.config. Embedded metadata = KLayout LayoutMetaInfo records (GDS context-info properties; OASIS equivalent), written by KCell.set_meta_data (kcell.py:1791) when write(set_meta_data=True, default): keys `kfactory:ports:{i}` {name, cross_section, trans|dcplx_trans, port_type, info}, `kfactory:pins:{i}` {name, pin_type, info, ports:[idx]}, `kfactory:settings`, `kfactory:info`, `kfactory:settings_units`, `kfactory:function_name`, `kfactory:basename`, `kfactory:instance_infos` (name->Info dict). Read back by get_meta_data, meta_format v1/v2/v3 (kcell.py:1882). Units: dbu integers in KCell, um floats in DKCell; dbu from KCLayout.dbu. Duplicate cell names -> DuplicateCellNameError unless deduplicate_cell_names=True (auto `$1` suffixes). Test: tests/test_write.py:20-45 (kcl.write(tmp/out.gds), write_bytes() nonempty).

G2 Netlist JSON (F4). kfnetlist.Netlist: {instances: {inst: {kcl, component, settings:{...}}}, nets: [[{instance,port},...]], ports: [...]}. Real doc example (https://gdsfactory.github.io/kfactory/latest/schematics/netlist/ "Netlist as JSON"): `{"instances":{"s1":{"kcl":"SCHEM_NETLIST","component":"straight","settings":{"length":15000,"width":500}},...},"nets":[[{"instance":"s1","port":"o1"},{"instance":"x1","port":"o1"}],...],"ports":[]}`. Settings values in dbu ints here (length 15000 = 15um @1nm dbu). KCell.netlist() returns dict keyed by cell name; Netlist has .instances/.nets/.ports; MUST call nl.sort() before == or to_json for run-stable ordering (nets/port order varies run to run). kfnetlist>=0.3 external pkg (not vendored; not installed here — grammar from docs + kcell.py:2270-2282 call site).

G3 Schematic JSON/YAML (F5). Pydantic TSchematic; top-level keys: ['name','instances','placements','nets','routes','ports','pins','constraints','unit','info'] (doc example). Placement: {'mirror':False,'x':0,'dx':0,'y':0,'dy':0,'orientation':0.0,'anchor':None} in dbu (DSchematic uses um floats). YAML = model_dump_json payload minus 'unit', loaded by kf.read_schematic(path, unit='dbu'|'um') -> Schematic|DSchematic (schematic.py:3073-3096) via from_pic_yml (accepts legacy pic.yml keys connections/port-placements; strict=True for dbu). KNOWN UPSTREAM BUG (docs): model_dump_json nets serialize as nested arrays but read validator expects {p1,p2} -> round-trip raises KeyError 'p1' when nets present. Schema source: schematic.py classes Placement/MirrorPlacement/Array/SchematicInstance (lines 131-411+).

G4 KCell YAML geometry (F6). to_yaml (kcell.py:3237): {name, insts:[{cellname, trans:"<kdb Trans.to_s()>"}], shapes:{"<LayerInfo.to_s()>": ["<ShapeType> <shape.to_s()>", ...]}, ports:[{name, layer:[layer,datatype], port_type, ...}]}. from_yaml parses "shapetype shapestring" split on first space (kcell.py:~3225). Test: tests/test_yaml.py (mmi body/ports/tapers).

G5 Report DB .lyrdb/.rdb XML (F7). KLayout rdb.ReportDatabase (XML schema owned by klayout, not in this repo). connectivity_check creates db named f"Connectivity Check {cell.name}" (kcell.py:2530), one RdbCell per cell, per-layer categories with subcategories: WidthMismatch, AngleMismatch, TypeMismatch, CrossSectionMismatch (opt-in), PortOverlap, MissingPhysicalShape, PartialPhysicalShape, CellPorts (opt-in annotation), plus dangling-port and overlap categories (checks.py:259-398). Pass/fail = item count per category (zero items = pass); no verdict string. Persist with db.save(path) (klayout API).

G6 LayoutToNetlist/.l2n (F3). KLayout binary/serializable netlist DB; kfactory builds circuits via KCell.circuit(l2n,...) (kcell.py:2306). Grammar = klayout's; extract via l2n.netlist() in-process. Optical (port-adjacency, default port_types=("optical",)) vs electrical (layer-connectivity tuples, l2n_elec mark_port_types=("electrical","RF","DC")).

G7 Session cache (F10). <session>/<kcl>/cells.gds.gz (subset-written, clear_cells+add_this_cell, factory cells only), factories.pkl (FunctionPickler: {factory_key: [dependents, [(hashkey,cellname)], file, filehash]}), cross_sections.pkl / asymmetrical_cross_sections.pkl (plain pickle of name->XS), kcl_dependencies.json {kcl:[lib,...]} (session_cache.py:90-174). Pickles are NOT a stable interchange grammar (version-coupled).

## 3. Python bindings verdict

3. PYTHON BINDINGS (confirm audit row: CONFIRMED + corrected)

Audit row "NATIVE Python on KLayout engine, KCell/DKCell, kdb.Region; GDS/OASIS, KEEP-BINDINGS" is correct but understated. Import path: `import kfactory as kf` (+ `from kfactory import kdb, rdb, lay` re-exported klayout modules). Natively returned results (no parsing): KCell/DKCell/VKCell objects, kdb.Region/Polygon/LayoutToNetlist, rdb.ReportDatabase, kfnetlist Netlist/Net dicts, pydantic Schematic/Settings/Info models, bytes (write_bytes), JSON strings (Netlist.to_json, model_dump_json). CORRECTIONS: (a) version is 3.5.0, not 3.0.4; (b) klayout floor is >=0.30.12 (not >=0.30.9) — still satisfied by KLAYOUT_PIN 0.30.12; (c) LVS exists as netlist equality + l2n, no dedicated lvs() report writer (only lvs_equivalent_ports attr, kcell.py:2614; merge.py compare is test-helper).

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE

Essentially none as a designed channel. S1/S2 carry only: loguru diagnostics (levels; critical on missing file/func in cli/build.py), rich pretty-prints (*.print(), console tables) which duplicate in-memory objects, `kf --version`, and difftest/geometry log noise. No verdict, netlist, or report exists solely on stdio — every check returns an object (rdb/Region/Netlist/bool) and every writer takes an explicit path. show()/plot() are GUI/socket side effects (klive), not extractable text. show() temp-file names are unstable (delete-on-close). So: stdio residue = logs/pretty-print only; nothing requiring a text grammar.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)

Verified at: clone 380796e9 (2026-10-23), v3.5.0, klayout>=0.30.12, kfnetlist>=0.3.
1. (bindings) Drive via subprocess `python -c`/`kf build` writing artifacts, then READ in-process: KCell.netlist()[name].sort().to_json() for connectivity/LVS-equality; connectivity_check() item counts for DRC-ish port checks; settings/info/model_dump for params. Deterministic after sort().
2. (structured files) GDS/OASIS + embedded kfactory:* meta (G1) re-read via kfactory/klayout; .lyrdb via klayout.rdb; schematic/netlist YAML/JSON (G3/G4/G2) with the nets round-trip bug noted.
3. (text) Nothing — no text grammar needed; treat stdout as logs.
CAVEATS: G7 pickles are cache-only (never parse); LVS-vs-schematic = Netlist == comparison (call .sort() first); .lyrdb XML schema lives in klayout repo, categories listed in G5.

## Weak-evidence gaps (flagged by dissector)

- | F7 | Report DB (DRC/connectivity) | KCell.connectivity_check -> rdb.ReportDatabase (kcell.py:2497); checks.port_mismatch_check / dangling_ports_check / instance_overlap_check / shape_instance_overlap_check (checks.py:259,602,715,774); persist via klayout rdb
- | S1 | stdout/stderr logs | loguru logger (conf.py:20) + rich console (conf.py:243): logger.{debug,warning,critical} e.g. cli/build.py, session_cache.py; *.print() helpers (port.py:766, ports/pins/instances print()) | n/a | stdio |
- G3 Schematic JSON/YAML (F5). Pydantic TSchematic; top-level keys: ['name','instances','placements','nets','routes','ports','pins','constraints','unit','info'] (doc example). Placement: {'mirror':False,'x':0,'dx':0,'y':0,'dy':0,'orientation':0.0,'anchor':None}
- G5 Report DB .lyrdb/.rdb XML (F7). KLayout rdb.ReportDatabase (XML schema owned by klayout, not in this repo). connectivity_check creates db named f"Connectivity Check {cell.name}" (kcell.py:2530), one RdbCell per cell, per-layer categories with subcategories:
- 2. (structured files) GDS/OASIS + embedded kfactory:* meta (G1) re-read via kfactory/klayout; .lyrdb via klayout.rdb; schematic/netlist YAML/JSON (G3/G4/G2) with the nets round-trip bug noted.
- CLONE: /tmp/rocket-tool-src/kfactory @ SHA 380796e9b38d8461869cc3e8e93d0f5aa3ff8c1c, date 2026-10-23. pyproject version 3.5.0 (pyproject.toml:7,208). Deps: klayout>=0.30.12,<0.31 (pyproject.toml:24), kfnetlist>=0.3 (pyproject.toml:23). Pin evidence: PyPI kfact

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
kfactory OUTPUT DISSECTION (review-only)

CLONE: /tmp/rocket-tool-src/kfactory @ SHA 380796e9b38d8461869cc3e8e93d0f5aa3ff8c1c, date 2026-10-23. pyproject version 3.5.0 (pyproject.toml:7,208). Deps: klayout>=0.30.12,<0.31 (pyproject.toml:24), kfnetlist>=0.3 (pyproject.toml:23). Pin evidence: PyPI kfactory 3.5.0 requires_dist matches (https://pypi.org/pypi/kfactory/json). Audit row said "3.0.4 locked (transitive), klayout>=0.30.9" — STALE: clone is 3.5.0, floor is now 0.30.12. Satisfied by provision KLAYOUT_PIN=0.30.12 (provision_toolchain.sh:70-72). DOCS: /tmp/rocket-tool-docs/kfactory-index.html is a 374-byte redirect stub -> fell back to upstream https://gdsfactory.github.io/kfactory/latest/ (+ /schematics/netlist/, /utilities/session_cache/).

kfactory is a pure Python library on the KLayout C++ engine (import klayout.db as kdb, lay, rdb in __init__.py:11-13). There is no batch-report mode; every result channel is an API call or a file the API writes.

1. RESULT CHANNELS

| # | Channel | Producing call/flag | Filename pattern | Kind |
|---|---|---|---|---|
| F1 | GDSII/OASIS layout file | KCell.write / KCLayout.write / DKCell.write / VKCell.write (kcell.py:1428, layout.py:2559, kcell.py:3630); format auto from extension via set_format_from_filename | caller-chosen; CLI: build/mask/<cell>.{oas,gds,gds.gz}, <lib>.{oas,...}, <cell>_STATIC.<sfx>, <cell>_NOCONT.<sfx> (cli/build.py) | file |
| F2 | GDS bytes in memory | KCell.write_bytes / KCLayout.write_bytes -> bytes (kcell.py:1491, layout.py:2632) | n/a (OASIS bytes) | API return |
| F3 | LayoutToNetlist object (.l2n-serializable) | KCell.l2n_ports / l2n_elec -> kdb.LayoutToNetlist (kcell.py:2181,2225); show() accepts .l2n files (kcell.py:3761) | caller-chosen *.l2n via kdb API | API return |
| F4 | Netlist dict + JSON | KCell.netlist() -> dict[str, kfnetlist.Netlist] (kcell.py:2255); Netlist.to_json() -> str; get_optical_nets -> list[Net] (kcell.py:2284) | caller-chosen *.json | API return/file |
| F5 | Schematic JSON/YAML | TSchematic pydantic model_dump_json / YAML round-trip; kf.read_schematic(path, unit) (schematic.py:3073); from_pic_yml (schematic.py:2329) | caller-chosen *.yaml/*.json (pic.yml style) | API return/file |
| F6 | KCell YAML (geometry dump) | TKCell.to_yaml/from_yaml ruamel representer (kcell.py:3237, ~3200) | caller-chosen *.yaml | API return/file |
| F7 | Report DB (DRC/connectivity) | KCell.connectivity_check -> rdb.ReportDatabase (kcell.py:2497); checks.port_mismatch_check / dangling_ports_check / instance_overlap_check / shape_instance_overlap_check (checks.py:259,602,715,774); persist via klayout rdb.ReportDatabase.save | caller-chosen *.lyrdb/*.rdb | API return/file |
| F8 | Region (DRC-fix residue) | utils/violations.fix_spacing_*_tiled -> kdb.Region (utils/violations.py) | n/a | API return |
| F9 | XOR diff cell | utils/difftest.xor(old,new) -> DKCell (+ raises GeometryDifferenceError) (utils/difftest.py:20) | n/a | API return/exc |
| F10 | Session cache dir | kf.save_session(cell?, session_dir) (session_cache.py:90; exported __init__.py:56) | <session>/<kcl>/cells.gds.gz + factories.pkl + cross_sections.pkl + asymmetrical_cross_sections.pkl + ../kcl_dependencies.json | files |
| F11 | show/plot side effects | kf.show(...)->None via klive socket + temp OAS/GDS (kcell.py:3761); KCell.plot/show (kcell.py:1004,1043,3462,3498) via KLive/matplotlib | temp files (deleted), no stable names | socket/GUI |
| S1 | stdout/stderr logs | loguru logger (conf.py:20) + rich console (conf.py:243): logger.{debug,warning,critical} e.g. cli/build.py, session_cache.py; *.print() helpers (port.py:766, ports/pins/instances print()) | n/a | stdio |
| S2 | CLI stdout/exit | `kf` entry (pyproject scripts.kf=kfactory.cli:app, cli/__init__.py:13): `kf build <file.py::func> [-o DIR] [--suffix oas|gds|gds.gz] [--write-static] [--write-nocontext] [--no-show]`; `kf show <file>`; `--version` | (writes F1) | stdio+files |
| DB | none | no database channel | — | — |

2. FORMAT GRAMMARS

G1 GDSII/OASIS (F1/F2/F10 cells.gds.gz). Writer is KLayout kdb (Cell.write/Layout.write_bytes); kfactory only sets options via save_layout_options() (utilities.py:41): write_context_info, gds2_write_cell_properties/file_properties/timestamps, max_cellname_length (CLI default 99), multi_xy_records, max_vertex_count (CLI default 4000), all from kf.config. Embedded metadata = KLayout LayoutMetaInfo records (GDS context-info properties; OASIS equivalent), written by KCell.set_meta_data (kcell.py:1791) when write(set_meta_data=True, default): keys `kfactory:ports:{i}` {name, cross_section, trans|dcplx_trans, port_type, info}, `kfactory:pins:{i}` {name, pin_type, info, ports:[idx]}, `kfactory:settings`, `kfactory:info`, `kfactory:settings_units`, `kfactory:function_name`, `kfactory:basename`, `kfactory:instance_infos` (name->Info dict). Read back by get_meta_data, meta_format v1/v2/v3 (kcell.py:1882). Units: dbu integers in KCell, um floats in DKCell; dbu from KCLayout.dbu. Duplicate cell names -> DuplicateCellNameError unless deduplicate_cell_names=True (auto `$1` suffixes). Test: tests/test_write.py:20-45 (kcl.write(tmp/out.gds), write_bytes() nonempty).

G2 Netlist JSON (F4). kfnetlist.Netlist: {instances: {inst: {kcl, component, settings:{...}}}, nets: [[{instance,port},...]], ports: [...]}. Real doc example (https://gdsfactory.github.io/kfactory/latest/schematics/netlist/ "Netlist as JSON"): `{"instances":{"s1":{"kcl":"SCHEM_NETLIST","component":"straight","settings":{"length":15000,"width":500}},...},"nets":[[{"instance":"s1","port":"o1"},{"instance":"x1","port":"o1"}],...],"ports":[]}`. Settings values in dbu ints here (length 15000 = 15um @1nm dbu). KCell.netlist() returns dict keyed by cell name; Netlist has .instances/.nets/.ports; MUST call nl.sort() before == or to_json for run-stable ordering (nets/port order varies run to run). kfnetlist>=0.3 external pkg (not vendored; not installed here — grammar from docs + kcell.py:2270-2282 call site).

G3 Schematic JSON/YAML (F5). Pydantic TSchematic; top-level keys: ['name','instances','placements','nets','routes','ports','pins','constraints','unit','info'] (doc example). Placement: {'mirror':False,'x':0,'dx':0,'y':0,'dy':0,'orientation':0.0,'anchor':None} in dbu (DSchematic uses um floats). YAML = model_dump_json payload minus 'unit', loaded by kf.read_schematic(path, unit='dbu'|'um') -> Schematic|DSchematic (schematic.py:3073-3096) via from_pic_yml (accepts legacy pic.yml keys connections/port-placements; strict=True for dbu). KNOWN UPSTREAM BUG (docs): model_dump_json nets serialize as nested arrays but read validator expects {p1,p2} -> round-trip raises KeyError 'p1' when nets present. Schema source: schematic.py classes Placement/MirrorPlacement/Array/SchematicInstance (lines 131-411+).

G4 KCell YAML geometry (F6). to_yaml (kcell.py:3237): {name, insts:[{cellname, trans:"<kdb Trans.to_s()>"}], shapes:{"<LayerInfo.to_s()>": ["<ShapeType> <shape.to_s()>", ...]}, ports:[{name, layer:[layer,datatype], port_type, ...}]}. from_yaml parses "shapetype shapestring" split on first space (kcell.py:~3225). Test: tests/test_yaml.py (mmi body/ports/tapers).

G5 Report DB .lyrdb/.rdb XML (F7). KLayout rdb.ReportDatabase (XML schema owned by klayout, not in this repo). connectivity_check creates db named f"Connectivity Check {cell.name}" (kcell.py:2530), one RdbCell per cell, per-layer categories with subcategories: WidthMismatch, AngleMismatch, TypeMismatch, CrossSectionMismatch (opt-in), PortOverlap, MissingPhysicalShape, PartialPhysicalShape, CellPorts (opt-in annotation), plus dangling-port and overlap categories (checks.py:259-398). Pass/fail = item count per category (zero items = pass); no verdict string. Persist with db.save(path) (klayout API).

G6 LayoutToNetlist/.l2n (F3). KLayout binary/serializable netlist DB; kfactory builds circuits via KCell.circuit(l2n,...) (kcell.py:2306). Grammar = klayout's; extract via l2n.netlist() in-process. Optical (port-adjacency, default port_types=("optical",)) vs electrical (layer-connectivity tuples, l2n_elec mark_port_types=("electrical","RF","DC")).

G7 Session cache (F10). <session>/<kcl>/cells.gds.gz (subset-written, clear_cells+add_this_cell, factory cells only), factories.pkl (FunctionPickler: {factory_key: [dependents, [(hashkey,cellname)], file, filehash]}), cross_sections.pkl / asymmetrical_cross_sections.pkl (plain pickle of name->XS), kcl_dependencies.json {kcl:[lib,...]} (session_cache.py:90-174). Pickles are NOT a stable interchange grammar (version-coupled).

3. PYTHON BINDINGS (confirm audit row: CONFIRMED + corrected)

Audit row "NATIVE Python on KLayout engine, KCell/DKCell, kdb.Region; GDS/OASIS, KEEP-BINDINGS" is correct but understated. Import path: `import kfactory as kf` (+ `from kfactory import kdb, rdb, lay` re-exported klayout modules). Natively returned results (no parsing): KCell/DKCell/VKCell objects, kdb.Region/Polygon/LayoutToNetlist, rdb.ReportDatabase, kfnetlist Netlist/Net dicts, pydantic Schematic/Settings/Info models, bytes (write_bytes), JSON strings (Netlist.to_json, model_dump_json). CORRECTIONS: (a) version is 3.5.0, not 3.0.4; (b) klayout floor is >=0.30.12 (not >=0.30.9) — still satisfied by KLAYOUT_PIN 0.30.12; (c) LVS exists as netlist equality + l2n, no dedicated lvs() report writer (only lvs_equivalent_ports attr, kcell.py:2614; merge.py compare is test-helper).

4. STDIO-ONLY RESIDUE

Essentially none as a designed channel. S1/S2 carry only: loguru diagnostics (levels; critical on missing file/func in cli/build.py), rich pretty-prints (*.print(), console tables) which duplicate in-memory objects, `kf --version`, and difftest/geometry log noise. No verdict, netlist, or report exists solely on stdio — every check returns an object (rdb/Region/Netlist/bool) and every writer takes an explicit path. show()/plot() are GUI/socket side effects (klive), not extractable text. show() temp-file names are unstable (delete-on-close). So: stdio residue = logs/pretty-print only; nothing requiring a text grammar.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)

Verified at: clone 380796e9 (2026-10-23), v3.5.0, klayout>=0.30.12, kfnetlist>=0.3.
1. (bindings) Drive via subprocess `python -c`/`kf build` writing artifacts, then READ in-process: KCell.netlist()[name].sort().to_json() for connectivity/LVS-equality; connectivity_check() item counts for DRC-ish port checks; settings/info/model_dump for params. Deterministic after sort().
2. (structured files) GDS/OASIS + embedded kfactory:* meta (G1) re-read via kfactory/klayout; .lyrdb via klayout.rdb; schematic/netlist YAML/JSON (G3/G4/G2) with the nets round-trip bug noted.
3. (text) Nothing — no text grammar needed; treat stdout as logs.
CAVEATS: G7 pickles are cache-only (never parse); LVS-vs-schematic = Netlist == comparison (call .sort() first); .lyrdb XML schema lives in klayout repo, categories listed in G5.
```
