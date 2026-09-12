# Partition — extract-character-sculpt-into-the-plugin

**Tree:** `img2threejs` @ `6e60b5e` (`main`), branch `extract/character-sculpt`.
**Measured:** 2026-09-12. Every count in this document came from a command run in this sitting.
**Scope:** D11 partition 1 — hair stays whole. This partition covers the **character sculpt** content only.

This is the change's acceptance criterion. "Extract the character sculpt track" has no other
definition.

## The test

**What does the symbol KNOW?** — not what it is called, and not what its docstring says it was
written for. The review of the previous attempt found four instances of classification by name:

| | Was derived from | Should have been derived from |
|---|---|---|
| `scalp_field.py` called content | its docstring, which recounts a hair defect as *motivation* | its code: signed distance to a stack of ellipse rings |
| `test_rigid_hair_binding` moved | its filename | its import: `geodesic_skinning`, which stays |
| `test_stand_proud_emission` left | its filename | its function-scoped import of `scalp_field` |
| `grimoire/character/` moved whole | the directory name | its contents: two of six are hair pages |

So this document flags by name only to open the list, then classifies by reading. The
name-flagged census is 13 symbols in `new_sculpt_spec.py`; three of the **unflagged** ones turned out
to matter, and one flagged one appeared to be mechanism.

**And "what does it know?" is necessary but NOT sufficient. Ask "who calls it?" beside it.**
Added after the 0.3 review overturned this document's own verdict on `_cnode`. By knowledge it is
mechanism — it knows the componentTree schema and nothing humanoid. By call graph it is content:
**18 call sites, every one inside `make_character_component_tree`**, which leaves; the only other
mention in the repo is a comment in `test_hierarchy_scale.py:67`. Leaving it behind ships a 65-line
function with no callers in the base — the withdrawn attempt's signature defect ("the plugin's copy
had no caller at all") pointed in the opposite direction.

That makes five instances in this change of deriving a classification from what something *is
called or says about itself* rather than from what *refers to it*: a docstring, two filenames, a
directory name, and now a symbol's self-description. Both questions get asked, every row.

## 1. The census, measured

| Module | module-level symbols | name-flagged |
|---|---|---|
| `forge/stage2_spec/new_sculpt_spec.py` | 24 | 13 |
| `forge/stage2_spec/validate_sculpt_spec.py` | 104 | 3 |
| `forge/_shared/pipeline_routing.py` | 12 | 0 |
| `forge/stage2_spec/new_pre_spec_assessment.py` | 15 | 0 |

## 2. `new_sculpt_spec.py` — the flagged thirteen

| Symbol | Line | Lines | What it knows | Verdict |
|---|---|---|---|---|
| `make_character_component_tree` | 394 | **416** | A stylized humanoid body plan: torso, neck, head, pelvis, arms, legs, face | **content** |
| `derive_character_rig` | 909 | **158** | How to derive a PLAN_1.5 §6 skeleton from a humanoid component tree | **content** |
| `apply_character_template` | 1122 | 48 | Which of the above to apply, and in what order | **content** |
| `apply_character_pose` | 1082 | 38 | `anatomy.pose.jointAngles` → component rotations | **content** |
| `make_character_build_passes` | 842 | 21 | The character-v1.5 pass list | **content** |
| `make_character_feature_targets` | 865 | 16 | anatomy-proportion, face-landmark-placement, pose-silhouette, outfit | **content** |
| `_hu_ratio` | 323 | 12 | Head-unit ratios from `anatomy.proportions` | **content** |
| `CHARACTER_BASE_MATERIALS` | 822 | 10 | skin, hair, shirt, pants, shoes, eye, lips | **content** |
| `CHARACTER_ACCESSORY_MATERIALS` | 834 | 6 | one reference person's decal, glasses, headphones | **content** |
| `_RIG_CHAINS` | 890 | 9 | Named humanoid limb chains | **content** |
| `_rig_chain_of` | 901 | 6 | Which chain a component id belongs to | **content** |
| `_POSE_JOINT_TO_COMPONENT` | 1071 | 9 | `leftShoulder` → `upper-arm-l` | **content** |
| `_RIG_STRUCTURAL_LEAVES` | 888 | 1 | pelvis, head, hands, feet | **content** |

Thirteen for thirteen, **750 lines**. The name flag was right about all of them — which is not an
argument that the flag is sufficient, as §3 shows.

## 3. The unflagged, where name-matching failed

