# Bubblewrap isolation probe (I16 input, 2026-10-28)

Can solver subprocesses run confined? Tool: bwrap 0.11.0, non-setuid
(user-namespace based). Probed with iverilog+vvp from oss-cad-suite.

## What this environment denies

- Network namespaces: `--unshare-all` dies with
  `loopback: Failed to create NETLINK_ROUTE socket` (exit 1).
- Fresh mounts: `--proc`/`--dev` fail with `Operation not permitted`.
- Allowed: user namespaces, bind mounts, symlinks, tmpfs.

Net isolation is therefore UNPROVABLE here (both host and sandbox
show an empty route table anyway). Filesystem isolation is fully
proven below. I16 design rule: profiles declare required namespaces;
where the kernel cannot provide them, preflight REFUSES with
`runner_unavailable` — never silently degraded. Re-prove
`--unshare-net` on target Ubuntu in B10.

## Working profile (verified)

```
bwrap --unshare-user --die-with-parent \
  --ro-bind /usr /usr \
  --symlink usr/bin /bin --symlink usr/sbin /sbin \
  --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --ro-bind /etc /etc --ro-bind /proc /proc \
  --ro-bind <tools> <tools> \
  --bind <work> /work --tmpfs /tmp \
  --setenv HOME /work --setenv PATH /usr/bin:/bin \
  --chdir /work <tool argv...>
```

## Gotchas decoded (each cost a failed run)

1. `--unshare-all` is fatal here; list namespaces explicitly and skip
   net (see above).
2. `--ro-bind / /` breaks dest creation (`Can't mkdir /work` on the
   fresh ro root). Bind sysdirs individually instead.
3. Missing `/lib64` gives a confusing `execvp ... No such file` —
   the dynamic loader path must exist, not just the binary.
4. A read-only `/proc` bind is REQUIRED for iverilog: it resolves
   its backend via `/proc/self/exe`, and without it falls back to a
   bogus compiled-in `/yosyshq` prefix (exit 127).

## Verified behavior

- Sandboxed `iverilog -o sim.vvp counter.v tb_pass.v`: exit 0,
  `sim.vvp` produced in the work bind.
- Sandboxed `vvp sim.vvp`: exit 0, `TB_PASS count=10` — identical
  to the host run.
- `/usr/evil` write denied (read-only fs); `/work/ok` write allowed.
- Home directory invisible except the bound tools subtree
  (`.bashrc` unreadable, only `tools` listed).

## Adapter sketch (next: isolation slice)

- An `IsolationRunner` port wraps solver argv in a profile:
  preflight probes bwrap plus required namespaces (cheap
  `bwrap ... /bin/true`), execute prefixes argv, parse unchanged.
- Profiles are data (binds, symlinks, env, required namespaces), one
  per solver family; the DRC/HDL adapters gain an optional runner.
- Full `--unshare-net` proof and the setuid-vs-userns decision ride
  with B10 on target Ubuntu.

## Addendum: workdir binds at its own path (2026-10-28)

The probe recipe above binds the work tree at `/work`, which only fits
relative argv. `BwrapRunner` instead binds it at its own host path and
chdirs there, so absolute argv (resolved tool and source paths) works
unchanged inside. Proven by the sandboxed sim suite.

## Addendum: oss-cad-suite bundles its own bwrap (2026-10-28)

`~/tools/oss-cad-suite/bin/bwrap` exists and SHADOWS the system bwrap
when oss-cad-suite leads PATH — and it cannot create namespaces here
(`No permissions to create a new namespace`). Consequences, both now
handled:

- `BwrapRunner.preflight()` refuses it with `runner_unavailable`,
  exactly as designed (unprovable profile, loud refusal).
- The runner tests take a `runner` fixture that skips unless the
  PATH-resolved bwrap passes preflight — shadowing skips loudly,
  never mystery-fails.
- B10 must decide bwrap provenance (system vs bundled) and PATH
  order. Until then, dev shells that export oss-cad-suite first will
  see the 4 bwrap-backed runner tests skip.
