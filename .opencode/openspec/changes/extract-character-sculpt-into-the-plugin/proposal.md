# Proposal: extract-character-sculpt-into-the-plugin

## Why

The rig half of the character domain already left. `f651263` is in `main`, `plugin-character` v0.2.0
is published and installed, and its suite is green (258 collected). What is still in the base is the **sculpt**
half: the humanoid template, the skeleton derived from it, the scalp/hair-coverage gate, the canon
proportion table, and six `grimoire/character/` pages. While they stay, `SKILL.md`'s own rule —
"This pipeline names no domain. If a rule is domain-specific, it lives in that domain's plugin" — is
false about the one domain the repo is named for.

**A previous attempt at this shipped and was withdrawn.** `extract-character-into-its-own-plugin`
was applied across three repos and archived as APPLIED on 2026-09-12. It was un-archived the same
day. What it actually produced, measured:

- the content was **copied, not moved** — the base still defined `make_character_component_tree`,
  `derive_character_rig` and `apply_character_template` while the plugin held a second, unpinned copy;
- the plugin's copy had **no caller at all** — no CLI, no `domain.json` row, no `gates.json` row;
- `new_pre_spec_assessment.py` passed `args.character` to a function after the same slice deleted
  that argparse flag, so **step 2 of the base pipeline raised `AttributeError` on every profile**,
  generic included;
- **100 tests were deleted and landed nowhere**, hidden by a `COLLECTED_FLOOR` **261** below the
  collected count on `main` (1192 against 1453);
- the commits' own comments described work the same file contradicted.

Every one of those is a consequence of the same two omissions: the suite was never run (three
"Full suite and oracle green" tasks stayed unchecked while the change was archived), and the
partition was never reviewed though its task text said "before any code moves". This proposal
starts from `main` rather than repairing that branch, and its plan is built so neither omission is
possible without the change visibly failing.

## What Changes

The extraction mirrors `plugin-cs2`, which is the same move already done and shipped. cs2's
`emit_spec_augmentation.py` is the worked reference for how a domain contributes spec content, and
its own comment names this domain as the next case: *"this one writes cs2Finish and
envMapIntensity; the character domain writes rig, buildPasses and sculptPipeline."*

1. **`plugin-character` v0.3.0 takes the sculpt side** and reaches the parity of a full domain
   plugin — the shape `plugin-cs2` already has:
   - `tools/character_spec_template.py` — the humanoid component tree, the derived `RigSpec`, the
     character materials, build passes and feature targets, authored into an **empty scratch dict**
     the way `apply_cs2_template` does. It never reads the base's authored spec.
   - `tools/emit_spec_augmentation.py` — the `spec-augmentation-v1` artifact, partitioned into
     `specSections` / `assessmentPatch` / `qualityFloors` exactly as cs2's is.
   - `tools/humanoid_proportions.py` — the **only** module that moves. `scalp_field.py` and
     `scalp_exposure.py` stay in the base (D10, D11).
   - `grimoire/character/` — **four** of its six entries, moved. The two hair pages
     (`stylized_hair_threejs.md`, `threejs_hair_parameter_contract.json`) stay, and the directory is
     five `.md` files plus one `.json`, not "six pages".
   - `spec_search_profile.json` and `specCollection: "character"` — the plugin contributes no
     evidence corpus today; cs2 does, and the mandatory local-spec-search step runs on every profile.
   - **no** `gates.json` row is added. An earlier revision added one for the scalp-exposure gate;
     under D11 that gate stays in the base, where it already has a caller, so the row and the
     verdict-envelope wrapper it would have needed both cease to exist.
2. **One domain id.** `domain.json` declares `id: "character"` and always carries the nine rig
   steps. `animated-character` is withdrawn. A static build skips a rig step with a recorded reason,
   which the checklist already supports; a profile that omitted the Stage R gates entirely is how
   animation shipped broken in 1.5.1, and `SKILL.md:83` still says so.
3. **The base deletes the sculpt content** and keeps the mechanism: `stage5_rig/` (the library the
   emitters import), `chirality.py`, `morph_targets.py`, `uv_unwrap.py`, `extract_landmarks.py`, and
   the whole emitter, whose bone-track routing reads `rig.bones` presence rather than a domain name.
4. **Invoking the contribution needs no base change. Withdrawing a profile does.** These were one
   sentence in an earlier revision and the sentence was false; they are separated here because only
   one half survived review.
   - **True:** the `spec-authoring` step already passes `--augmentation spec-augmentation.json`
     (`workflow_state.py:40-43`); `setupAnchorBefore: local-spec-search` already lands a contributed
     step after `reference-admission` and before `pre-spec-assessment` and `spec-authoring`;
     `_anchor_index` fails loud on an unknown anchor; `new_sculpt_spec.py` already refuses when
     `--domain` is set and the artifact is missing. Nothing in that path changes.
   - **False:** `forge/state.py:37-40` builds `--profile` with `choices=` computed from the registry
     at argparse-construction time, so argparse rejects an unknown profile **before**
     `domain_profile()` can name the missing provider. Measured on `main`:
     `state.py init --profile cs2` → `invalid choice: 'cs2' (choose from 'generic', 'character')`.
     After slice 3, `--profile character` gets exactly that and names no provider, no plugin and no
     remedy. The carefully worded refusal at `domains/__init__.py:157-161` is reachable only on the
     **resume** path (`load_state` → `validate_state` → `domain_profile`), so init and resume today
     give two different messages and this change must stop treating them as one.
   - **Therefore the base changes**: `state.py` validates the profile itself instead of delegating
     to argparse `choices`, and a withdrawal table beside the registry teaches
     `animated-character → character` with its remedy. No harness release is required; the harness
     is genuinely untouched.

