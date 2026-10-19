# Design: extract-character-sculpt-into-the-plugin

Anchored to `img2threejs` `main` @ `6e60b5e`, `plugin-character` `v0.2.0` @ `796dd9c`,
`img2-harness` — **actually on `apply/slice-4-contract-clause` @ `4760153` with an uncommitted edit
to `tests/cli.e2e.test.mjs`**, not `78c6299` as an earlier revision recorded. That branch carries
`CONTRACT_REVISION = 15` and §15, both authored by the **withdrawn** change (§15's own heading reads
"slice 4 of extract-character-into-its-own-plugin"); at `78c6299` the revision is 14 and §15 does
not exist. §15's "the base SHALL NOT import plugin code" is a rule this change ought to be
conforming to, and it presently lives only on an unmerged branch of the thing being abandoned —
see follow-up 7.2. Measured 2026-09-12.

Baseline that every later measurement is compared against:

```
IMG2_HOME=$(mktemp -d) pytest forge/tests --collect-only -q  →  1453 collected   (main; 1387 passed, 66 skipped)
IMG2_HOME=$HOME/.img2  pytest tests --collect-only -q        →   258 collected   (plugin v0.2.0; 226 passed, 32 skipped)
```

Both figures are the **collected** count, which is the only one a floor may be set from. An earlier
revision of this document recorded `1387` (the base's *passed* count) and `235` (the *declared
floor* at `test_suite_integrity.py:35`, transcribed and mislabelled as measured). Each error would
have produced exactly the slack this change legislates against — 66 and 23 respectively — which is
why the baseline itself is now stated as a `--collect-only` run and nothing else.

**`plugin-character` v0.2.0's own floor is 23 short**: 235 declared against 258 collected. Task 1.8
corrects it rather than raising from it.

---

## D1 — One domain id: `character`, rig always present

**Decided.** `domain.json` declares `id: "character"` with `setupSteps`, `passSteps` and the nine
`rigSteps`. `animated-character` is withdrawn.

The constraint is real: `domain.json` admits one scalar `id` (`img2.mjs:940`, mirrored by
`domains/__init__.py:_ALLOWED`), and the registry refuses two providers for one id. So "both
capabilities" has three shapes — one id carrying both, a harness change admitting two, or a second
plugin. The first is chosen, and not only because it is cheapest:

- `SKILL.md:83` describes the rig-less `character` profile as the one where "the Stage R gates are
  absent and the build completes without ever running them, which is how animation used to ship
  broken". A profile whose distinguishing feature is the absence of gates is not a feature worth
  preserving under its own name.
- The checklist already has the escape: a step is marked `skipped` with a `--reason`, and silent
  omission is forbidden. A static build therefore records *why* it has no rig, which is strictly
  more information than the old profile produced.
- It keeps the harness off the critical path. The only alternative that preserves two profile names
  needs a harness release plus a mirrored `_ALLOWED` change in the base, and a coordinated
  three-repo release order is what the withdrawn attempt could not hold.

Cost, stated: `--profile animated-character` stops resolving. `validate_state` refuses a workspace
naming an absent provider by design, so an in-flight run fails loud rather than silently downgrading.
The release note carries the re-init instruction.

## D2 — Hair stays in the base

**Decided.** The leaving set is the sculpt content that is unambiguously character. Hair is not.

| Fact | Where |
|---|---|
| `from hair_profile import REJECTED_HAIR_PRIMITIVES, validate_hair_profile` at module scope | `validate_sculpt_spec.py:18` |
| `validate_hair_profile(...)` inside the base's strict validation | `validate_sculpt_spec.py:2820` |
| `STAND_PROUD_EXPECTED_ROLES = {"hair"}` | `validate_sculpt_spec.py:64` |
| role-keyed hair checks | `validate_sculpt_spec.py:470`, `:1549` |

