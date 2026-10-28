"""Bubblewrap isolation runner (I16): confine solver subprocesses.

Profiles are data: namespaces, ro binds, symlinks, tmpfs mounts, env.
The workdir is always bound read-write at /work. Preflight proves the
profile on a trivial command before any real work runs; unprovable
profiles refuse loudly instead of degrading silently. See
docs/probe-bwrap-isolation.md for the verified recipe and the
environment limits found while probing.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from .errors import ExecutionError


class BwrapRunner:
    def __init__(self, profile, binary="bwrap"):
        self._profile = dict(profile)
        self._binary = binary

    def _resolve(self):
        found = shutil.which(self._binary)
        if found is not None:
            return found
        if Path(self._binary).is_file():
            return self._binary
        raise ExecutionError(
            "missing_dependency", f"bwrap not found: {self._binary}."
        )

    def _argv(self, binary, workdir, command):
        argv = [binary]
        for ns in self._profile.get("namespaces", ["user"]):
            argv.append(f"--unshare-{ns}")
        argv.append("--die-with-parent")
        for src, dest in self._profile.get("binds_ro", []):
            argv += ["--ro-bind", src, dest]
        for src, dest in self._profile.get("symlinks", []):
            argv += ["--symlink", src, dest]
        for path in self._profile.get("tmpfs", []):
            argv += ["--tmpfs", path]
        argv += ["--bind", str(workdir), "/work"]
        for key, value in self._profile.get("env", {}).items():
            argv += ["--setenv", key, value]
        argv += ["--chdir", "/work", *command]
        return argv

    def preflight(self, timeout_s=30):
        binary = self._resolve()
        with tempfile.TemporaryDirectory(prefix="bwrap_probe_") as tmp:
            try:
                proc = subprocess.run(
                    self._argv(binary, tmp, ["/bin/true"]),
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired as exc:
                raise ExecutionError(
                    "runner_unavailable", "bwrap probe timed out."
                ) from exc
        if proc.returncode != 0:
            lines = (proc.stderr or "").strip().splitlines()
            detail = lines[0] if lines else f"exit {proc.returncode}"
            raise ExecutionError(
                "runner_unavailable", f"bwrap probe failed: {detail}."
            )
        return {"ready": True, "binary": binary}

    def run(self, command, workdir, timeout_s=120):
        binary = self._resolve()
        if not Path(workdir).is_dir():
            raise ExecutionError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        try:
            return subprocess.run(
                self._argv(binary, workdir, command),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionError(
                "runner_unavailable",
                f"Sandboxed run timed out after {timeout_s}s.",
            ) from exc
