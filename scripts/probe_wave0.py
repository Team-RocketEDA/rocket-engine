"""Wave-0 environment probe (cleanup plan step 1).

Reports whether this machine can do the ticket-wave work: EDA
binaries, venv imports, pymeep env, PDK dirs, uv.lock pins, and
host-only capabilities (fuse/userns/build tools). Reports only —
never installs. Exit 0 when every runnable-here required check
passes; host-only misses are warnings unless --strict.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME_TOOLS = Path.home() / "tools"
BUNDLE_BIN = HOME_TOOLS / "oss-cad-suite" / "bin"


def _check(id, kind, target, required=True, host_only=False, extra=""):
    return {"id": id, "kind": kind, "target": target,
            "required": required, "host_only": host_only, "extra": extra}


CHECKS = (
    # Bundle binaries (oss-cad-suite 20261025).
    [_check(f"bin.{b}", "binary", str(BUNDLE_BIN / b))
     for b in ("yosys", "sby", "eqy", "mcy", "slang", "iverilog", "vvp",
               "verilator", "ghdl")]
    + [_check("bin.slang-flags", "slang_flags", "diag-json,ast-json")]
    # Ambient / provisioned binaries.
    + [_check("bin.magic", "binary", "magic"),
       _check("bin.netgen", "binary", "netgen"),
       _check("bin.ngspice", "binary", "ngspice"),
       _check("bin.xschem", "binary", "xschem"),
       _check("bin.klayout", "binary-klayout",
              str(HOME_TOOLS / "klayout-0.30.12" / "bin" / "klayout")),
       _check("bin.elmer", "binary", "ElmerSolver")]
    # Venv imports (groups synced).
    + [_check(f"py.{m}", "pyimport", m)
       for m in ("sax", "circulax", "meow", "gdsfactory", "kfactory",
                 "pyslang", "pywellen", "vlsirtools", "amaranth",
                 "cace", "devsim", "cocotb")]
    # pymeep env, PDKs.
    + [_check("pymeep.import", "pymeep", "meep"),
       _check("pdk.sky130A", "pdk", "sky130A"),
       _check("pdk.sky130B", "pdk", "sky130B", required=False)]
    # uv.lock pins (repo state, same everywhere).
    + [_check(f"pin.{p}", "pin", p)
       for p in ("sax", "circulax", "meow-sim", "gdsfactory",
                 "pyslang", "pywellen", "vlsirtools", "amaranth",
                 "cace", "devsim")]
    # Host-only capabilities.
    + [_check("cap.fuse", "capability", "fuse",
              required=False, host_only=True),
       _check("cap.userns", "capability", "userns",
              required=False, host_only=True),
       _check("cap.build", "capability", "make,gcc,swig",
              required=False, host_only=True)]
)


def _run(cmd, timeout=60):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr)[:2000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"


def run_check(check):
    cid, kind, target = check["id"], check["kind"], check["target"]
    try:
        if kind == "binary":
            path = target if "/" in target else (shutil.which(target) or "")
            if path and os.access(path, os.X_OK):
                return {"id": cid, "status": "ok", "detail": path}
            return {"id": cid, "status": "missing",
                    "detail": f"not executable: {target}"}
        if kind == "binary-klayout":
            if os.access(target, os.X_OK):
                _, out = _run([target, "-v"])
                first = out.strip().splitlines()[0] if out.strip() else "?"
                return {"id": cid, "status": "ok",
                        "detail": f"{target} [{first}]"}
            return {"id": cid, "status": "missing",
                    "detail": f"not executable: {target}"}
        if kind == "slang_flags":
            slang = str(BUNDLE_BIN / "slang")
            if not os.access(slang, os.X_OK):
                return {"id": cid, "status": "missing",
                        "detail": "slang binary absent"}
            proc = subprocess.run([slang, "--help"], capture_output=True,
                                    text=True, timeout=60)
            out = proc.stdout + proc.stderr
            if "--diag-json" in out and "--ast-json" in out:
                return {"id": cid, "status": "ok",
                        "detail": "--diag-json + --ast-json present"}
            return {"id": cid, "status": "missing",
                    "detail": "slang lacks --diag-json/--ast-json"}
        if kind == "pyimport":
            code, _ = _run([sys.executable, "-c", f"import {target}"])
            if code == 0:
                return {"id": cid, "status": "ok",
                        "detail": f"import {target} ok"}
            return {"id": cid, "status": "missing",
                    "detail": f"import {target} failed"}
        if kind == "pymeep":
            py = (HOME_TOOLS / "miniforge3" / "envs" / "pymeep" /
                  "bin" / "python")
            if not py.exists():
                return {"id": cid, "status": "missing",
                        "detail": f"no env: {py}"}
            env = dict(os.environ, MPLCONFIGDIR="/tmp")
            proc = subprocess.run(
                [str(py), "-c", "import meep; print('pymeep ok')"],
                capture_output=True, text=True, timeout=120, env=env)
            if "pymeep ok" in proc.stdout:
                return {"id": cid, "status": "ok", "detail": str(py)}
            return {"id": cid, "status": "missing",
                    "detail": (proc.stdout + proc.stderr)[-300:] or
                    "import meep failed"}
        if kind == "pdk":
            d = Path.home() / ".local" / "share" / "pdk" / target
            if d.is_dir():
                return {"id": cid, "status": "ok", "detail": str(d)}
            return {"id": cid, "status": "missing",
                    "detail": f"no dir: {d}"}
        if kind == "pin":
            lock = ROOT / "uv.lock"
            if lock.exists() and f'name = "{target}"' in lock.read_text():
                return {"id": cid, "status": "ok",
                        "detail": f"{target} in uv.lock"}
            return {"id": cid, "status": "missing",
                    "detail": f"{target} not in uv.lock"}
        if kind == "capability":
            if target == "fuse":
                if Path("/dev/fuse").exists():
                    return {"id": cid, "status": "ok",
                            "detail": "/dev/fuse present"}
                return {"id": cid, "status": "host-only",
                        "detail": "no /dev/fuse here (LibreLane runs on host)"}
            if target == "userns":
                bwrap = shutil.which("bwrap")
                if not bwrap:
                    return {"id": cid, "status": "host-only",
                            "detail": "no bwrap here (sandbox tests on host)"}
                code, _ = _run([bwrap, "--unshare-user-try",
                                "--ro-bind", "/", "/", "true"])
                if code == 0:
                    return {"id": cid, "status": "ok",
                            "detail": "userns works"}
                return {"id": cid, "status": "host-only",
                        "detail": "userns restricted here (sandbox tests on host)"}
            missing = [t for t in target.split(",")
                       if not shutil.which(t)]
            if not missing:
                return {"id": cid, "status": "ok",
                        "detail": "make+gcc+swig present"}
            return {"id": cid, "status": "host-only",
                    "detail": f"missing here: {','.join(missing)} "
                    "(source builds on host)"}
    except Exception as exc:  # never crash the probe
        return {"id": cid, "status": "missing",
                "detail": f"probe error: {exc}"}
    return {"id": cid, "status": "missing",
            "detail": f"unknown kind: {kind}"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="host-only misses also fail")
    args = parser.parse_args(argv)
    rows = [run_check(c) for c in CHECKS]
    by_id = {c["id"]: c for c in CHECKS}
    missing_required = sum(
        1 for r in rows
        if r["status"] == "missing" and by_id[r["id"]]["required"])
    host_only = sum(1 for r in rows if r["status"] == "host-only")
    summary = {"total": len(rows),
               "missing_required": missing_required,
               "host_only": host_only}
    if args.json:
        print(json.dumps({"checks": rows, "summary": summary}, indent=1))
    else:
        print(f"{'CHECK':24} {'STATUS':10} DETAIL")
        for r in rows:
            flag = "" if r["status"] == "ok" else (
                " [HOST-ONLY]" if r["status"] == "host-only" else " *")
            print(f"{r['id']:24} {r['status']:10} {r['detail']}{flag}")
        print(f"\n{summary['total']} checks, "
              f"{missing_required} missing-required, "
              f"{host_only} host-only")
    failed = missing_required > 0 or (args.strict and host_only > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