`role: "hair"` is a role in the **base** schema and `standProud` is enforced by the base generator.
Extracting hair therefore changes base strict validation, which is a different risk from moving a
self-contained module, and it gets its own change — see the rewritten follow-up 7.1, which names the
mechanism that must exist first.

**The reasoning an earlier revision gave for this was wrong, and is corrected here rather than
quietly dropped.** It argued hair stays because "a doll, a wig stand or a furred creature carries
hair and is not a character" — and then sent `scalp_exposure.py`, the **hard** channel of that very
gate (`SKILL.md:293`, `:362`), to a *character* plugin. Exactly those non-character subjects would
lose their hard channel, and `hair_gate.py:120-124` would report it on every one of their runs:
*"scalpExposure was not supplied; a pixel comparison cannot reliably see a bald patch, so this
verdict is incomplete. Run forge/stage4_review/scalp_exposure.py"* — naming a path the change had
deleted. The partition cut the hair subsystem along the line its own rationale rejects.

D11 partition 1 repairs the module list. The honest reason hair stays is **not** that hair is
generic: it is that the base cannot yet be told what a role obliges, so hair cannot leave whole, and
a half-left hair subsystem is worse than either end. And the base does still name `hair` — at
`STAND_PROUD_EXPECTED_ROLES`, `:470`, `:1549`, `REJECTED_HAIR_PRIMITIVES`, `material_physics.py:210`,
`geodesic_skinning.py:66` and `orchestrate_passes.py:138`. This change discharges "the pipeline names
no domain" for exactly one name. That is worth doing and worth stating accurately; it is not the rule
satisfied.

`scalp_exposure.py` **stays too**, under D11 partition 1 — an earlier revision of this section had
it leaving, which was the very split the paragraph above refutes. The coupling analysis stands and is
worth keeping for 7.1: `hair_gate.py` imports only `extract_hair_evidence` and takes
`scalp_exposure_report` as a **parameter** (`hair_gate.py:104`), so when hair does leave, the
dependency is data rather than code and only a docstring path at `:123` moves with it.

## D3 — The template authors into an empty scratch, never into the base's spec

**This is the correction that makes the design simple, and it is not novel — it is what cs2 does.**

`apply_cs2_template(scratch, …)` receives an empty dict and assigns wholesale, including
`spec["materials"] = [_cs2_finish_material(...), _cs2_substrate_material(), _cs2_hidden_material()]`
(`cs2_spec_template.py:417`). Each material it writes is self-contained — its own `shaderModel`,
`textureResolution`, `textureProjection`, `albedo`, `roughness`.

The base's current `apply_character_template` does the opposite: it seeds each character material
from the base-authored `base` material (`existing.get("base", {})` at `:1140`). That inheritance is
what made the earlier attempt reach for the authored spec as an input, which in turn needed a second
`spec-authoring` run to merge the result.

**Making the materials self-contained is necessary but NOT sufficient.** Three further reads of the
incoming spec were missed in an earlier revision of this section, all measured:

1. **`materials` is a MERGE, not a replacement, and the result is nine — not eight.** `:1140` seeds
   `existing` from `spec["materials"]` and `:1158` writes back `list(existing.values())`, so today's
   output is `['base', 'hidden', 'skin', 'hair', 'shirt', 'pants', 'shoes', 'eye', 'lips']` — the
   base's own `base` material first, in base-first insertion order. With accessories it is
   **thirteen**, not eleven: `CHARACTER_ACCESSORY_MATERIALS` has **four** entries. Since
   `specSections` assigns wholesale (`spec_augmentation.py:87`), a contributed `materials` array
   REPLACES the base's and drops `base`. The plugin must therefore re-author a base-equivalent
   default as part of its own list. This is this change's own delta — "the merge SHALL NOT be relied
   on to preserve fields the contributed value omitted" — one level up: **elements of a list, not
   fields of an object**, and the delta's scenario does not reach that level.
