# LAYOUT-SCHEMA: Folder schema YAML in source

*Status: Backlog · Depends: STORAGE-REV · Size: M · Roadmap: orch-build-mvp*

## Why

Every path decision this week (co-located runs, shared PDK store,
gitignored outputs, KiCad-style config) currently lives in prose.
Prose rots; a machine-readable schema doesn't. A single versioned
YAML file describing the engine-root and project layouts gives us
one source of truth that doubles as validator input and migration
baseline — and its `required` + non-empty checks are the teeth for
zero-silent-defaults: the template ships defaults, and anything
that matters must be present and non-empty or startup fails loudly.

## What

- `src/interfaces/layout_schema.yaml` (schema_version 1) using the
  agreed Entry struct (name/type/match/pattern/required/tracked/
  created_by/mutable/children-or-format/description).
- Parser + validator: check a tree against the schema, derive and
  verify `.gitignore` from `tracked` flags.
- Refuse-newer path: folder stamped above known version errors
  loudly, never misreads.
- Per-tool defaults audit feeds the template entries (timeouts,
  threads, flags, deck/tool fallbacks, seeds).

## Acceptance

- RED-first tests: valid tree passes; missing required entry fails;
  present-but-empty required entry fails; newer-version folder
  refuses with a clear message; derived gitignore matches expected.
- Suite green both PATH configs; coverage floor holds.
