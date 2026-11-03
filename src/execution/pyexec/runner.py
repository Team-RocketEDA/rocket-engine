"""Worker lifecycle: confined execution of one cell."""

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from ..errors import ExecutionError
from ..runner import BwrapRunner, clean_stream
from ..worker import CredentialGate, worker_profile
from .support import (
    CELL_ENTRY,
    DEFAULT_TIMEOUT_S,
    _POLL_SLICE_S,
    _check_timeout,
    _confirm_tree_dead,
    _display_exception,
    _interp_chain,
    _validate_artifacts,
    parse_exception,
)


class PythonExecRunner:
    """Fresh prepared workers on the console's sandbox substrate.

    Same confinement machinery as console cells (`BwrapRunner` +
    `worker_profile` + `CredentialGate`): one worker per run, a
    scratch-only write area, execution-scoped IPC credentials, and
    revocation plus confirmed tree-kill before every terminal
    record. The interpreter is the prepared profile's Python (with
    gdsfactory/numpy where the profile installs them), bound
    read-only into the sandbox — never the host interpreter, and
    with no host fallback when isolation is unprovable.

    Args:
        python: Prepared interpreter path; the running engine's
            interpreter when omitted.
        extra_tool_paths: Extra resolved paths ro-bound with the
            profile (tool binaries on PATH inside the worker).
        profile: Full sandbox profile override; worker_profile()
            over the interpreter when omitted.
        binary: bwrap binary name or path.
        artifacts_root: Harvest destination root; temp dir default.
        default_timeout_s: Worker budget when the call omits one.
        require_net: Refuse admission unless net isolation probes;
            degrade loudly to user-only otherwise.
    """

    def __init__(self, python=None, extra_tool_paths=(), profile=None,
                 binary="bwrap", artifacts_root=None,
                 default_timeout_s=DEFAULT_TIMEOUT_S, require_net=False):
        self._python = python or sys.executable
        if profile is None:
            # venv interpreters are often symlink chains into a
            # manager-owned install (uv): the kernel traverses every
            # dirent inside the sandbox, so cover each level's root
            # or exec fails with ENOENT.
            tool_paths = _interp_chain(self._python)
            tool_paths.extend(extra_tool_paths)
            base = worker_profile(tool_paths=tool_paths)
            env = dict(base.get("env", {}))
            env["MPLBACKEND"] = "Agg"
            env["MPLCONFIGDIR"] = "/tmp"
            base["env"] = env
            self._base_profile = base
        else:
            self._base_profile = dict(profile)
        self._binary = binary
        self._gate = CredentialGate()
        self._default_timeout_s = default_timeout_s
        self._artifacts_root = Path(
            artifacts_root
            if artifacts_root is not None
            else Path(tempfile.gettempdir()) / "rocketeda_pyexec_artifacts"
        )
        self._admission, self._runner = self._preflight(require_net)

    def _preflight(self, require_net):
        try:
            runner = BwrapRunner(self._base_profile, binary=self._binary)
            runner.preflight()
        except ExecutionError as exc:
            return (
                {"admitted": False, "reason": str(exc),
                 "network_isolated": False},
                None,
            )
        network_isolated = False
        try:
            netted = dict(self._base_profile)
            namespaces = list(netted.get("namespaces", ["user"]))
            if "net" not in namespaces:
                namespaces.append("net")
            netted["namespaces"] = namespaces
            BwrapRunner(netted, binary=self._binary).preflight()
            network_isolated = True
            runner = BwrapRunner(netted, binary=self._binary)
        except ExecutionError:
            if require_net:
                return (
                    {
                        "admitted": False,
                        "reason": "network isolation unprovable: "
                        "net namespace refused by the kernel.",
                        "network_isolated": False,
                    },
                    None,
                )
        try:
            self._prove_python(runner)
        except ExecutionError as exc:
            return (
                {"admitted": False, "reason": str(exc),
                 "network_isolated": False},
                None,
            )
        return (
            {"admitted": True, "reason": None,
             "network_isolated": network_isolated},
            runner,
        )

    def _prove_python(self, runner):
        with tempfile.TemporaryDirectory(prefix="pyexec_python_probe_") as tmp:
            try:
                proc = runner.run(
                    [self._python, "-c", "pass"], tmp, timeout_s=30
                )
            except ExecutionError as exc:
                raise ExecutionError(
                    "isolation_unavailable",
                    f"sandbox python unavailable: {exc}.",
                ) from exc
        if proc.returncode != 0:
            raise ExecutionError(
                "isolation_unavailable",
                f"sandbox python unavailable: exit {proc.returncode}.",
            )

    @property
    def admission(self):
        """Isolation admission record, stamped on every result.

        Returns:
            Admission mapping copy (admitted, reason,
                network_isolated).
        """
        return dict(self._admission)

    @property
    def gate(self):
        """Execution-scoped credential gate for worker IPC.

        Returns:
            Credential gate.
        """
        return self._gate

    @property
    def python(self):
        """Prepared interpreter path this runner executes.

        Returns:
            Interpreter path string.
        """
        return self._python

    def run(self, source, run_id=None, timeout_s=None, artifacts=(),
            extra_env=None, on_live=None, is_cancelled=None,
            cell_name=CELL_ENTRY, cell_line_offset=0):
        """Run one source text in a fresh worker; return its record.

        Pre-spawn checks precede any execution, cheapest first:
        artifact paths, then timeout shape, then isolation
        admission. Without admission the call raises
        isolation_unavailable and nothing runs anywhere — no host
        fallback, ever. The wait polls in short slices so a
        cancelled job kills its worker tree promptly instead of
        sleeping out the budget.

        Args:
            source: Full worker source to execute.
            run_id: Execution id; generated when omitted.
            timeout_s: Worker budget; runner default when omitted.
            artifacts: Scratch-relative paths to harvest.
            extra_env: Per-run env additions inside the worker.
            on_live: Optional callback while the worker is live.
            is_cancelled: Optional zero-arg callable; a true
                reading kills the worker and reports cancelled.
            cell_name: Display filename in_cell frames report.
            cell_line_offset: Worker lines preceding the display
                cell; in_cell frames shift back by this much so
                the location points at submitted code, never at
                the deleted scratch or the trusted preamble.

        Returns:
            Terminal worker record (completed/failed/timeout/
                crashed/cancelled) with bounded stdio, the parsed
                exception location, artifacts, and kill
                confirmations.

        Raises:
            ExecutionError: invalid_reference for escaping artifact
                paths, invalid_command for a malformed timeout,
                isolation_unavailable without admission,
                runner_unavailable when the worker cannot spawn.
        """
        names = _validate_artifacts(artifacts)
        budget = self._default_timeout_s if timeout_s is None else _check_timeout(timeout_s)
        if not self._admission["admitted"]:
            raise ExecutionError(
                "isolation_unavailable", self._admission["reason"]
            )
        scratch = tempfile.mkdtemp(prefix="rocketeda_pyexec_")
        run_id = run_id or uuid.uuid4().hex
        token = self._gate.issue(run_id)
        Path(scratch, CELL_ENTRY).write_text(source, encoding="utf-8")
        env = {
            "ROCKETEDA_RUN_ID": run_id,
            "ROCKETEDA_PYEXEC_TOKEN": token,
            "HOME": scratch,
        }
        env.update(extra_env or {})
        argv = self._runner.argv_for(
            scratch, [self._python, CELL_ENTRY], extra_env=env,
        )
        try:
            try:
                proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=scratch,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ExecutionError(
                    "runner_unavailable", f"Worker spawn failed: {exc}."
                ) from exc
            try:
                if on_live is not None:
                    on_live(run_id, token)
                out_bytes, err_bytes, outcome = self._wait(
                    proc, budget, is_cancelled
                )
                if outcome == "timeout":
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="timeout", ok=False,
                        reason=f"timeout after {budget}s; partials retained.",
                        exit_code=None, partial=True, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                if outcome == "cancelled":
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="cancelled", ok=False,
                        reason="cancelled via the job surface; "
                        "worker tree killed.",
                        exit_code=None, partial=True, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                returncode = proc.returncode
                if returncode == 0:
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="completed", ok=True, reason=None,
                        exit_code=0, partial=False, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                # bwrap reports child signal death as 128+signo (the
                # shell convention), so exits above 128 read as crashes.
                # A script deliberately exiting 129+ misreads the same
                # way; both land ok False, so the ambiguity never
                # fake-passes.
                if returncode < 0 or returncode > 128:
                    signo = -returncode if returncode < 0 else returncode - 128
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="crashed", ok=False,
                        reason=f"death by signal {signo}.",
                        exit_code=returncode, partial=True, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                return self._finish(
                    run_id, scratch, names, out_bytes, err_bytes,
                    state="failed", ok=False,
                    reason=f"exit {returncode}.",
                    exit_code=returncode, partial=False, pgid=proc.pid,
                    cell_name=cell_name,
                    cell_line_offset=cell_line_offset,
                )
            finally:
                if proc.poll() is None:
                    self._terminate(proc)
                    proc.communicate()
        finally:
            self._gate.revoke(run_id)
            shutil.rmtree(scratch, ignore_errors=True)

    @staticmethod
    def _wait(proc, budget, is_cancelled):
        start = time.monotonic()
        while True:
            if is_cancelled is not None and is_cancelled():
                PythonExecRunner._terminate(proc)
                out_bytes, err_bytes = proc.communicate()
                return out_bytes, err_bytes, "cancelled"
            remaining = budget - (time.monotonic() - start)
            if remaining <= 0:
                PythonExecRunner._terminate(proc)
                out_bytes, err_bytes = proc.communicate()
                return out_bytes, err_bytes, "timeout"
            try:
                out_bytes, err_bytes = proc.communicate(
                    timeout=min(_POLL_SLICE_S, remaining)
                )
            except subprocess.TimeoutExpired:
                continue
            return out_bytes, err_bytes, "exited"

    @staticmethod
    def _terminate(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
        proc.wait()

    def _finish(self, run_id, scratch, names, out_bytes, err_bytes,
                state, ok, reason, exit_code, partial, pgid,
                cell_name=CELL_ENTRY, cell_line_offset=0):
        # Revocation + tree-kill confirmation strictly precede the
        # terminal record (and therefore the next run).
        self._gate.revoke(run_id)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        tree_killed = _confirm_tree_dead(pgid)
        harvested, rejected = self._harvest(run_id, scratch, names)
        stdout = clean_stream(out_bytes)
        stderr = clean_stream(err_bytes)
        exception = _display_exception(
            parse_exception(stderr), cell_name, cell_line_offset)
        return {
            "run_id": run_id,
            "state": state,
            "ok": ok,
            "reason": reason,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "partial": partial,
            "exception": exception,
            "artifacts": harvested,
            "rejected_artifacts": rejected,
            "network_isolated": self._admission["network_isolated"],
            "credential_revoked": True,
            "tree_killed": tree_killed,
            "spawned": True,
            "scratch": scratch,
        }

    def _harvest(self, run_id, scratch, names):
        base = Path(scratch).resolve()
        harvested, rejected = [], []
        for name in names:
            target = (base / name).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                rejected.append(name)
                continue
            digest = hashlib.sha256()
            with open(target, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            dest = self._artifacts_root / run_id / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, dest)
            harvested.append(
                {
                    "name": name,
                    "path": str(dest),
                    "bytes": dest.stat().st_size,
                    "sha256": digest.hexdigest(),
                }
            )
        return harvested, rejected