2. **`primaryDomain` is a write into `preSpecAssessment`.** `:1139` sets
   `objectClass["primaryDomain"] = "character"`, and `validate_sculpt_spec.py:904` hard-errors
   without it. It travels as `assessmentPatch.objectClass` — that route is open, since the merge
   refuses only `objectClass.domain` — but an earlier revision named only the canon anatomy as
   travelling that way.
3. **`include_accessories` loses its switch.** Slice 3 deletes `--accessories` with no plugin-side
   replacement named. The plugin needs its own way to select the accessory set, or the capability
   silently disappears with the flag.

Consequences, all simplifications:

- `emit_spec_augmentation.py` takes no `--spec`.
- The step is an ordinary `setupStep`; there is no re-run of `spec-authoring`.
- The plugin cannot write the base's spec even by accident, which is what `spec-augmentation`
  requires ("the base SHALL pull; a plugin SHALL NOT push").

`specSections` is a wholesale assignment (`spec[key] = value`), so a section the template
**updates** rather than replaces must be authored complete. For this domain those sections are
`componentTree`, `rig`, `materials`, `buildPasses`, `featureReviewTargets` and `sculptPipeline` —
the exact list cs2's own `BASE_OWNED` comment predicted.

## D4 — The anchor, and why

`setupAnchorBefore: "local-spec-search"`, matching cs2 and the cookbook's Scenario 1. That index
places the contributed steps after `reference-admission` (so `admission.json` and `probe.json`
exist) and before `spec-authoring` (so authoring can pull the artifact).

**The anatomy source is decided here, not left to the anchor.** `new_pre_spec_assessment.py`
authors no `anatomy` at all — zero occurrences of the word — while `apply_character_template`
consumes `assessment["preSpecAssessment"]["anatomy"]` (`new_sculpt_spec.py:1945-1948`), which the
agent fills between the landmark step and authoring. At this anchor `assessment.json` does not exist
yet, so the plugin reads **`anatomy.json` from its own `character-landmarks` step**. Arguably better
— machine evidence rather than a transcription — but it silently redefines "for the same anatomy" in
task 1.2's byte-identity test, so it is stated rather than inherited.

An earlier revision also claimed the position mattered so that "the assessment sees the contract".
**That reason is false** — nothing makes `new_pre_spec_assessment.py` read the artifact; outside
tests, `spec-augmentation` appears only at `workflow_state.py:42`, `new_sculpt_spec.py:13` and
`:1966`, and in `spec_augmentation.py` itself. The only real constraint is *before `spec-authoring`, which is the only step that reads the
artifact*. The conclusion was right and the reason was invented, which is worse than having no
reason: a wrong reason gets reused. An anchor naming an unknown base step fails loud —
`WorkflowStateError` — rather than appending at the end, where a setup step would land after its
own consumers.

`passAnchorBefore: "ai-review-recorded"` for the scalp gate, matching cs2's review step: it runs on
geometry each pass, and after a render it would be reporting on a picture of the defect instead of
the defect.

## D5 — What the base keeps, and why each stays

Manifest-level capability edges are kept **deliberately**. §13 resolves three distinct edges
independently and `--plugin <id>` disambiguates, so the multi-edge manifest is legal. §5 notes that
the documented upgrade path for a multi-edge provider is per-step `provides` in `steps.json`, and
this plugin ships no `steps.json` — staying with manifest-level edges is a choice, not an oversight.
The edge count drives a doctor WARN mandated by §12, which is why the doctor bar is zero FAILs and
not zero findings.


