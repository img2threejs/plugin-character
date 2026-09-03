# Proposal: extract-animated-character

## Why

`plugin-character` (one commit, 2026-08-27) is a contract-conformant port of the v1.5.2
rigging/animation stack — 221 tests green against a linked core — but it is **inert**: no
`domain.json`, so it cannot contribute a checklist step. It predates the domain registry
(img2threejs PR #106) and the `rigSteps` registry vocabulary (added 2026-09-03). Meanwhile the base
carries an in-repo `animated-character` domain module, and the registry refuses two providers for
one id — so wiring the plugin and removing the module are one coupled motion.

Honesty notes this proposal owes from review: "221 green" is a self-consistency result, not parity
evidence — the 9 rig_spec drift-pin tests and 6 oracle-replay tests are exactly the ones that skip
without `IMG2THREEJS_BASE`/`IMG2_ORACLE_GLB`. And this is a **three-repo change**: the harness's
`DOMAIN_JSON_ALLOWED_KEYS` does not know `rigSteps` (a base↔harness vocabulary drift introduced
2026-09-03), so `img2 doctor` rejects the plugin's declaration until the harness ships first.

Requested outcome: `--profile animated-character` works as today, served from the installed plugin.

## What Changes

1. **img2-harness (prerequisite, ships first):** `rigSteps` joins `DOMAIN_JSON_ALLOWED_KEYS` with
   anchor-exempt row validation (rig rows have no anchor by design); `PLUGIN_CONTRACT.md` §10
   documents it; version bump (0.2.3) so `requires.harness` can express the dependency.
2. **plugin-character gains `domain.json`** (id `animated-character`):
   - `setupSteps`: the two character steps **verbatim base-relative** (the static `character`
     domain stays in-repo and owns those assets); a base-side agreement test pins the two paths.
   - `rigSteps`: the nine Stage R steps — same ids, same order, same load-bearing sequence. Command
     deviations from today's in-repo strings are **enumerated exhaustively in design.md D4** (the
     A2 allow-list): three rows keep their load-bearing caveat prose via the harness's sanctioned
     prose-row classification (`Run python3 {plugin_dir}/tools/…`); `mesh-freeze`/
     `mesh-parity-verify` are reworded doctor-legal (no `<preview>`, no `&&`) while still calling
     the base-owned browser bridge; `rig-gates` becomes
     `Run python3 {plugin_dir}/tools/gate_rigging.py --payload rig-gate-payload.json` — no
     `{workspace}` (illegal in domain.json), payload at the workspace root for parity with today's
     positional-path CLI; `rig-contract-read` reads `{plugin_dir}/reference/…` (byte-identical
     copies, now pinned by a drift test).
