"""Bubblewrap isolation runner (I16): confine solver subprocesses.

Profiles are data: namespaces, ro binds, symlinks, tmpfs mounts, env.
The workdir is always bound read-write at its own host path, so both
absolute and relative argv work unchanged inside. Preflight proves the
profile on a trivial command before any real work runs; unprovable
profiles refuse loudly instead of degrading silently. See
docs/probe-bwrap-isolation.md for the verified recipe and the
environment limits found while probing.

Profiles also carry `env_unset` (emitted as `--unsetenv`): bwrap
inherits the caller's environment except where told otherwise, so a
host DISPLAY would leak into the sandbox and abort display-sensitive
tools (netgen's Tk init). Default profiles scrub it.
"""

import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from .errors import ExecutionError

_SYSTEM_BINDS_RO = [("/usr", "/usr"), ("/etc", "/etc"), ("/proc", "/proc")]
_SYSTEM_SYMLINKS = [
    ("usr/bin", "/bin"),
    ("usr/sbin", "/sbin"),
    ("usr/lib", "/lib"),
    ("usr/lib64", "/lib64"),
]


def tool_roots(tool_paths):
    """Read-only roots covering resolved tool binaries.

    A tool under `*/bin/` binds its grandparent (the suite root);
    anywhere else binds its parent directory. Deduped, order kept.
    """
    roots = []
    for path in tool_paths:
        parent = Path(path).parent
        root = str(parent.parent if parent.name == "bin" else parent)
        if root not in [str(r) for r, _ in roots]:
            roots.append((root, root))
    return roots


def default_profile(tool_paths=()):
    """Sandbox profile from the verified probe recipe, plus tool roots."""
    return {
        "namespaces": ["user"],
        "binds_ro": list(_SYSTEM_BINDS_RO) + tool_roots(tool_paths),
        "symlinks": list(_SYSTEM_SYMLINKS),
        "tmpfs": ["/tmp"],
        "env": {"PATH": "/usr/bin:/bin", "TMPDIR": "/tmp"},
        "env_unset": ["DISPLAY"],
    }


_OUTPUT_LIMIT_BYTES = 1 << 20  # per stream; deployment may lower, never raise
_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_BAD_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_stream(data):
    """Decode, strip terminal/control bytes, bound length with a marker.

    Truncation counts exact input bytes; a split multibyte tail decodes
    as U+FFFD, which the marker line explains by construction.
    """
    total = len(data)
    text = data[:_OUTPUT_LIMIT_BYTES].decode("utf-8", "replace")
    text = _CSI_RE.sub("", text)
    text = _BAD_CHARS_RE.sub("", text)
    if total > _OUTPUT_LIMIT_BYTES:
        text += f"\n...[truncated after {_OUTPUT_LIMIT_BYTES} of {total} bytes]\n"
    return text


_clean_stream = clean_stream


def _kill_tree(proc):
    """SIGKILL one spawned process group, then reap the leader.

    Every sandboxed spawn leads its own session (start_new_session),
    so the group kill reaches grandchildren the leader already
    orphaned. Missing-group errors mean everyone already exited.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass
    proc.wait()


def pgid_survivors(pgid):
    """Pids still in one process group (Linux /proc scan).

    Excludes this process. Used to CONFIRM a tree kill, never to
    select new victims: kill by group first, then scan.
    """
    me = os.getpid()
    found = []
    procfs = Path("/proc")
    if not procfs.is_dir():
        return found
    for entry in procfs.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            group = int(stat.rsplit(")", 1)[1].split()[2])
        except (IndexError, ValueError):
            continue
        if group == pgid:
            found.append(int(entry.name))
    return found


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

    def _argv(self, binary, workdir, command, extra_binds=(), extra_env=None):
        argv = [binary]
        for ns in self._profile.get("namespaces", ["user"]):
            argv.append(f"--unshare-{ns}")
        argv.append("--die-with-parent")
        for src, dest in self._profile.get("binds_ro", []):
            argv += ["--ro-bind", src, dest]
        for src, dest in extra_binds:
            argv += ["--ro-bind", src, dest]
        for src, dest in self._profile.get("symlinks", []):
            argv += ["--symlink", src, dest]
        for path in self._profile.get("tmpfs", []):
            argv += ["--tmpfs", path]
        argv += ["--bind", str(workdir), str(workdir)]
        for key, value in self._profile.get("env", {}).items():
            argv += ["--setenv", key, value]
        for key, value in dict(extra_env or {}).items():
            argv += ["--setenv", key, value]
        for key in self._profile.get("env_unset", []):
            argv += ["--unsetenv", key]
        argv += ["--chdir", str(workdir), *command]
        return argv

    def argv_for(self, workdir, command, extra_binds=(), extra_env=None):
        """Sandbox argv for one run; per-run env rides as extra `--setenv`.

        Uses the configured binary verbatim (no PATH resolution): call
        after a passing preflight, or let PATH lookup resolve it at
        spawn. Unset entries are emitted last, so unset wins on a
        set/unset conflict by construction.
        """
        return self._argv(
            self._binary, workdir, command, extra_binds, extra_env
        )

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

    def run(self, command, workdir, timeout_s=120, extra_binds=(), input_text=None):
        binary = self._resolve()
        if not Path(workdir).is_dir():
            raise ExecutionError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        proc = subprocess.Popen(
            self._argv(binary, workdir, command, extra_binds),
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir,
            start_new_session=True,
        )
        try:
            out_bytes, err_bytes = proc.communicate(
                input_text.encode() if input_text is not None else None,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            _kill_tree(proc)
            raise ExecutionError(
                "runner_unavailable",
                f"Sandboxed run timed out after {timeout_s}s.",
            ) from exc
        return subprocess.CompletedProcess(
            proc.args,
            proc.returncode,
            _clean_stream(out_bytes),
            _clean_stream(err_bytes),
        )