| Stays | Reason |
|---|---|
| `forge/stage5_rig/` (11 modules) | `generate_threejs_factory.py:2106` imports `rig_spec`; `ARCHITECTURE.md:145-150` declares it the base library. The plugin's `rig_*.py` are deliberate duplicates pinned by `test_rig_spec_agreement.py`. |
| `_shared/chirality.py` | `label_glb_nodes.py:208` cross-references `CHARACTER_LEFT_SIGN` as a shared handedness convention. A coordinate-system fact, not anatomy. |
| `_shared/morph_targets.py`, `_shared/uv_unwrap.py` | Nothing humanoid in either. |
| `stage1_intake/extract_landmarks.py` | Generic intake; the plugin's `character-landmarks` step invokes it base-relative, as it does today. |
| the whole emitter | Role-blind and payload-driven — **after 3.4**, not today. `rig_is_bone_track()` at `:1926` tests `primaryDomain not in BONE_TRACK_DOMAINS` **first** and only then `rig.bones`, so an earlier revision of this row described the post-deletion state as though it were `main`. What IS true on `main`, and was never claimed: the emitter contains **zero** occurrences of `"hair"` and reads `standProud` by key presence at `:2399`, so it never knew the role. |
| hair | D2. |

**The recurring error has a name: deriving from what something is CALLED instead of from what it
references.** Three instances, all caught by review, none by the author:

| | Derived from | Should have been derived from |
|---|---|---|
| `scalp_field.py` classified as content (D10) | its docstring, which recounts a hair defect as *motivation* | its code — `ScalpField(rings)` over ellipse rings |
| `test_rigid_hair_binding` moved | its filename saying "hair" | its import — `geodesic_skinning`, a module that stays |
| `test_stand_proud_emission` left in place | its filename not saying "hair" | its function-scoped import of `scalp_field` |
| `grimoire/character/` moved whole | the **directory** name | its contents — two of the six are hair pages |

Every one of them was a `grep -n "^from\|^import\|sys.path"` — or, for the last, an `ls` — away.
Four instances in one review. The directory case is the same error in documentation form: a folder
called `character` is not an argument that everything inside it is character. Slice 0's sweep therefore covers
`forge/tests/` in both directions and the disposition list is a **derivation**, not a judgement
recorded as one.

**A caution this change earned twice.** Two claims about the emitter were put to the reviewers: that
`rig_is_bone_track` routes on payload presence (confidently asserted here — false on `main`), and
nothing at all about whether the generator knows `role: "hair"` (unasserted — and true). The
intuition was unreliable in **both** directions, so slice 0 verifies the "stays" column the same way
it verifies the leaving set, rather than treating it as the half that needs no evidence.

## D6 — Verification, designed so the failure mode cannot repeat

The withdrawn attempt failed on exactly two things, and each gets a mechanism here rather than a
task that can be left unticked.

**The suite runs at the end of every slice, and its numbers go in the commit message.** Not a
checkbox — a number a reader can re-derive. A slice whose commit message carries no measurement is
not done. The command is the one the cookbook calls "not a formality":

```bash
IMG2_HOME=$(mktemp -d) python3 -m pytest forge/tests -q --continue-on-collection-errors
```

**The suite RUN is the primary gate; the floor is a second check for a different loss.** These
catch different things and neither substitutes for the other. Measured on the abandoned branch:
`test_stand_proud_emission.py` imports `scalp_field` **inside two test bodies**, so when the module
left, `--collect-only` still reported **31 tests collected** — no `_FailedTest` is synthesised for a
function-local import — while the run reported `2 failed`. A floor set to the measured count would
not have caught it. The floor sees tests that stop being *collected*; only running the suite sees
tests that break while still being collected, and the withdrawn attempt lost tests both ways.

**The floor is the measured collected count, with the arithmetic written down.** `COLLECTED_FLOOR`
is **1192** against **1453** collected on `main` — **261 of slack**, and 100 deleted tests fit
inside it with room to spare. (1361 is the count on the abandoned branch *after* the loss; the slack
that let the loss through was the 261 that existed before it.) Because the slack is that wide, the
floor after this extraction moves **up**, ~1192 → ~1353, not down. Every floor move records
`before − moved + added = after`, both sides measured in the same sitting.