## Breaking changes

- **`--profile animated-character` is withdrawn.** `--profile character` now serves the whole track.
  A workspace initialised against the old name keeps it in its state file and must be re-initialised;
  `validate_state` refuses by design rather than silently downgrading, and the refusal names the
  provider.
- **`--profile character` requires the installed plugin.** Without it the profile must fail loud
  naming the missing provider — which is work this change performs, not behaviour it inherits: on
  `main` the init path answers `invalid choice` and names nothing (item 4 above). A character
  reference still reconstructs on the generic path, by inference, with no humanoid template and no
  rig — less exact is the intended trade.

## What this proves, and what it does not

The Why above rests the extension point's credibility on the base naming no domain. Stated
precisely, because the roadmap should not inherit the stronger claim: this change demonstrates that
a domain's **workflow and spec content** can move out of the base. That is real and it is most of
the value.

It does **not** demonstrate that the seam is general. A plugin contributes workflow —
`_ALLOWED` is seven keys and every one of them is a step, an anchor, a collection or a track. It
cannot contribute **schema**: not a component role, not a role-keyed validation rule, not a material
family. `specSections` looks like schema contribution and is not — it is content authored into
base-defined paths, accepted opaquely because "the base cannot validate a finish recipe or a rig".
The next domain to try will meet that half within the hour, and the registry's own docstring
promises generality it does not yet have. Follow-up 7.1 is that work.

## Capabilities

- **Modified: `spec-augmentation`** — the artifact is authored independently of the base's spec
  output, and the authority over each admitted section is stated rather than inferred.
- **Modified: `domain-step-contribution`** — a withdrawn profile fails loud and names its successor.
- **Modified: `domain-plugin-boundary`** — no in-repo domain module remains, and the asserted floor
  is the measured collected count.

No capability is ADDED. `domain-code-boundary` and `domain-emission-authority` entered the book from
the withdrawn change and already say what this change needs; re-declaring their requirements as
ADDED is what makes `openspec archive` throw (`specs-apply.js:212`).

## Affected code and systems

- `plugin-character` (from `v0.2.0`, tag `796dd9c`): new tools, `grimoire/`,
  `spec_search_profile.json`, `domain.json`, `gates.json`, `plugin.json` (0.3.0 + the
  `image → character-sculpt-spec` edge), CHANGELOG, SKILL.md, tests.
- `img2threejs` (from `main`, `6e60b5e`). Every file the tasks edit, since two revisions of this
  list were incomplete: `forge/state.py` (drop the argparse `choices=` so the registry's own refusal
  survives to the user), `forge/_shared/domains/__init__.py` (the withdrawal table and its remedy
  text), `forge/_shared/pipeline_routing.py` (drop the character track),
  `forge/stage2_spec/new_pre_spec_assessment.py` (the flag and **every reader of it**),
  `forge/stage3_build/generate_threejs_factory.py` (`BONE_TRACK_DOMAINS`),
  `forge/_shared/spec_augmentation.py` (the authority ruling);
  delete `forge/_shared/domains/character.py`,
  `forge/stage2_spec/humanoid_proportions.py` and four of the `grimoire/character/` pages; remove the character content from
  `new_sculpt_spec.py` and `validate_character_track` from `validate_sculpt_spec.py`; the domain-name
  sweep; the doc sweep; the floor, lowered with accounting.

## Scope

Both repos, the release, the install, and the acceptance captures. `img2-harness` is untouched.

## Non-scope (each with its reason)

- **Hair stays in the base — whole, and by decision (design D11, partition 1).** Not "for now" as a
  hedge: `scalp_field.py`, `scalp_exposure.py`, `hair_profile.py`, `hair_gate.py`,
  `extract_hair_evidence.py`, `docs/HAIR_PIPELINE.md` and the two hair grimoire pages all stay, and
  base strict validation is untouched. The reason is **not** that hair is generic — that argument was
  refuted in review, since it would have sent the hard channel of the hair gate to a *character*
  plugin and left a doll, a wig stand and a furred creature without it. The reason is that hair
  cannot leave **whole** until a plugin can contribute a component role, and a half-left hair
  subsystem is worse than either end. Follow-up 7.1 is that mechanism; hair is its first consumer.
  Measured effect on this change: 22 tests move rather than 100, one module rather than four, four
  grimoire pages rather than six, and the `gates.json` scalp row with its verdict-envelope wrapper
  ceases to exist rather than needing to be written.

- **`forge/stage5_rig/` stays.** `generate_threejs_factory.py` imports `rig_spec`, and
  `ARCHITECTURE.md:145-150` declares it the base library. The plugin's `rig_*.py` are deliberate
  duplicates pinned by `test_rig_spec_agreement.py`.
- **Harness multi-domain support.** Decided against on 2026-09-12 in favour of one id; revisit only
  if a static-only character profile is asked for again.
- **The `--cs2` flag and any CS2 residue.** Not this change's.

## Open questions

None. The two that were open are decided and recorded in `design.md`: one domain id (D1) and hair
staying in the base (D2).