3. **plugin-character tool change:** `gate_rigging.py` gains `--payload <path>` — it is the one
   tool with no `--out` escape from `resolve_workspace`, which refuses checkout-shaped workspaces,
   and the base pipeline's workspace *is* a checkout. `anim_clip_features.py` is invoked with
   `--out clip-features.json` (deviation: today's base step is stdout-only; recorded in D4).
4. **Gate timing and blocking (the review's load-bearing finding):**
   - `run_gates.py` participation becomes **rig-aware**: a plugin whose domain declares `rigSteps`
     is not *due* until at least one rig step is `done`. Without this, the blocking `rigging` gate
     fires at `plugin-gates` (checklist index 24) against a payload produced at index 33, hard-
     failing every animated-character build — machine-proven by both reviewers.
   - `gates.json` `rigging` becomes **`blocking: false`** with a recorded re-block trigger: four of
     twelve checks have no producer yet (the plugin's own SKILL.md says so), `unevaluated` is
     honestly an `error`, so even correctly-sequenced the gate cannot return `pass` today; a
     blocking declaration would halt any post-rig sweep on an honest verdict. Reviewer A's dissent
     (recorded verdicts train people to ignore the gate) is noted, mitigated by rig-aware timing:
     verdicts are only recorded when due.
5. **The base removes `forge/_shared/domains/animated_character.py`** and:
   - guards `forge/state.py:32` (argparse-time `registered_domains()` falls back to a generic-only
     choice list on `DomainRegistryError`, letting `new_state` produce the real message) — without
     this, the both-present window kills the whole `state.py` CLI for **every** profile;
   - reworks `test_rig_workflow_steps.py` per the 21-method enumeration in design.md D5 (dispatcher
     tests keep a fixture — they test the mechanism; the six order tests move to the plugin, which
     owns the canonical order after the move; a skip-with-reason base test reads the *installed*
     plugin's order when present);
   - keeps `forge/stage5_rig/` (the factory imports `rig_spec`; every module has base tests —
     "delete now" was reviewed and rebutted) but **demotes it in docs**: every runnable
     `stage5_rig` example in the doc-sweep table (design D7) states the plugin as the checklist
     authority.
6. **Release plugin-character v0.2.0** (create CHANGELOG.md — it does not exist; bump SKILL.md
   frontmatter version with plugin.json; `requires.harness >= 0.2.3`), install, and capture the
   acceptance evidence A1–A10 (design D8), headed by: structural checklist parity byte-equal (A1),
   command diff exactly equal to the D4 allow-list (A2), doctor clean (A3), and `run_gates.py` at
   `plugin-gates` with the rig scope untouched neither stopping nor recording a `rigging` error (A4).

## Breaking changes

- Without the plugin installed, `--profile animated-character` fails loud naming available
  profiles. **An in-flight animated-character workspace is inoperable while its provider is absent
  and recovers unchanged when reinstalled** (`validate_state` refuses by design; round-trip pinned
  by acceptance A8). Rollback of the base deletion is `git revert`, not `img2 remove`.
- Persisted checklists do **not** migrate: a workspace initialized before the switch keeps base
  `forge/stage5_rig/...` commands and silently runs the base stack (the modules survive as a
  library). Stated in release notes with the remedy (re-init, or finish on the old stack).
- The `rigging` gate is no longer declared blocking (see §4; re-block trigger recorded).
- Command strings change per the D4 table; step ids, order, scopes, and the produced workspace
  files are unchanged except `clip-features.json` (new, was stdout-only).

## Capabilities

- **New capability: `animated-character-domain`** — the plugin's domain contribution: declaration
  validity, structural parity, the command-deviation allow-list, gate timing, fail-loud and
  round-trip behavior, order authority and its pins.
- **Modified capability: `character-rig-tooling`** — `gate_rigging.py --payload`, the `--out`
  short-circuit contract, `clip-features.json`, installed-copy evidence.

## Affected code and systems

- img2-harness: `bin/img2.mjs` (`DOMAIN_JSON_ALLOWED_KEYS`, anchor-exempt `checkSteps`),
  `docs/PLUGIN_CONTRACT.md`, version/CHANGELOG, tests.
- plugin-character: `domain.json` (new), `tools/gate_rigging.py` (`--payload`), `gates.json`
  (`blocking: false` + trigger comment), order tests (two-file pin), reference-doc drift pins,
  CHANGELOG.md (new), README/SKILL.md, `plugin.json` (0.2.0, `requires.harness`),
  `tests/test_suite_integrity.py` floor (227 → new count).
- img2threejs (branch `lab/cs2-plugin`, base commit stated at apply time): delete the domain
  module; `forge/state.py` guard; `forge/stage3_build/run_gates.py` rig-aware participation +
  test; `test_rig_workflow_steps.py` rework (21 methods enumerated in D5);
  `test_domain_registry.py` expectations; doc sweep per D7 table; CHANGELOG; floor (1192 → new).

## Scope

All three repos above, the release order harness → plugin → base, install, and acceptance captures
A1–A10.

## Non-scope (each with its reason)

- Extracting the static `character` domain (base flagship; its assets stay, pinned by the
  agreement test).
- Deleting base `forge/stage5_rig/` modules — rebutted in review (all have base tests; the factory
  imports `rig_spec`); demoted in docs instead, with a dedup trigger: when the factory's rig
  imports move behind a core API.
- `steps.json` rows — not parity-required, and the harness returns a plugin's whole steps.json per
  matched edge so "rows per edge" is not expressible; cs2 ships `[]` at v0.1.2. Debt trigger: when
  a rig edge becomes an emission target, revisit together with cs2's.
- A base-owned post-rig gate sweep row (reviewers' option (b), the better end state) — follow-up
  with trigger "when a base-owned post-rig gate row exists", at which point the sweep can re-run
  the rigging gate at the right phase and re-blocking becomes meaningful.
- Rewriting `runtime/scripts/export_mesh_buffers.mjs` (the `<preview>` token changes in the
  declaration, not the script).
- The harness's workspace-vs-checkout model (`resolve_workspace` refuses checkouts; this pipeline's
  workspace is one) — recorded debt; plugin-character is the first plugin to collide with it.

## Open questions

None. The five raised in review are decided in design.md: gate timing/blocking (D1, with A's
dissent recorded), parity over confinement (D3), order authority in the plugin with two-file pins
(D5), setupSteps base-relative with an agreement test (D6), prose-row classification for the
caveat strings (D4) with the fallback named if harness owners judge it abuse.