**The oracle covers authoring, not only emission.** There is no character oracle on `main` at all —
`test_character_oracle_replay.py` exists only on the abandoned branch, and an earlier revision of
this document described it as existing today. This change freezes **two**: an emission oracle
(frozen spec → `generate()`) and an **authoring** oracle (assessment → authored spec). Only the
second can see this extraction regress; an emission oracle replays base mechanism that never moves,
so it stays green with the entire authoring side gone.

**The authoring oracle lives in the PLUGIN's suite from the moment it is frozen** — frozen from
`main` before anything moves, run against the base checkout through `IMG2THREEJS_BASE` during slice
0, and against the plugin thereafter. Putting it in `forge/tests/` would make it a contradiction:
the `domain-plugin-boundary` delta requires that deleting the moved authoring makes it fail, while
task 3.10 requires the base suite to have zero failures after exactly that deletion. Its removal
from the base is a named, expected line in slice 3's floor arithmetic, not a test "reworked" into
silence.

**The partition review gates the base deletion, and is scheduled first.** Slice 0, not slice 7.

**The rule that decides what belongs in the base suite at all:**

> A test in the base suite must assert a property of the **shipped artifact** that remains true after
> the change archives. Anything whose truth expires when the change closes belongs on the branch's
> CI or in the task list, not in `forge/tests`.

**So the gate is the partition's CONCLUSIONS, not its review.** An earlier revision of this design
made "the review happened" a base test. That is withdrawn: a test in `forge/tests/` pointing at
`openspec/changes/<name>/review/` breaks or is deleted when the change archives, so the enforcement
evaporates exactly when nobody is watching — **a gate that expires silently is worse than a
checkbox, because it looks like a gate** — and it is satisfiable by writing the file, which is the
withdrawn attempt's signature failure wearing a different costume. What is asserted instead is a
property of the shipped repo: no module under `forge/` references any name in the leaving set, and
every symbol in the partition's stays column still resolves. It survives archive, needs no allowlist
upkeep, and it is the only check that catches the two losses the floor and the run both miss — a
staying test importing a leaving module, and a leaving test whose subject stays.

## D8 — The base changes this needs, named

An earlier revision claimed the base needed no change. Two do, and both are on the critical path.