| Symbol | Line | Lines | What it knows | Verdict |
|---|---|---|---|---|
| `_eye_socket_sdf` | 363 | 29 | Three baked ratios (`0.09 / 0.075 / 0.055 × hu`) — face anatomy. **1 call site, inside the leaving function**; none elsewhere in the repo | **content — leaves** |
| `_limb_attachment` | 337 | 24 | Its body is a generic dict constructor with two generic defaults (`embed_depth=0.03`, `gap_tolerance=0.01`); the anatomy is entirely in its **arguments**, supplied by the caller. **9 call sites, all inside the leaving function**; none elsewhere | **content — leaves, with its caller** |
| `make_pre_spec_assessment` | 23 | 81 | **SPLIT.** The scaffold every profile uses is mechanism. But `:77` authors an `anatomy` block, and `:98-100` says it is *"Only meaningful when objectClass.primaryDomain is character or hybrid"* and names two leaving grimoire pages | **split — see §6** |
| `_cnode` | 256 | 65 | By knowledge, the **componentTree schema**, not anatomy. By call graph, the character template's private node builder: **18 call sites, all inside `make_character_component_tree`** (`:490`–`:804`), zero elsewhere | **content — leaves.** §9.1 asked which way to neutralise its humanoid defaults; the 0.3 review rejected the question, because after slice 3 nothing in the base calls it at all |
| `slugify`, `make_quality_contract`, `load_assessment`, `inject_geometry_rules`, `_shade_hex`, `make_spec`, `main` | — | — | Generic | **mechanism** |

`_cnode` looked like the inverse of the four errors above — a symbol whose docstring names a domain
while its code does not — and this document classified it as mechanism on that basis. The 0.3 review
overturned it on the call graph: every caller leaves, so it leaves. The docstring was a red herring
in **both** directions, and only the call graph settled it.

## 4. `validate_sculpt_spec.py` — the flagged three

| Symbol | Line | Lines | What it knows | Verdict |
|---|---|---|---|---|
| `validate_character_track` | 2610 | 36 | anatomy.applies, styleHeads, proportions, faceLandmarks, character featureReviewTargets | **content** |
| `_mirror_partner` | 2663 | 11 | `upper-arm-l` ↔ `upper-arm-r`, including mid-id `-l-` for digits | **content** |
| `validate_rig_admission` | 2676 | **122** | **STAYS WHOLE.** This document split it; the 0.3 review rebutted the split and the rebuttal holds | **mechanism — all 122 lines stay** |

**Why it does not split**, verified:

1. **`rig` is plugin-contributable, so the base must be the one that checks it.** `rig` is not in
   `BASE_OWNED` (`spec_augmentation.py:26`), so a plugin writes `spec["rig"]` wholesale through
   `specSections` and the merge admits it **opaquely** — that module's own words: *"Accepted opaquely
   — the base cannot validate a finish recipe or a rig."* `validate_rig_admission` is the base's only
   check on rig content arriving that way. Moving three of its five checks into the plugin would
   mean **the plugin validates its own submission**, which is not validation.
2. **`spec["rig"]` has five base consumers and none of them leaves**: `materials/compatibility.py:47`,
   `stage4_review/attachment_anchor.py:167`, `generate_threejs_factory.py:1928` and `:1955`, and the
   validator itself at `:2684`. `rig` is base schema with a base consumer graph; its validator
   belongs with it.
3. **It is payload-gated, not domain-gated.** `rig = spec.get("rig")` then `if not bones: return` —
   a no-op for any spec without a skeleton. This is the genuine payload-presence routing that D5
   wrongly attributed to `rig_is_bone_track`.
4. **No check names a domain.** Measured over all 122 lines: the only occurrence of "anatomy" is
   inside MONOTONIC_CHAIN's calibration **comment**; the code contains zero domain literals.
   `_mirror_partner` keys on `-l`/`-r` **id suffixes** — a naming convention, the same category as
   `CHARACTER_LEFT_SIGN`, which D5 keeps as "a coordinate-system fact, not anatomy". So keeping all
   five leaves no domain name behind, which was the objection to keeping them.

**Where this document was wrong, check by check:**

| Check | This document said | Measured |
|---|---|---|
| SYMMETRY_PARITY | content, because it mutates the spec | **True that it mutates, and orthogonal.** Mutation is a *write* concern, not a content one; moving it would relocate the write, not stop it. See the row below |
| MONOTONIC_CHAIN | content, "calibrated on an upright biped" | The **narrative** is; the check is `dot(child_dir, parent_dir) < -0.5` gated on same-chain. No anatomical term in it. A chair armature with a bone folded back through its parent is equally broken |
| PROPORTION_LIMIT | content, "calibrated on clavicle/thumb" | **Misattributed.** Clavicle and thumb are MONOTONIC_CHAIN's comment at `:2747-2762`. This document read a neighbouring comment and attached it to the wrong check, then used it as grounds to move that check |

