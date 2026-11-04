# PALACE-SOURCE: Read Palace install docs into provision-sources §12

*Status: Backlog · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

`verdict()` reports palace `unsourced` and
`docs/provision-sources.md` §12 already names the action (fetch
awslabs.github.io/palace superbuild docs) — but the action was never
taken, so Palace has no pin, no recipe, and no explicit deferral. It is
the only solver in the matrix with neither.

## Goal

Palace sourced or explicitly deferred with reason.

## Scope

- Perform the §12 action: read the awslabs Palace superbuild docs,
  record URL + revision + pin preconditions in `provision-sources.md`.
- Either add a provision recipe (then it joins the matrix) or record an
  explicit deferral (owner + unblock condition) in
  [PROV-DEFERRED](PROV-DEFERRED.md).

## Acceptance

- Palace is pinned with a recipe or deferred with reason; the
  `unsourced` verdict line is gone either way.