**`forge/state.py` must stop delegating profile validation to argparse.** `:37-40` computes
`choices=` from `registered_domains()` at parser-construction time, so `init` answers
`invalid choice: 'x' (choose from 'generic', 'character')` and the registry's own message — which
names the missing provider and the remedy — is never reached. `init` and **resume** therefore give
different answers for the same bad profile today: resume goes through
`load_state → validate_state → domain_profile` and does print the good message. The fix is for
`state.py` to accept any string and let `new_state()` refuse, so one refusal serves both paths.
The comment already at `state.py:31` ("new_state() re-checks and names the available set on a bad
value") describes the behaviour this restores — it is currently contradicted by its own file.

**A withdrawal table must live beside the registry.** `animated-character → character`, with the
remedy. `domain-step-contribution`'s new scenarios require the refusal to name the withdrawn
identifier, name its successor and state the remedy; today's message names the identifier and an
availability list, from which a user cannot tell "your plugin is missing" from "this profile no
longer exists". Worse, it says *"Install the domain plugin that provides it"* — after this change
nobody provides it, so a user who obeys installs v0.3.0 and gets the same message again.

Neither is a harness change. The harness is genuinely untouched.

## D9 — The in-repo second consumer, and why it may now go

`forge/_shared/domains/character.py`'s docstring says character stays in-repo so "the seam has two
consumers from the day it exists", and `test_domain_registry.py::test_both_registry_sources_register_hermetically`
enforces it, commented "A seam with one consumer is a rename, so both sources are exercised."

That reasoning was correct when written and is now spent: the seam has **three** plugin consumers
(cs2, character, img2glb — hello-cube a fourth), so the in-repo source is no longer what keeps it
honest. `domain-plugin-boundary` states the successor rule directly — "The consumers MAY both be
out-of-repo… and SHALL NOT be read as requiring an in-repo domain to be retained for the purpose."

What replaces the hermetic test is not nothing: it becomes a test that two INSTALLED plugins resolve
through the same mechanism with no in-repo branch for either. Task 3.8 names that replacement rather
than simply deleting the old assertion.

## D10 — `scalp_field.py` stays in the base. The withdrawn attempt's partition got this backwards

**Provisional; an architect's second read is outstanding.** The evidence is strong enough to record
the decision now rather than leave the question silent.

`forge/tests/test_stand_proud_emission.py:204,228` pins the base's **emitted TypeScript**
`ringStackDistance` (`generate_threejs_factory.py:1429`) against the Python `ScalpField` over a
~2000-point sweep plus a sign-agreement check. The emitter stays (D5). If `scalp_field.py` leaves,
that pin breaks — and it broke exactly this way on the abandoned branch, invisibly to the floor.

Applying the partition's own test — *what does the symbol KNOW?* — to the emitted helper:

> `// Signed distance to a stack of ellipse rings. Negative inside, positive outside.`
> `// the failure being prevented is a component sinking into the one beneath it and rendering as a`
> `// bare patch.`

**The directory is not evidence either.** `grimoire/character/` is five pages and a JSON file, not
"six pages" as an earlier revision said, and two of them — `stylized_hair_threejs.md` and
`threejs_hair_parameter_contract.json`, cross-referenced from `SKILL.md:163-164` and from
`stylized_hair_threejs.md:151` — are **hair**. Under D11 partition 1 they stay and the moving set is
**four**. Assign them by content, like everything else.

It knows ellipse rings and signed distance. It is driven by `standProud`, a **base schema field**
(`STAND_PROUD_EXPECTED_ROLES` lives in the base validator, and D2 already keeps hair there). Nothing
in it is humanoid.

So the split runs between the **maths** and the **gate**:

| | Classification | Disposition |
|---|---|---|
| `_shared/scalp_field.py` — signed distance to a ring stack | **mechanism**; the reference implementation the emitter is ported from and pinned against | **stays** (rename deferred with hair — D11) |
| `stage4_review/scalp_exposure.py` — "find bald patches before anything is rendered" | **content**, but **hair's** content, not character's | **stays** under D11 partition 1 |

The withdrawn attempt's `partition.md` classified `scalp_field.py` as "content (entire file)",
reasoning from its docstring — which recounts a hair defect as *motivation*. The docstring says why
it was written; the code says what it knows. That is the distinction the partition's own test exists
to draw, and it was drawn the wrong way once already.

**The module does not name a domain — its filename does.** Its content is
`ScalpField(rings)` over `[[y, rx, rz, zc], ...]`: a signed distance to a stack of ellipse rings,
with nothing humanoid in it. That is precisely D5's stated reason for keeping `morph_targets.py`,
`uv_unwrap.py` and `CHARACTER_LEFT_SIGN` ("a coordinate-system fact, not anatomy"). So it stays. The rename to
`_shared/ring_stack_field.py` / `RingStackField` — which would *strengthen* "the base names no
domain" by removing a domain-flavoured name rather than leaving one — is **deferred to 7.1 with
hair**, per D11: under partition 1 the base keeps the whole hair subsystem, and renaming one member
of it for a rule this partition defers would make the group less legible, not more. `docs/ARCHITECTURE.md:165` describes it as "signed distance to a
**skull**", which is the same domain flavour in prose and is reworded with it.

The rename surface, measured when the rename was still live: `scalp_exposure.py`,
`test_scalp_exposure.py`, `test_scalp_field.py`, `test_stand_proud_emission.py` and
`ARCHITECTURE.md:165` — **all of which stay** under D11 partition 1, which is why the rename is
deferred to 7.1 rather than performed here. `CHANGELOG.md`
entries are historical and stay as written.

The plugin's scalp gate then carries its own copy as a **deliberate duplicate with a two-sided
agreement pin** — not a new pattern: D5 already describes exactly that for `rig_*.py`, pinned by
`test_rig_spec_agreement.py`. This applies a precedent rather than inventing one.

Two options were rejected and are recorded so they are not re-proposed:

- **Pin in the plugin, reading the base's TypeScript through `IMG2THREEJS_BASE`.** It inverts the
  warranty: the base's own emitted geometry would be verified only when an optional plugin happens
  to be installed, through a skip-guarded test. `domain-plugin-boundary` already forbids a skip whose
  reason is a missing plugin; this is its mirror image, and the consequence is `standProud`
  regressing silently on the generic path that A7 exists to protect.
- **`ringStackDistance` is character content.** Not holdable with D2: `standProud` is enforced by the
  base generator, `STAND_PROUD_EXPECTED_ROLES` sits in base strict validation, `role: "hair"` is a
  base schema role, and D5 puts the whole emitter in the stays column. If `ringStackDistance` is
  character, then `standProud` is, then hair is, and D2 is wrong. A coherent position — but not one
  compatible with this design as written. See **D11**.

## D11 — RESOLVED: partition 1. Hair stays whole; this change does not touch it

**Decided by the owner, 2026-09-12.** The plan no longer sits between two positions.

**What that settles.** `scalp_field.py`, `scalp_exposure.py`, `hair_profile.py`, `hair_gate.py`,
`extract_hair_evidence.py`, `docs/HAIR_PIPELINE.md` and the two hair grimoire pages
(`stylized_hair_threejs.md`, `threejs_hair_parameter_contract.json`) all **stay**. The base's strict
validation is untouched. `role: "hair"` remains a base schema role, named in seven places.

**The reason, which is not the one an earlier revision gave.** Not "hair is generic" — that argument
was refuted, because it would have sent the hard channel of the hair gate to a *character* plugin and
left a doll, a wig stand and a furred creature without it. The reason is that **hair cannot leave
whole until a plugin can contribute a component role**, and a half-left hair subsystem is worse than
either end. Follow-up 7.1 names that mechanism; hair extraction is its first consumer.

**Measured consequences, all simplifications:**

| | Before partition 1 | After |
|---|---|---|
| moving test count | 100 (as first written) | **22** — `test_character_rig_derivation` 13, `test_humanoid_proportions` 9 |
| tests that stay which the plan would have moved | — | **78** (`test_scalp_field` 36, `test_scalp_exposure` 21, `test_rigid_hair_binding` 21) |
| moving modules | 4 | **1** — `humanoid_proportions.py` |
| moving grimoire pages | 6 | **4** |
| `gates.json` scalp row + its verdict-envelope wrapper | required | **dissolves** — M1 is not solved, it ceases to exist |
| base floor arithmetic | `1453 − 100 + added` | **`1453 − 22 + added`** |

**The rename is deferred with it.** D10 argued for `scalp_field.py` → `ring_stack_field.py` because
the base should not carry a domain-flavoured filename. Under partition 1 that justification
evaporates: the base legitimately keeps the whole hair subsystem, and renaming one member of a
coherent group — whose only consumer is `scalp_exposure.py`, also staying — would make the pair
*less* legible, for a rule this partition explicitly defers. The rename travels with hair in 7.1.
D10's analysis stands and is why the module stays; only its cosmetic half is deferred.

## D12 — Assumptions this change makes, written down so they can be attacked

The review's closing finding was that several load-bearing assumptions were never stated. Stated:

- **`~/.img2` is not clean.** The registry records `796dd9c` (v0.2.0) while the directory holds the
  abandoned v0.3.0 tree, and `img2 doctor` FAILs on it today. Task 3.10a cleans it; until then every
  "with the plugin installed" capture photographs the abandoned attempt.
- **`anatomy.json` substitutes for the agent-curated `preSpecAssessment.anatomy`.** Decided in D4,
  not inherited: `new_pre_spec_assessment.py` authors no `anatomy` at all, and at this anchor
  `assessment.json` does not exist yet.
- **The plugin re-authors a base-equivalent `base` material.** The alternative — accepting that
  `specSections` drops it — is rejected, because task 1.2's byte-identity test could not pass.
- **A doctor WARN is not a finding.** The multi-capability WARN is mandated by §12 and this change
  adds a third edge; the bar is zero FAILs.
- **`assessmentPatch` may carry `primaryDomain`.** It may — `spec_augmentation.py:102` refuses only
  `objectClass.domain` — but the plan names this as the mechanism rather than leaving it implied,
  for a value `validate_sculpt_spec.py:904` hard-errors without.
- **`hybrid` is NOT assumed to leave with `character`.** The abandoned branch removed both from
  `VALID_KINDS`; `hybrid` is a classification outcome, not a domain name, and `domain-recognition`
  requires it to request input rather than route. Task 3.5 decides it.
- **The harness branch carrying §15 is out of scope but not irrelevant.** §15's "the base SHALL NOT
  import plugin code" is a rule this change ought to conform to, and it lives only on an unmerged
  branch of the change being abandoned. Follow-up 7.2.
- **A function-local import is NOT caught by the collected-count floor.** Measured: with the module
  gone, `--collect-only` still reported 31 while the run reported 2 failed. D6 and the Direction-1
  sweep exist because of it.

*(This section was silently deleted once, by an edit that replaced the block between D11 and D7
while D12 sat inside it — and two documents went on citing it. Restored, and recorded here because
"a claim that does not match the artifact" is the failure this whole change is about.)*

## D7 — Acceptance

| | Capture |
|---|---|
| A1 | Base suite with an empty `IMG2_HOME`: **zero** failures, zero errors. Not "the same failures as before". |
| A2 | Plugin suite standalone, without the base test tree. |
| A3 | `img2 doctor` reporting **zero FAILs** after `img2 add --link`. The multi-capability WARN is expected and is part of the captured baseline, so "clean" is defined as zero FAILs, not zero findings. Requires the installed clone to be free of the withdrawn attempt's untracked residue first. |
| A4 | Both oracles green — emission and authoring — run **before** any file moves and **again** with the plugin installed. |
| A5 | Structural checklist parity: `(scope, id)` capture before and after, byte-equal apart from the intended additions. |
| A6 | Fail-loud without the plugin, **on both paths**: `state.py init --profile character` and a resume of a saved state both name the missing provider and the remedy. Today init answers `invalid choice` and names nothing — D8 is what makes this achievable. |
| A7 | Generic run with no plugin installed still authors a spec and passes strict validation. |
| A8 | Removal round-trip: refusal names the provider; resume unchanged after reinstall. |
| A9 | Collected counts asserted against both floors, each set to its measured value. |
| A10 | Every skip states a reason, and no skip's reason is a missing plugin. |
| A11 | One real character image driven end to end **through the checklist**, evidenced by a named artifact, not by a state file full of `done` marks: the emitted TypeScript contains `THREE.SkinnedMesh`, `THREE.Skeleton`, `new THREE.Bone` and `skinIndex` — the same anti-tamper assertion the emission oracle uses — captured alongside the state file and the reference image. **Blocked until `runtime/scripts/export_mesh_buffers.mjs` is located**: two rig steps (`mesh-freeze`, `mesh-parity-verify`) invoke it and it does not exist in the **`img2threejs`** checkout — `ls -d runtime` there fails and the path appears only in four `.md` files. That is a pre-existing defect in the shipped v0.2.0 plugin, not one this change introduces, but A11 cannot be honest until it is resolved. |