That misattribution is the sixth instance in this change of deriving from adjacent or
self-descriptive text rather than from the thing itself — and the second, after Q2, of reasoning
from a premise that was never checked.

### A base validator writes into a section a plugin contributed — decided, not discovered

SYMMETRY_PARITY writes `jointPos` and `tipPos` back through references into `spec["rig"]["bones"]`
(`:2812-2816`). Today that edits base-authored data. **After this change it edits data a plugin
contributed**, which sits directly against `spec-augmentation`'s "the base SHALL pull; a plugin SHALL
NOT push" — from the other side of the wall, where nothing currently says anything.

Recorded as **mechanism, stays, mutates on snap — deliberate**, so that whoever meets it is reading
a decision rather than debugging a surprise. **Open:** should a snap on plugin-contributed data be a
refusal instead? Snapping base-authored data is a convenience; silently correcting a provider's
submission and then emitting from the corrected version is a different act, and the provider never
learns. Not resolved here; it is a `spec-augmentation` question, not a partition one.

## 5. Consumers — the 0.2 sweep, whole-tree, three passes

`import` hits: **0**. Nothing imports `humanoid_proportions`; it is a standalone CLI.

**Symbol references: 33.** Production: `new_sculpt_spec.py` (11, all internal to the leaving set),
`validate_sculpt_spec.py:2730` (`_mirror_partner`), `:2841` (`validate_character_track`).

**Test references — three modules no earlier disposition list named:**

| Module | Reference | Why it was missed | Disposition |
|---|---|---|---|
| `test_character_rig_derivation.py` | 13 symbol refs | — | **moves** (13 tests) |
| `test_joint_admission_gate.py` | `_mirror_partner` ×4 at `:150-153` | name gives no hint | **reworked** — it is the 12-error module on the abandoned branch |
| `test_rig_hierarchy_emission.py:102` | `from new_sculpt_spec import apply_character_pose`, **inside a method body** | its module-scope imports are `json/re/subprocess/sys/tempfile` — invisible to any module-scope scan, and the collected count never moves | **stays**; its subject is the emitter. Re-express or relocate that one method |
| `test_run_gates.py:187` | `forge/_shared/domains/character.py` as a **path string** | no AST node references the module at all | **reworked** — its premise ("an in-repo domain") vanishes with slice 3.1 |

**Path strings: 8.** Two in `domains/character.py` (leaves), two in `new_sculpt_spec.py:100`
(leaves with the seed block), two in `test_rig_workflow_steps.py:207-208` (reworked),
**one in `extract_landmarks.py:6` — a module that STAYS**, and one in `test_run_gates.py:184`.

## 6. The leaving set, final — after the 0.3 review

| | |
|---|---|
| **Whole modules** | `forge/_shared/domains/character.py` (26L), `forge/stage2_spec/humanoid_proportions.py` (214L) |
| **From `new_sculpt_spec.py`** | the thirteen of §2 (**750L**) + `_cnode` (65L) + `_eye_socket_sdf` (29L) + `_limb_attachment` (24L) = **868L**, plus the `anatomy` seed block inside `make_pre_spec_assessment` |
| **From `validate_sculpt_spec.py`** | `validate_character_track` (36L) — **and nothing else** |
| **Grimoire** | `reconstruction.md`, `likeness_maximization.md`, `structure_decomposition.md`, `head_construction.md` — four, not six |
| **Tests** | `test_character_rig_derivation` (13), `test_humanoid_proportions` (9) — **22 collected** |

**What the review moved back into the base**, against this document's first draft:

| | Lines | Why |
|---|---|---|
| `validate_rig_admission` | **122** (whole) | §4 — `rig` is plugin-contributable and admitted opaquely, so the base must be the party that checks it |
| `_mirror_partner` | 11 | Its only production caller is `validate_rig_admission:2730`, which stays |
| `test_joint_admission_gate` | whole module | It imports `POOL_FLOOR_MIN_BONES` and `_mirror_partner`; under the abandoned split it would have been torn along the same seam |

**And what the review moved out**, also against the first draft: `_cnode`, `_eye_socket_sdf` and
`_limb_attachment` — **118 lines** the document had classified as mechanism, every one with all of
its call sites inside `make_character_component_tree`.

Net: the base loses ~118 lines more than first booked and keeps ~133 it was going to lose. The
**test** accounting is unchanged — `test_joint_admission_gate` was already slated for rework rather
than relocation — so the moving set is still 22.

## 7. Floor arithmetic

```
base:    1453 collected on main  −  22 moved  +  <added> =  <measured, same sitting>
plugin:   258 collected at v0.2.0  +  22 arrived  +  <added> =  <measured, same sitting>
```

