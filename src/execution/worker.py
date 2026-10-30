"""Isolated worker substrate (I23/I24): one sandboxed worker per cell.

A CellRunner admits approved console cells and runs each in a fresh
worker: a BwrapRunner-confined `/usr/bin/python3` on a fresh scratch
directory (scratch-only writes, I16 output budgets, kill on timeout).
Approval binding is NOT reimplemented here — run_cell admits through
ConsoleSession.admit_cell and inherits approval_invalid for free.

Execution-scoped IPC credentials (I23): each run issues one token
from a CredentialGate and injects it as ROCKETEDA_CELL_TOKEN. The
gate accepts a token only while its run lives; background or
delayed callbacks after the run meet credential_revoked, and tokens
from other runs meet credential_revoked too — the namespace never
crosses cells. Revocation plus confirmed tree-kill strictly precede
the terminal state and therefore the next cell (runs are serial).

Reusable results persist only as approved artifacts (I24): the
caller declares relative scratch paths up front; at harvest time
each is resolved and only survivors strictly inside the scratch are
copied to the artifacts root (symlink escapes are rejected, never
followed). The scratch itself is always removed.

Crash/timeout reconciliation is truthful: completed (exit 0) is the
only ok state; failed (nonzero exit), timeout (budget kill, partial
stdout plus present artifacts retained), and crashed (death by
signal) all report ok False with a reason — never a fake PASS.

Network namespaces ride capability probing, loudly: the worker
tries ["user", "net"] first and falls back to ["user"] only where
the kernel refuses, stamping every admission and result with
network_isolated. require_net=True disables admission instead of
degrading. (This sandbox denies netns; re-prove on target, B10.)
"""

import hashlib
import os
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path, PurePosixPath

from .errors import ExecutionError
from .runner import BwrapRunner, clean_stream, default_profile, pgid_survivors

_CELL_PYTHON = "/usr/bin/python3"
_CELL_ENTRY = "cell.py"
_TOKEN_BYTES = 32
_KILL_CONFIRM_GRACE_S = 2.0
_KILL_CONFIRM_STEP_S = 0.05


def worker_profile(tool_paths=(), extra_unset=()):
    """Sandbox profile for cells: the default recipe, scrubbed by default.

    DISPLAY is always unset inside workers (netgen's Tk init aborts
    against an unreachable display); callers add more via extra_unset.
    Namespaces stay ["user"] here — CellRunner upgrades to net where
    the kernel proves it, and says so on every result.

    Args:
        tool_paths: Resolved tool binary paths to bind read-only.
        extra_unset: Extra env names scrubbed inside workers.

    Returns:
        Cell sandbox profile mapping.
    """
    profile = default_profile(tool_paths)
    profile["env_unset"] = list(profile.get("env_unset", [])) + list(extra_unset)
    return profile


