"""Block-scoped run targets (BLOCK-RUNS): run-from-block substrate.

Every `run_*` verb targets the project today; this module teaches run
targets an entity scope so `target: {scope: block, id}` flows through
submit, preflight, snapshot, and verdict with the same honesty as
project runs. No new verbs: scope rides the existing `target` shape,
and any future verb ships with a scope parameter from birth.

Pipeline (the wiring patch calls these from the composition root):

1. `parse_target` normalizes the caller target (absent means the
   whole project).
2. `check_operation_scope` gates block scope to the verbs that
   serve it — SPICE + syntax first, decks following.
3. `resolve_block` resolves the block entity; unknown ids fail
   with the named `unknown_block` reason, never an empty run.
4. `snapshot_closure` pins the block's component closure
   (sources, CellLink, params, constraints) so the run cannot
   drift mid-flight and sibling edits cannot leak in.
5. `narrow_job_for_block` rewrites the solver job onto the
   closure sources before adapter preflight.
6. `build_scope_record` binds `(run_id, revision, block_id,
   deck)` provenance plus the closure hash; `stamp_verdict`
   records that scope on the verdict, and the run event carries
   it into the ledger as provenance.

The module never imports the composition root, adapters, or the
CELL-LINK lane: CellLink resolution arrives as an optional caller
callable, so this substrate stands alone however the lanes land.
"""

import copy
import hashlib
import json
from collections.abc import Mapping

#: Scopes a run target may name. Absent targets mean `project`.
PROJECT_SCOPE = "project"
BLOCK_SCOPE = "block"
SUPPORTED_SCOPES = (PROJECT_SCOPE, BLOCK_SCOPE)

#: Run verbs serving block scope. SPICE + syntax first; every other
#: verb rejects block targets with `unsupported_scope` until its deck
#: lane wires narrowing.
BLOCK_RUN_OPERATIONS = frozenset({"run_spice", "run_syntax"})

__all__ = [
    "BLOCK_RUN_OPERATIONS",
    "BLOCK_SCOPE",
    "PROJECT_SCOPE",
    "SUPPORTED_SCOPES",
    "BlockScopeError",
    "build_scope_record",
    "check_operation_scope",
    "closure_hash",
    "narrow_job_for_block",
    "parse_target",
    "resolve_block",
    "scope_provenance",
    "snapshot_closure",
    "stamp_verdict",
]