The plugin's declared floor at v0.2.0 is **235** against 258 collected — already 23 short. It is
**corrected**, not raised from.

Both floors are re-measured in one sitting after the leaving set lands, per the change's own
measurement rule. The line counts above moved in both directions during review; the test counts did
not, and only the test counts feed a floor.

## 8. What the base still names after this change

`hair`, in seven places — `STAND_PROUD_EXPECTED_ROLES`, `validate_sculpt_spec.py:470` and `:1549`,
`REJECTED_HAIR_PRIMITIVES`, `material_physics.py:210`, `geodesic_skinning.py:66`,
`orchestrate_passes.py:138`. This change discharges "the pipeline names no domain" for **one** name.
Follow-up 7.1 is the mechanism that lets a plugin carry a role; hair is its first consumer.

## 9. Open questions — for the 0.3 review, not for the author to settle

1. **`_cnode`'s humanoid defaults.** It stays as mechanism, but `material="skin"` and `role="body"`
   are humanoid flavour left in the base. Neutralising them changes emitted output for every caller
   that relies on the default. Leave, neutralise, or require callers to pass them?
2. **`make_pre_spec_assessment`'s `anatomy` block.** Extracting it from inside a staying function is
   the same shape as the `apply_character_template` call site. Does the base keep an empty `anatomy`
   scaffold, or stop authoring the key entirely? `validate_sculpt_spec.py:904` hard-errors on a
   missing `primaryDomain`, so the interaction needs stating.
3. **`test_rig_hierarchy_emission`'s one method.** Its subject stays; only that method reaches into
   the leaving set. Re-express it against a fixture, or move the single method to the plugin?
4. **`validate_rig_admission`'s split leaves a 122-line function in two pieces.** Is the mechanism
   half worth keeping as a function, or does it fold into its caller?
5. **`POOL_FLOOR`'s threshold of 4.** Bound to the weight function (mechanism) — but the number
   itself was chosen for humanoid skeletons. Mechanism, or a content constant on a mechanism check?
6. **`_eye_socket_sdf` and `_limb_attachment` are generic CSG with anatomical constants.** Leaving
   them takes 53 lines of usable geometry out of the base. Is the right split the function or the
   constants?
7. **The base keeps `character` in `pipeline_routing.TRACK_BY_KIND`** until slice 3.5, and `hybrid`
   stays in `VALID_KINDS` by decision. Confirm `hybrid` is genuinely a classification outcome and
   not a third domain name.

### Follow-on from the 0.3 review, not required by this change

`POOL_FLOOR_MIN_BONES = 4` is a bare literal at `validate_sculpt_spec.py:2654`, duplicating the
attribute width it encodes. Express it as `POOL_FLOOR_MIN_BONES = MAX_INFLUENCES` with the import,
so the two cannot drift. One line; recorded here so the next reader does not re-ask question 5.

### Provenance travels with the code

`_eye_socket_sdf`'s comment records a shipped defect — empty eye-socket geometry, with 457 tests
passing while the cavity did not exist. That history moves **verbatim** with the function; a comment
recording a defect is the cheapest test there is for a defect no test caught. Before any symbol
moves, check whether it carries one.

### `hybrid` stays — and the sweep must not take it by accident

`hybrid` is never a track key: `TRACK_BY_KIND` holds only `weapon` and `character`. Its only role is
in `resolve_pipeline_routing`, where `kind in {"hybrid", "unknown"}` forces `status:
"request-input"` — a classification **outcome**, the fail-closed verdict `domain-recognition` asks
for, not a domain name.

Removing it would not change control flow: `_normalize_classification` would reject the kind, fall
back to `_fallback_classification("malformed-classification")`, and still land on request-input.
What changes is the **diagnosis** — a legitimate "part object, part character, I cannot decide"
verdict would be reported as corrupt input, carrying
`evidenceRefs: ["pipeline-routing:malformed-classification"]`. That is a regression in a gate whose
entire value is explaining its refusal.

**So the domain-name sweep is scoped to the `{"character", "hybrid"}` literal pair, not the bare
word.** `hybrid` appears in three roles: the `VALID_KINDS` member (stays) and two character-track
sites (`new_sculpt_spec.py:1924`, `validate_sculpt_spec.py:904`) that leave. A bare grep takes all
three.

### The rule this round earned

> A symbol's classification is not settled until **both** questions are answered — what does it
> know, and who calls it — and where they disagree, **the call graph wins**.

Five findings in the 0.3 review were one call-graph query away, and none of them was reachable from
a docstring.

**This partition is the change's acceptance criterion. Nothing in slice 1 or later moves until §9 is
answered in `review/partition-review.md`.**