class CredentialGate:
    """Thread-safe execution-scoped credential ledger.

    Tokens are random per run. invoke() accepts a token only while
    its run is live; revoked tokens raise credential_revoked and
    never-issued tokens raise credential_unknown.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._live = {}
        self._revoked = set()

    def issue(self, run_id):
        """Issue one random token scoped to a live run.

        Args:
            run_id: Run the token is scoped to.

        Returns:
            Token hex string.
        """
        token = secrets.token_hex(_TOKEN_BYTES)
        with self._lock:
            self._live[token] = run_id
        return token

    def invoke(self, token, call=None):
        """Accept a token only while its run lives.

        Args:
            token: Token to invoke with.
            call: Call descriptor recorded on acceptance.

        Returns:
            Acceptance with run_id, call, and accepted True.

        Raises:
            ExecutionError: credential_revoked for an expired token,
                credential_unknown for a never-issued token.
        """
        with self._lock:
            if token in self._live:
                return {
                    "run_id": self._live[token],
                    "call": call,
                    "accepted": True,
                }
            revoked = token in self._revoked
        if revoked:
            raise ExecutionError(
                "credential_revoked",
                "Credential expired with its run; delayed calls rejected.",
            )
        raise ExecutionError(
            "credential_unknown", "Unknown credential: never issued."
        )

    def revoke(self, run_id):
        """Expire every token scoped to one run.

        Args:
            run_id: Run whose tokens expire.

        Returns:
            Mapping with run_id and whether any token expired.
        """
        with self._lock:
            expired = [
                token for token, owner in self._live.items() if owner == run_id
            ]
            for token in expired:
                del self._live[token]
                self._revoked.add(token)
        return {"run_id": run_id, "revoked": bool(expired)}


def _validate_artifacts(artifacts):
    names = []
    for name in artifacts:
        parsed = PurePosixPath(name)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or not parsed.parts
            or str(name) != parsed.as_posix()
        ):
            raise ExecutionError(
                "invalid_reference",
                f"Artifact escapes the scratch: {name}.",
            )
        names.append(parsed.as_posix())
    return names


def _confirm_tree_dead(pgid, grace_s=_KILL_CONFIRM_GRACE_S):
    """True once no process-group member survives (bounded wait)."""
    deadline = time.monotonic() + grace_s
    while True:
        if not pgid_survivors(pgid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_KILL_CONFIRM_STEP_S)


class CellRunner:
    """Admit approved cells; run each in a fresh isolated worker.

    Args:
        binary: bwrap binary name or path.
        profile: Sandbox profile; worker_profile() when omitted.
        artifacts_root: Harvest destination root; temp dir default.
        default_timeout_s: Cell budget when the call omits one.
        require_net: Refuse admission unless net isolation probes;
            degrade loudly to user-only otherwise.
    """

    def __init__(self, binary="bwrap", profile=None, artifacts_root=None,
                 default_timeout_s=120, require_net=False):
        self._binary = binary
        self._base_profile = dict(profile) if profile else worker_profile()
        self._gate = CredentialGate()
        self._default_timeout_s = default_timeout_s
        self._artifacts_root = Path(
            artifacts_root
            if artifacts_root is not None
            else Path(tempfile.gettempdir()) / "rocketeda_cell_artifacts"
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
            self._prove_cell_python(runner)
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

    def _prove_cell_python(self, runner):
        with tempfile.TemporaryDirectory(prefix="cell_python_probe_") as tmp:
            try:
                proc = runner.run(
                    [_CELL_PYTHON, "-c", "pass"], tmp, timeout_s=30
                )
            except ExecutionError as exc:
                raise ExecutionError(
                    "isolation_unavailable",
                    f"sandbox python3 unavailable: {exc}.",
                ) from exc
        if proc.returncode != 0:
            raise ExecutionError(
                "isolation_unavailable",
                f"sandbox python3 unavailable: exit {proc.returncode}.",
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
        """Execution-scoped credential gate for cell IPC.

        Returns:
            Credential gate.
        """
        return self._gate

    def run_cell(self, session, approval_id, code, history_cursor,
                 env_digest, expected_revision, artifacts=(), timeout_s=None,
                 on_live=None):
        """Run one approved cell in a fresh worker; return its record.

        Pre-spawn checks precede any execution, cheapest first:
        artifact paths, then the console approval binding, then
        isolation admission. Without admission the call raises
        isolation_unavailable and nothing runs anywhere — no host
        fallback, ever.

        Args:
            session: Console session admitting the approval.
            approval_id: Approval bound by request_cell_approval.
            code: Full worker source; must match the binding.
            history_cursor: History position to re-check.
            env_digest: Environment digest to re-check.
            expected_revision: Revision to re-check.
            artifacts: Scratch-relative paths to harvest.
            timeout_s: Cell budget; runner default when omitted.
            on_live: Optional callback while the worker is live.

        Returns:
            Terminal cell record (completed/failed/timeout/crashed)
                with stdio, artifacts, and kill confirmations.

        Raises:
            ExecutionError: invalid_reference for escaping artifact
                paths, approval_invalid for binding drift,
                isolation_unavailable without admission,
                runner_unavailable when the worker cannot spawn.
        """
        names = _validate_artifacts(artifacts)
        session.admit_cell(
            approval_id, code=code, history_cursor=history_cursor,
            env_digest=env_digest, expected_revision=expected_revision,
        )
        if not self._admission["admitted"]:
            raise ExecutionError(
                "isolation_unavailable", self._admission["reason"]
            )
        budget = self._default_timeout_s if timeout_s is None else timeout_s
        scratch = tempfile.mkdtemp(prefix="rocketeda_cell_")
        run_id = uuid.uuid4().hex
        token = self._gate.issue(run_id)
        Path(scratch, _CELL_ENTRY).write_text(code, encoding="utf-8")
        argv = self._runner.argv_for(
            scratch, [_CELL_PYTHON, _CELL_ENTRY],
            extra_env={"ROCKETEDA_RUN_ID": run_id,
                       "ROCKETEDA_CELL_TOKEN": token},
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
                try:
                    out_bytes, err_bytes = proc.communicate(timeout=budget)
                except subprocess.TimeoutExpired:
                    self._terminate(proc)
                    out_bytes, err_bytes = proc.communicate()
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="timeout", ok=False,
                        reason=f"timeout after {budget}s; partials retained.",
                        exit_code=None, partial=True, pgid=proc.pid,
                    )
                returncode = proc.returncode
                if returncode == 0:
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="completed", ok=True, reason=None,
                        exit_code=0, partial=False, pgid=proc.pid,
                    )
                # bwrap reports child signal death as 128+signo (the
                # shell convention), so exits above 128 read as crashes.
                # A cell deliberately exiting 129+ misreads the same way;
                # both land ok False, so the ambiguity never fake-passes.
                if returncode < 0 or returncode > 128:
                    signo = -returncode if returncode < 0 else returncode - 128
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="crashed", ok=False,
                        reason=f"death by signal {signo}.",
                        exit_code=returncode, partial=True, pgid=proc.pid,
                    )
                return self._finish(
                    run_id, scratch, names, out_bytes, err_bytes,
                    state="failed", ok=False,
                    reason=f"exit {returncode}.",
                    exit_code=returncode, partial=False, pgid=proc.pid,
                )
            finally:
                if proc.poll() is None:
                    self._terminate(proc)
                    proc.communicate()
        finally:
            self._gate.revoke(run_id)
            shutil.rmtree(scratch, ignore_errors=True)

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
                state, ok, reason, exit_code, partial, pgid):
        # Revocation + tree-kill confirmation strictly precede the
        # terminal record (and therefore the next cell).
        self._gate.revoke(run_id)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        tree_killed = _confirm_tree_dead(pgid)
        harvested, rejected = self._harvest(run_id, scratch, names)
        return {
            "run_id": run_id,
            "state": state,
            "ok": ok,
            "reason": reason,
            "exit_code": exit_code,
            "stdout": clean_stream(out_bytes),
            "stderr": clean_stream(err_bytes),
            "partial": partial,
            "artifacts": harvested,
            "rejected_artifacts": rejected,
            "network_isolated": self._admission["network_isolated"],
            "credential_revoked": True,
            "tree_killed": tree_killed,
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