class BlockScopeError(Exception):
    """Block-scope violation with a stable machine code.

    Args:
        code: Stable machine-readable error code
            (unknown_block, invalid_target, unsupported_scope,
            invalid_block).
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def parse_target(target):
    """Normalize a caller run target to (scope, id).

    Absent targets mean the whole project; block targets name the
    block entity id the run is scoped to.

    Args:
        target: Caller target mapping ({scope, id}), or None for
            a project run.

    Returns:
        Normalized mapping with scope (project or block) and id
            (the block id, or None for project runs).

    Raises:
        BlockScopeError: invalid_target for a non-mapping target,
            an unknown scope, a block scope without a non-empty
            string id, or a project scope carrying an id.
    """
    if target is None:
        return {"scope": PROJECT_SCOPE, "id": None}
    if not isinstance(target, Mapping):
        raise BlockScopeError(
            "invalid_target", f"Run target must be a mapping, got {target!r}."
        )
    scope = target.get("scope", PROJECT_SCOPE)
    if scope not in SUPPORTED_SCOPES:
        raise BlockScopeError(
            "invalid_target",
            f"Unknown target scope {scope!r}; supported scopes: "
            f"{list(SUPPORTED_SCOPES)}.",
        )
    block_id = target.get("id")
    if scope == BLOCK_SCOPE:
        if not isinstance(block_id, str) or not block_id:
            raise BlockScopeError(
                "invalid_target",
                "target.scope 'block' needs a non-empty string id.",
            )
        return {"scope": BLOCK_SCOPE, "id": block_id}
    if block_id is not None:
        raise BlockScopeError(
            "invalid_target", "target.scope 'project' takes no id."
        )
    return {"scope": PROJECT_SCOPE, "id": None}


def check_operation_scope(operation, scope):
    """Gate one operation against a target scope.

    Project scope serves every operation; block scope serves only
    the verbs in BLOCK_RUN_OPERATIONS (SPICE + syntax first).

    Args:
        operation: Cataloged operation about to run.
        scope: Target scope (project or block).

    Returns:
        The admitted scope, unchanged.

    Raises:
        BlockScopeError: invalid_target for an unknown scope,
            unsupported_scope when the operation serves no block
            runs yet (the message names the serving verbs).
    """
    if scope == PROJECT_SCOPE:
        return PROJECT_SCOPE
    if scope != BLOCK_SCOPE:
        raise BlockScopeError(
            "invalid_target",
            f"Unknown target scope {scope!r}; supported scopes: "
            f"{list(SUPPORTED_SCOPES)}.",
        )
    if operation not in BLOCK_RUN_OPERATIONS:
        raise BlockScopeError(
            "unsupported_scope",
            f"{operation} serves no block runs yet "
            f"(block runs serve: {sorted(BLOCK_RUN_OPERATIONS)}).",
        )
    return BLOCK_SCOPE


def resolve_block(block_id, blocks):
    """Resolve one block entity from the block store.

    Args:
        block_id: Block entity id to resolve.
        blocks: Block store: a mapping of id to block entity, or
            a list of block mappings each carrying an id.

    Returns:
        The resolved block entity mapping (owned by the store;
            snapshot it before running).

    Raises:
        BlockScopeError: invalid_target for a non-string or empty
            block id, invalid_block for a malformed store or block
            entry, unknown_block naming the id when no block
            matches.
    """
    if not isinstance(block_id, str) or not block_id:
        raise BlockScopeError(
            "invalid_target", f"Block id must be a non-empty string, got {block_id!r}."
        )
    if isinstance(blocks, Mapping):
        try:
            return blocks[block_id]
        except KeyError:
            raise BlockScopeError(
                "unknown_block",
                f"Unknown block: {block_id!r}.",
                fields=[block_id],
            ) from None
    if isinstance(blocks, (list, tuple)):
        for block in blocks:
            if not isinstance(block, Mapping):
                raise BlockScopeError(
                    "invalid_block", f"Block must be a mapping, got {block!r}."
                )
            entry_id = block.get("id")
            if not isinstance(entry_id, str) or not entry_id:
                raise BlockScopeError(
                    "invalid_block", "Each block needs a non-empty string id."
                )
            if entry_id == block_id:
                return block
        raise BlockScopeError(
            "unknown_block", f"Unknown block: {block_id!r}.", fields=[block_id]
        )
    raise BlockScopeError(
        "invalid_block", "Blocks must be a mapping or a list of blocks."
    )


def snapshot_closure(block, resolve_celllink=None, variant=None):
    """Pin a block's component closure for one run.

    The closure (sources, CellLink, params, constraints) is the
    complete input set the scoped run may read: snapshotting it at
    submit time freezes the run against later edits and keeps
    sibling blocks out by construction.

    Args:
        block: Block entity mapping with an id plus optional
            sources, CellLink, params, and constraints components.
        resolve_celllink: Optional resolver called as
            `resolve_celllink(block, variant)` returning the
            effective (cell, pinMap, variant) link; the raw stored
            CellLink is always pinned too. None pins the stored
            link only.
        variant: Variant selector passed to the resolver; None
            resolves the stored base link.

    Returns:
        Closure mapping with block_id, sources, celllink (the
            stored component, or None), celllink_resolved (the
            resolver output, or None), params, constraints, and
            variant. Every collection is a copy: storage is never
            mutated and never aliased.

    Raises:
        BlockScopeError: invalid_block for a malformed block or
            component (non-list sources, non-mapping CellLink,
            params, or constraints).
    """
    if not isinstance(block, Mapping):
        raise BlockScopeError(
            "invalid_block", f"Block must be a mapping, got {block!r}."
        )
    block_id = block.get("id")
    if not isinstance(block_id, str) or not block_id:
        raise BlockScopeError(
            "invalid_block", "Each block needs a non-empty string id."
        )
    sources = block.get("sources", [])
    if not isinstance(sources, list) or any(
        not isinstance(s, str) or not s for s in sources
    ):
        raise BlockScopeError(
            "invalid_block", f"Block {block_id!r} sources must be a list of paths."
        )
    raw_link = block.get("CellLink")
    if raw_link is not None and not isinstance(raw_link, Mapping):
        raise BlockScopeError(
            "invalid_block", f"Block {block_id!r} CellLink must be a mapping."
        )
    params = block.get("params", {})
    if not isinstance(params, Mapping):
        raise BlockScopeError(
            "invalid_block", f"Block {block_id!r} params must be a mapping."
        )
    constraints = block.get("constraints", {})
    if not isinstance(constraints, Mapping):
        raise BlockScopeError(
            "invalid_block", f"Block {block_id!r} constraints must be a mapping."
        )
    resolved = None
    if resolve_celllink is not None:
        resolved = resolve_celllink(block, variant)
    return {
        "block_id": block_id,
        "sources": list(sources),
        "celllink": copy.deepcopy(dict(raw_link)) if raw_link is not None else None,
        "celllink_resolved": resolved,
        "params": copy.deepcopy(dict(params)),
        "constraints": copy.deepcopy(dict(constraints)),
        "variant": variant,
    }


def closure_hash(closure):
    """Hash a closure for provenance and change detection.

    The hash is content-addressed and key-order stable: equal
    closures hash equally, so a rerun after a sibling edit proves
    isolation by hashing identically.

    Args:
        closure: Closure mapping from snapshot_closure.

    Returns:
        Hex sha256 over the canonical JSON encoding.

    Raises:
        BlockScopeError: invalid_block when the closure is not a
            mapping.
    """
    if not isinstance(closure, Mapping):
        raise BlockScopeError(
            "invalid_block", f"Closure must be a mapping, got {closure!r}."
        )
    canonical = json.dumps(
        closure, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def narrow_job_for_block(job, closure):
    """Rewrite a solver job onto a block closure.

    Sources are replaced wholesale: the adapter preflights and
    executes only the closure files, so project sources never leak
    into a block run. The closure hash rides along for provenance.

    Args:
        job: Solver job mapping (operation plus tool inputs).
        closure: Closure mapping from snapshot_closure.

    Returns:
        Job copy with sources replaced by the closure sources and
            a block_scope record (block_id plus closure_hash). The
            input job is never mutated.

    Raises:
        BlockScopeError: invalid_target when the job is not a
            mapping, invalid_block when the closure carries no
            block_id or sources list.
    """
    if not isinstance(job, Mapping):
        raise BlockScopeError(
            "invalid_target", f"Solver job must be a mapping, got {job!r}."
        )
    if (
        not isinstance(closure, Mapping)
        or not isinstance(closure.get("block_id"), str)
        or not closure.get("block_id")
        or not isinstance(closure.get("sources"), list)
    ):
        raise BlockScopeError(
            "invalid_block", "Closure must carry a block_id and a sources list."
        )
    narrowed = dict(job)
    narrowed["sources"] = list(closure["sources"])
    narrowed["block_scope"] = {
        "block_id": closure["block_id"],
        "closure_hash": closure_hash(closure),
    }
    return narrowed


def scope_provenance(run_id, revision, block_id, deck):
    """Cite a block run as (run_id, revision, block_id, deck).

    Args:
        run_id: Run the verdict belongs to.
        revision: Project revision the closure was pinned at.
        block_id: Block entity the run was scoped to.
        deck: Deck mapping the solver ran under (copied
            verbatim), or None for the default deck.

    Returns:
        Provenance mapping with run_id, revision, block_id, and
            deck keys.

    Raises:
        BlockScopeError: invalid_target for an empty citation
            field or a deck that is neither a mapping nor None.
    """
    for name, value in (
        ("run_id", run_id),
        ("revision", revision),
        ("block_id", block_id),
    ):
        if not isinstance(value, str) or not value:
            raise BlockScopeError(
                "invalid_target",
                f"Scope citation {name} must be a non-empty string, got {value!r}.",
            )
    if deck is None:
        deck = {}
    if not isinstance(deck, Mapping):
        raise BlockScopeError(
            "invalid_target", f"Scope citation deck must be a mapping, got {deck!r}."
        )
    return {
        "run_id": run_id,
        "revision": revision,
        "block_id": block_id,
        "deck": dict(deck),
    }


def stamp_verdict(verdict, scope):
    """Record block scope on a verdict, without mutating it.

    Args:
        verdict: Verdict mapping to cite scope on.
        scope: Provenance mapping from scope_provenance.

    Returns:
        Verdict copy with the scope recorded under "scope".

    Raises:
        BlockScopeError: invalid_target when the verdict is not a
            mapping, invalid_block when the scope misses a
            citation key.
    """
    if not isinstance(verdict, Mapping):
        raise BlockScopeError(
            "invalid_target", f"Verdict must be a mapping, got {verdict!r}."
        )
    if not isinstance(scope, Mapping):
        raise BlockScopeError(
            "invalid_block", f"Scope must be a mapping, got {scope!r}."
        )
    missing = [
        key
        for key in ("run_id", "revision", "block_id", "deck")
        if key not in scope
    ]
    if missing:
        raise BlockScopeError(
            "invalid_block",
            f"Scope misses citation keys: {missing}.",
        )
    stamped = dict(verdict)
    stamped["scope"] = dict(scope)
    return stamped


def build_scope_record(run_id, revision, block_id, deck, closure):
    """Bind one block run's provenance, hash, and closure.

    The record is what the submit path stores per run_id and what
    the verdict path stamps: provenance cites the run, the hash
    detects drift, and the closure replays exactly what ran.

    Args:
        run_id: Run the verdict belongs to.
        revision: Project revision the closure was pinned at.
        block_id: Block entity the run was scoped to.
        deck: Deck mapping the solver ran under, or None.
        closure: Closure mapping from snapshot_closure.

    Returns:
        Scope record with provenance, closure_hash, and a private
            closure copy.

    Raises:
        BlockScopeError: invalid_block when the closure belongs
            to another block, plus the scope_provenance codes for
            bad citation fields.
    """
    if not isinstance(closure, Mapping) or closure.get("block_id") != block_id:
        raise BlockScopeError(
            "invalid_block",
            f"Closure is for block {closure.get('block_id')!r} "
            f"when {block_id!r} was requested."
            if isinstance(closure, Mapping)
            else f"Closure must be a mapping, got {closure!r}.",
        )
    return {
        "provenance": scope_provenance(
            run_id=run_id, revision=revision, block_id=block_id, deck=deck
        ),
        "closure_hash": closure_hash(closure),
        "closure": copy.deepcopy(dict(closure)),
    }
