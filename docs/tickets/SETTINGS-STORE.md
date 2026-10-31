# SETTINGS-STORE: Engine settings store (design truth + migration mechanics)

*Status: Ready · Size: M · Roadmap: convergence (MVP track)*

## Why

Every design decision the engine makes reads configuration —
PDK pins, rule decks, net classes, text vars, library tables —
and today that configuration is scattered across
`constraints.yaml`, ad-hoc files, and vibes. KiCad solved
this a decade ago with a three-way split: versioned design
truth (`.kicad_pro`), per-user view state (`.kicad_prl`,
need-not-exist), and machine prefs — with versioned schemas,
chained migrators, and save hygiene (merge-onto-original,
absent-default-is-clean, atomic writes). We adopt the rule,
not the code. Without an engine-owned settings store, the
frontend cannot render a project panel, rule scope, or stackup
from contract, and every new config key becomes another silent
default that rots reproducibility (I28).

## What

- RED-first: engine-owned design-truth schemas, all
  versioned + migrated: `chip.manifest` (name, PDK
  ref+version, canvas list), `design.rules` nested (ERC
  default+on/off, DRC deck ref, LVS config), `net.classes`
  (default class + per-net color/visibility split),
  `text.vars` scalar map (ClearUnknownKeys delete
  semantics), `lib.tables` (resolve-only refs).
- Mechanics: `meta.version` per file, chained
  `registerMigration(old,new,fn)`, additive-params-first,
  merge-onto-original preserving unknown keys,
  future-format blocks autosave, byte-compare skip, atomic
  write, one writer per key with unset-fill merge.
- CRUD + query surface over the store through the existing
  doc/component verbs; resolved-config snapshot per
  session/run for clients (never per-event round-trips).

## Acceptance

- Fresh project gets a valid manifest + defaults; unknown
  keys survive a round-trip; newer files refuse autosave;
  deletes propagate in scalar maps.
- Contract + api_spec regen; full suite + gate green.
