# Design: extract-animated-character

## Context

The registry (img2threejs PR #106) treats in-repo domain modules and installed plugins' `domain.json`
identically; `rigSteps` (appended after FINAL, no anchor) entered the base registry vocabulary
2026-09-03 when v1.5.2's hardcoded `RIG_STEPS` was ported into
`forge/_shared/domains/animated_character.py`. plugin-character holds faithful ports of the same
v1.5.2 tools with its own tests, but no declarations. Both adversarial reviews machine-probed the
constraints: the harness's `domainJsonFindings()` and the base's real `new_state` scope order.

## Decisions

### D1 — Gate timing: rig-aware participation; blocking off until the gate can pass

**Problem (machine-proven):** `plugin-gates` is checklist index 24; the rig track is 25–33;
participation clause (i) counts `setupSteps`+`passSteps` only, so the blocking `rigging` gate becomes
involved at setup and errors at index 24 on a payload produced at index 33 — every build halts.

**Decision, part 1 (jointly recommended by both reviewers):** `run_gates.py` participation becomes
rig-aware — *a plugin whose domain declares `rigSteps` is not due until at least one rig step is
`done`*. Phrased as a participation rule (not "skip the sweep at index 24") so a hand-run
`run_gates.py` after the rig track evaluates the gate against a real payload. Owner:
`forge/stage3_build/run_gates.py` (`domain_step_ids` gains a rig-aware clause) + a test.

**Decision, part 2 (lead ruling on the one residual disagreement):** `gates.json` `rigging` becomes
`blocking: false` with a recorded re-block trigger. Reviewer B's H4 point is decisive: four of
twelve checks have no producer (the plugin's SKILL.md says so), `unevaluated` honestly reports
`error`, so *correct sequencing still yields a guaranteed halt* — no fix leaving `blocking: true`
can ship a green build. Reviewer A's dissent — recorded non-pass verdicts train people to ignore
the gate — is noted; mitigation: with rig-aware participation, verdicts are only recorded when due
(post-rig), where an honest fail SHOULD be visible. Re-block trigger, written into gates.json as a
comment-equivalent (a `"note"` is not schema; it goes in CHANGELOG + SKILL.md): *re-enable blocking
when the four producer-less checks gain producers and the gate can return `pass` on a healthy rig.*
The jointly-named better end state — a base-owned post-rig gate sweep row — is a tracked follow-up
(Non-scope), since `_ALLOWED` deliberately has no `finalSteps` and the row must be base-owned.

### D2 — Three repos, ordered: harness → plugin → base

`DOMAIN_JSON_ALLOWED_KEYS` (img2.mjs:879) lacks `rigSteps`; doctor errors on the plugin. The comment
above that set claims it mirrors the base `_ALLOWED` "exactly" — the 2026-09-03 base change broke
that silently; this change repairs the drift rather than deepening it. Harness work: add the key;
wire anchor-exempt row validation (a naive `checkSteps('rigSteps','rigAnchorBefore')` would demand
an anchor that must not exist); amend `PLUGIN_CONTRACT.md` §10; bump to 0.2.3 with CHANGELOG; the
plugin's `requires.harness` becomes `>=0.2.3`. Without the wiring, rig rows would be silently
unvalidated — worse than today's loud rejection.

### D3 — Parity over confinement (decided; confinement is currently impossible)

`{workspace}` is not domain.json vocabulary (KeyError at render), and `resolve_workspace(None)` →
cwd → the base checkout → refused on the SKILL.md marker. No confined path works from this pipeline
today. Contract: every plugin rig step passes explicit `--out <name>` (the `--out` short-circuit
avoids `resolve_workspace`); `gate_rigging.py` gains `--payload <path>` (the one tool with no
escape); the cwd contract is stated as it is — *rig steps run from the base checkout, which is also
the workspace*. Recorded debt: the harness confinement model vs the checkout-as-workspace reality;
plugin-character is the first plugin to collide (zero cs2 tools call `resolve_workspace`). This
also dissolves the steps.json artifact-location contradiction (D9 drops steps.json).

### D4 — The command deviation table (the A2 allow-list; verbatim, exhaustive)

Setup steps: verbatim today's strings (base-relative, see D6). Rig rows — every deviation from
`forge/_shared/domains/animated_character.py` enumerated; anything not on this list fails A2:

| id | new command string (verbatim) | deviation class |
|---|---|---|
| rig-contract-read | `Read {plugin_dir}/reference/animation-contract.md and {plugin_dir}/reference/character-rigging-animation-1.5.2.md completely` | docs from plugin (byte-identical, drift-pinned) |
| glb-rig-reference | `Run python3 {plugin_dir}/tools/rig_glb_reference.py {reference} --out glb-rig.json (skeleton, skin joint order, inverse binds and clips read FROM the GLB; skip with a reason only when there is no GLB)` | prose-prefix + tool retarget |
| mesh-repair | *(unchanged)* | — |
| mesh-freeze | `Export the mesh buffers with node runtime/scripts/export_mesh_buffers.mjs --url PREVIEW_URL --out meshes.json, then run python3 {plugin_dir}/tools/rig_mesh_parity.py freeze meshes.json --out mesh-manifest.json` | prose rewrite: no `<preview>`, no `&&`; base bridge kept |
| rig-payload-validate | `Run python3 {plugin_dir}/tools/rig_validate_payload.py --payload rig-payload.json (structural payload integrity ONLY -- never pose stress or likeness; a sculpt spec is NOT a rig payload, they are different schemas)` | prose-prefix + retarget; the base-test-pinned string survives |
| rig-bind | *(unchanged)* | — |
| mesh-parity-verify | `Export the post-bind buffers with node runtime/scripts/export_mesh_buffers.mjs --url PREVIEW_URL --out meshes-after.json, then run python3 {plugin_dir}/tools/rig_mesh_parity.py verify mesh-manifest.json meshes-after.json` | as mesh-freeze |
| clip-measure | `Run python3 {plugin_dir}/tools/anim_clip_features.py sampled-clips.json --out clip-features.json (measure, classify, name, and decide loop from poseReturn)` | prose-prefix + retarget + **new artifact** `clip-features.json` (base was stdout-only; `--out` is required because bare cwd resolution would hit the checkout refusal) |
| rig-gates | `Run python3 {plugin_dir}/tools/gate_rigging.py --payload rig-gate-payload.json (G1-G10; an unevaluated gate is not a pass)` | prose-prefix + `--payload` replaces the positional path; payload stays at the workspace root for parity |

The prose-row classification (`Run …` leading token → metachar hardening skipped) is the harness's
own sanctioned reading (img2.mjs's cookbook cites a parenthesised prose setupStep); it is what lets
the load-bearing caveat prose survive doctor, and it keeps the base test pinning
`"structural payload integrity ONLY"` green. Angle-bracket and placeholder checks still apply to
prose rows — hence `PREVIEW_URL`. If harness owners judge the reading abuse, the recorded fallback
is a schema `note` field (a second harness change).

### D5 — Order authority and the test split

Canonical ordered rig list: **the plugin's `domain.json`** (after deletion it is the only place the
real order exists). Plugin-side: port the six `StageROrderIsLoadBearing` assertions, asserting
`domain.json` ids against a *separately declared* expected list in the test file — a real two-file
pin, the repo's existing drift-pin pattern. The module's 20-line freeze-before-bind rationale moves
to those tests' docstrings and the plugin SKILL.md. Base-side `test_rig_workflow_steps.py`
(21 methods, per-method disposition recorded in tasks): `TheDispatcherActuallyReachesThem` (5) keeps
a fixture — those test the splice/dispatch mechanism, for which a fixture is the right input; the
six order tests are dropped from base with a comment naming the plugin as order authority; plus one
new base test that reads the **installed** plugin's `domain.json` when present (skip-with-reason
otherwise) asserting `repair < freeze < bind < parity-verify`. `test_domain_registry.py`
expectations return to `["character"]`.

### D6 — setupSteps stay base-relative, pinned by an agreement test

Copying `grimoire/character/*` and `extract_landmarks.py` into the plugin would fork the static
character domain's assets. Instead the two command strings stay verbatim base-relative, and a
base-side test asserts the two referenced paths exist — turning an unenforceable convention into a
tripwire. Doctor cannot check file existence on domain rows (documented at img2.mjs:907-909), so
the base test is the enforcement point. The `reference/` doc copies get a plugin-side drift-pin
against a recorded hash, since the base keeps its own copies.

### D7 — Base residue and the doc sweep

`forge/stage5_rig/` stays: the factory imports `rig_spec`, and the review rebutted "no test" —
every module has a dedicated base test file. Demotion, not deletion: every runnable example naming
`stage5_rig` or `--profile animated-character` states the plugin as the checklist authority /
prerequisite. The sweep table (from review, verified line-anchored): README.md:94,140,270-272;
SKILL.md:65,77,81-83,300-303; docs/GLB_ANIMATED_CHARACTER_PROMPT.md (8 invocations);
docs/STAGE_R_TEST_PLAN.md; docs/STAGE_R_BACKLOG.md:96,251; docs/standard-prompts/build.md:21;
docs/ARCHITECTURE.md:145-152. Dedup trigger recorded: when the factory's rig imports move behind a
core API, base copies shrink to what the emitter needs.

**Known, accepted residue:** an in-flight workspace initialized before the switch keeps frozen
base-path commands and silently runs the base stack (checklists never re-splice; `_splice` runs only
in `new_state`). With the modules kept, that is silent divergence, not breakage — stated in release
notes with the remedy (re-init, or finish the run on the old stack). This is the deliberate
counterpart of keeping the library (deleting it would turn stale workspaces into loud breakage —
the reviewers noted the two options pull in opposite directions; we choose silent-with-release-note).

### D8 — Failure windows, sequencing, and the state.py guard

Mixed states (from review, verified):

| state | behavior |
|---|---|
| plugin installed + harness < 0.2.3 | pipeline works (base `_ALLOWED` has rigSteps); doctor red — confusing half-state, avoided by release order |
| module still present + plugin installed | duplicate-id refusal from `registered_domains()` — **and `state.py:32` constructs choices from it at argparse time, killing every subcommand for every profile**. In scope: guard it (catch `DomainRegistryError` → generic-only choices; `new_state` then names the real error), the exact remedy `targets.py:14-19` already ruled for this shape |
| module deleted + plugin absent | fail-loud naming available profiles (designed); an in-flight workspace is inoperable until reinstall and **recovers unchanged** (round-trip pinned by A8) |
| rollback | `img2 remove character` restores nothing base-side; rollback of the deletion is `git revert`. Stated, not implied |

Release order: **harness 0.2.3 → plugin v0.2.0 (+install) → base branch change**. Acceptance
criteria A1–A10 are Reviewer B's list adopted verbatim (structural parity byte-equal; command diff
== D4 table; doctor clean; no gate stop at plugin-gates pre-rig; gate evaluated once with a real
payload; dispatcher drain on the installed plugin; fail-loud absent; removal round-trip; both suites
green with drift pins actually running via `IMG2THREEJS_BASE`; doc sweep grep).

