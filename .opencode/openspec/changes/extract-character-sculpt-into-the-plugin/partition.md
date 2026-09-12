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
to matter, and one flagged one turned out to be mechanism.

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
| `_eye_socket_sdf` | 363 | 29 | *"A concave eye socket"* — a shell with a sphere carved out at `0.09 / 0.075 / 0.055 × hu`. The CSG is generic; the three constants and the cavity's purpose are **face anatomy** | **content** |
| `_limb_attachment` | 337 | 24 | *"an attachment contract for a linear **body segment**"* — taper, embed depth and gap tolerance for a limb | **content** |
| `make_pre_spec_assessment` | 23 | 81 | **SPLIT.** The scaffold every profile uses is mechanism. But `:77` authors an `anatomy` block, and `:98-100` says it is *"Only meaningful when objectClass.primaryDomain is character or hybrid"* and names two leaving grimoire pages | **split — see §6** |
| `_cnode` | 256 | 65 | *"a full schema-valid componentTree node with humanoid-friendly defaults"*. It knows the **componentTree schema**, not anatomy. Its defaults (`material="skin"`, `role="body"`) are humanoid flavour on a generic builder | **mechanism — with an open question, §9.1** |
| `slugify`, `make_quality_contract`, `load_assessment`, `inject_geometry_rules`, `_shade_hex`, `make_spec`, `main` | — | — | Generic | **mechanism** |

`_cnode` is the inverse of the four errors above: a symbol whose docstring names a domain while its
code does not. Classifying it by docstring would have moved 65 lines of schema machinery.

## 4. `validate_sculpt_spec.py` — the flagged three

| Symbol | Line | Lines | What it knows | Verdict |
|---|---|---|---|---|
| `validate_character_track` | 2610 | 36 | anatomy.applies, styleHeads, proportions, faceLandmarks, character featureReviewTargets | **content** |
| `_mirror_partner` | 2663 | 11 | `upper-arm-l` ↔ `upper-arm-r`, including mid-id `-l-` for digits | **content** |
| `validate_rig_admission` | 2676 | **122** | **SPLIT** — see below | **split** |

`validate_rig_admission`, by check:

| Check | Knows | Verdict |
|---|---|---|
| NAME_UNIQUENESS | duplicate ids, exactly one root | **mechanism** |
| POOL_FLOOR | the weight function keeps four influences per vertex | **mechanism** — bound to the §4 weight function, which stays |
| SYMMETRY_PARITY | bilateral symmetry about X, `-l`/`-r` vocabulary — **and it mutates the spec** | **content**, and it must leave regardless: a base validator may not write |
| MONOTONIC_CHAIN | "a bone points against its parent", calibrated on an upright biped | **content** |
| PROPORTION_LIMIT | bone length against skeleton height, calibrated on clavicle/thumb | **content** |

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

## 6. The leaving set, final

| | |
|---|---|
| **Whole modules** | `forge/_shared/domains/character.py` (26L), `forge/stage2_spec/humanoid_proportions.py` (214L) |
| **From `new_sculpt_spec.py`** | the thirteen of §2 (750L) + `_eye_socket_sdf` + `_limb_attachment` (53L) + the `anatomy` seed block in `make_pre_spec_assessment` |
| **From `validate_sculpt_spec.py`** | `validate_character_track`, `_mirror_partner`, and SYMMETRY_PARITY / MONOTONIC_CHAIN / PROPORTION_LIMIT |
| **Grimoire** | `reconstruction.md`, `likeness_maximization.md`, `structure_decomposition.md`, `head_construction.md` — **four**, not six |
| **Tests** | `test_character_rig_derivation` (13), `test_humanoid_proportions` (9) — **22 collected** |

**Stays, and would have moved under an earlier revision:** `scalp_field.py`, `scalp_exposure.py`,
both hair grimoire pages, and `test_scalp_field` + `test_scalp_exposure` + `test_rigid_hair_binding`
— **78 collected**.

## 7. Floor arithmetic

```
base:    1453 collected on main  −  22 moved  +  <added> =  <measured, same sitting>
plugin:   258 collected at v0.2.0  +  22 arrived  +  <added> =  <measured, same sitting>
```

The plugin's declared floor at v0.2.0 is **235** against 258 collected — already 23 short. It is
**corrected**, not raised from.

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

**This partition is the change's acceptance criterion. Nothing in slice 1 or later moves until §9 is
answered in `review/partition-review.md`.**