## Gap matrix (debate outcome)

| Finding | Decision | Landed in |
|---|---|---|
| A-H1/B-H2 harness vocabulary | in scope, ships first, 0.2.3 | D2, tasks §1 |
| A-H2/B-H3 doctor-illegal rows (6) | prose-row classification + 3 rewrites; verbatim table | D4 |
| A-H3/B-H1 gate fires pre-rig | rig-aware participation | D1 |
| A-H4 gate cannot pass (4/12 no producer) | blocking:false + re-block trigger (lead ruling; A dissent recorded) | D1 |
| A-H5/B-M6 frozen checklists, false "invisible" claim | honesty rewrite; silent-divergence accepted w/ release note | D7, proposal Breaking |
| A-H6/B-M7 both-present kills all profiles | state.py guard in scope + sequencing table | D8 |
| A-M1/B-M3/M4 confinement vs parity | parity; gate --payload; cwd contract stated; debt logged | D3 |
| A-M2 base-relative setupSteps | keep + base agreement test (B's third option) | D6 |
| A-M3/B-M5 order tautology + 21-method rework | plugin owns order (two-file pin); base keeps mechanism tests on fixture; installed-order skip test | D5 |
| A-M4/B-L3 doc copies drift | plugin-side drift pin | D6 |
| A-M5/B-M2 doc sweep | A's superset table adopted | D7 |
| A-M6 delete stage5_rig | **rebutted by B** (all modules tested; factory imports rig_spec) — demote, don't delete | D7 |
| B-H4 parity evidence overclaim | Why rewritten; A9 requires drift pins to RUN | proposal Why, D8 |
| B-H5 clip-measure/rig-gates different programs | deviations enumerated (new artifact; --payload) | D4 |
| B-M1 payload-path docs | SKILL/docs tasks incl. payload location | tasks |
| B-M8 CHANGELOG missing, requires.harness | create; bump to >=0.2.3 | tasks |
| B-M9 bootstrap/CI | premise withdrawn per A-L4 (installed tools/_img2_local.py); tasks = installed-copy evidence + CI env + both COLLECTED_FLOORs (A corrected B: base 1192, plugin 227) | D8, tasks |
| A-L1/B-L1 steps.json | dropped from scope; cs2 `[]` debt trigger | D9/proposal Non-scope |
