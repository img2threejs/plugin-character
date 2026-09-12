# Partition review — OpenSpec task 0.3

**Reviewer:** independent architecture adversary (`oh-my-claudecode:architect`, read-only), ten
report parts. **Tree:** `img2threejs` @ `extract/character-sculpt` = `6e60b5e`, clean.
**Date:** 2026-09-12. **Verdict: the gate is closed.** The partition is sound once Q1, Q4 and Q6 are
applied and both floors re-derived.

Every ruling below was re-measured by the author before acceptance. Where the author's leaning
survived, it says so; where it did not, the measurement that killed it is named.

| Q | Subject | Author's leaning | Confidence | Ruling |
|---|---|---|---|---|
| 1 | `_cnode`'s humanoid defaults | leave in base | medium | **REBUT** — question malformed |
| 2 | the `anatomy` block | keep empty scaffold | medium | **AMEND** — premise false |
| 3 | `test_rig_hierarchy_emission`'s method | re-express | high | **AMEND** — two owners |
| 4 | `validate_rig_admission`'s split | keep remainder as a function | high | **REBUT** — question malformed |
| 5 | `POOL_FLOOR`'s threshold of 4 | mechanism | **lowest** | **AMEND** — right answer, wrong reason |
| 6 | `_eye_socket_sdf` / `_limb_attachment` | move the functions | medium | **REBUT** — question malformed |
| 7 | `hybrid` in `VALID_KINDS` | keep | **highest** | **ACCEPT** |

---

## Q1 — `_cnode` leaves. REBUT: all three options presupposed it stays

**18 call sites, every one inside `make_character_component_tree`** (`:490`–`:804`); nothing else in
the repo but a comment at `test_hierarchy_scale.py:67`. By knowledge it is mechanism — it knows the
componentTree schema and nothing humanoid. By call graph it is the template's private node builder,
and after slice 3 it would sit in the base with **zero callers**: the withdrawn attempt's signature
defect ("the plugin's copy had no caller at all") pointed the other way.

The defaults question dissolves with it. `material="skin"` and `role="body"` travel with the
function, and "neutralising changes output for every caller" is moot — there are no other callers.

## Q2 — stop authoring the `anatomy` key. AMEND: the author's premise was false

The question asserted that `validate_sculpt_spec.py:904` hard-errors on a missing `primaryDomain`.
It does not: it fires only when `routing_track == "character-v1.5"`, and `primaryDomain` is seeded
`"unassessed"` independently. **The interaction the question reasoned from does not exist.**

On the evidence: every producer and consumer of `preSpecAssessment.anatomy` leaves
(`new_sculpt_spec.py:77` and `:1947`, `humanoid_proportions.py:186`,
`validate_sculpt_spec.py:2620`). The one staying writer, `extract_landmarks.py:441`, writes into its
own artifact, not the assessment. **Zero base consumers after slice 3.** Keep a scaffold only if a
base consumer can be named; none can. The plugin contributes `anatomy` through `assessmentPatch`,
which merges non-guarded keys into `preSpecAssessment` by plain dict update — exactly where the base
used to put it.

## Q3 — split the method. AMEND: it has two owners

`assertEqual(len(applied), 2)` tests `apply_character_pose`, which leaves. Everything from
`generate(spec, "blockout")` onward tests the emitter, which stays, and the docstring says so. The
emitter half needs no leaving code: the block reads rotations straight off `componentTree`, so a
pre-posed fixture satisfies it identically.

Base keeps the emitter assertions against a pre-posed fixture; the `len(applied)` assertion moves to
the plugin with its subject. The import is a **function-local `ImportFrom`** — the third instance in
this change — and belongs on the Direction-1 sweep's expected-hits list. **If the sweep does not
surface it, the sweep is wrong.**

## Q4 — all 122 lines stay. REBUT: the costliest malformed question of the four

1. **`rig` is plugin-contributable**, so the base must be the party that checks it. `rig` is not in
   `BASE_OWNED`; a plugin writes it wholesale and the merge admits it **opaquely** — *"the base
   cannot validate a finish recipe or a rig"*. `validate_rig_admission` is the base's only check on
   rig content arriving that way. Moving three of five checks into the plugin makes **the plugin
   validate its own submission**.
2. **Five base consumers, none leaving**: `materials/compatibility.py:47`,
   `attachment_anchor.py:167`, `generate_threejs_factory.py:1928` and `:1955`, and the validator.
3. **Payload-gated, not domain-gated** — a no-op without a skeleton. This is the genuine
   payload-presence routing D5 wrongly attributed to `rig_is_bone_track`.
4. **No check names a domain.** Over all 122 lines the only occurrence of "anatomy" is inside
   MONOTONIC_CHAIN's calibration comment; the code has zero domain literals. `_mirror_partner` keys
   on `-l`/`-r` id suffixes — the same category as `CHARACTER_LEFT_SIGN`, which D5 keeps.

**The three grounds the author gave, checked individually:**

| Check | Author said | Measured |
|---|---|---|
| SYMMETRY_PARITY | content, it mutates the spec | mutation is real and **orthogonal** — a write concern, not a content one. Moving it relocates the write, it does not stop it |
| MONOTONIC_CHAIN | content, calibrated on an upright biped | the **narrative** is; the check is `dot(child, parent) < -0.5` gated on same-chain, with no anatomical term. A chair armature folding a bone back through its parent is equally broken |
| PROPORTION_LIMIT | content, calibrated on clavicle/thumb | **misattributed** — clavicle and thumb are MONOTONIC_CHAIN's comment. And PROPORTION_LIMIT's own comment records the **opposite**: *"READING CHOSEN: the rig carries no head unit… so the limit is expressed as a fraction of the skeleton's own height. That is scale-free and needs no external input."* A previous author **deliberately de-anatomised this check**; the partition would have re-anatomised it by classification |

That last one is the sharpest instance of the round's pattern: the evidence against the
classification was written down, in the file, directly above the constant.

**Side effect:** `test_joint_admission_gate.py` — which imports `POOL_FLOOR_MIN_BONES` at `:34` and
asserts the `POOL_FLOOR` tag at `:100` — stays whole rather than being torn along the same seam. The
simpler outcome, and one more sign the function was not meant to divide.

## Q5 — mechanism, decisively. AMEND: right answer, wrong reason, wrong confidence

The `4` was not chosen by looking at skeletons. It is the **`skinIndex`/`skinWeight` vec4 attribute
width**: `MAX_INFLUENCES = 4` (`geodesic_skinning.py:38`), `Uint16BufferAttribute(skinIndices, 4)`
and `Float32BufferAttribute(skinWeights, 4)` (`emit_rig.py:272-273`), both in `stage5_rig/`, which
stays. A chair with an armature is bound by it identically. The author's least-confident question
should have been the most confident.

**Follow-on, not required here:** `POOL_FLOOR_MIN_BONES = 4` is a bare literal at
`validate_sculpt_spec.py:2654`, duplicating the width it encodes. `= MAX_INFLUENCES` with the import
stops the two drifting.

## Q6 — both leave with their caller. REBUT: the call graph makes it moot, as in Q1

`_limb_attachment` has 9 call sites, `_eye_socket_sdf` 1, all inside the leaving function, none
elsewhere in the repo. "Leaving them takes 53 lines of usable geometry out of the base" is true in
principle and empty in practice: the base does not use them.

**The stated binary was also false.** "Split at the constants" would leave a parameterised
`_limb_attachment` in the base with zero callers — Q1's defect, reintroduced deliberately. And the
constants are not the humanoid part: `_limb_attachment`'s anatomy is entirely in its **arguments**,
supplied by the caller; its body is a dict constructor with two generic defaults.

**Provenance travels:** `_eye_socket_sdf`'s comment records a shipped defect — empty socket geometry
with 457 tests passing while the cavity did not exist. That moves **verbatim**.

## Q7 — keep `hybrid`. ACCEPT

Never a track key; its only role is forcing `status: "request-input"` — a classification **outcome**,
which is the fail-closed verdict `domain-recognition` requires.

Removing it would not change control flow: the kind would be rejected as invalid and fall back to
`malformed-classification`, still landing on request-input. What changes is the **diagnosis** — a
legitimate "part object, part character, I cannot decide" becomes *corrupt input*. That is a
regression in a gate whose entire value is explaining its refusal.

**Sweep caveat:** scope the domain-name sweep to the `{"character", "hybrid"}` **literal pair**, not
the bare word. `hybrid` has three roles; a bare grep takes all three.

---

## The round's own finding: four of seven questions were malformed

Q1 presupposed `_cnode` stays. Q2 asserted an interaction that does not exist. Q4 presupposed the
split. Q6 offered a false binary. In each, **both offered options sat downstream of a premise the
evidence does not support**.

Q4 is the costliest shape: a reviewer answering it as asked would have chosen carefully between two
ways of doing something that should not be done, and the answer would have read as responsive.
Q2 is the most dangerous: a reviewer trusting its premise would have answered the wrong question
correctly, and handed the answer back **wearing the review's authority**.

> The defence is not more careful reviewers. It is that **a question asserting an interaction must
> cite the line that creates it**, so the premise is checkable at the same cost as the answer.

## The rule this round earned

> A symbol's classification is not settled until **both** questions are answered — what does it
> know, and who calls it — and where they disagree, **the call graph wins**.

Five findings here were one call-graph query away. None was reachable from a docstring. Counting the
review of the change itself, this is the seventh instance of deriving a classification from what
something is *called or says about itself* rather than from what *refers to it*: a docstring, two
filenames, a directory name, a symbol's self-description, a neighbouring comment, and a comment that
recorded the opposite of what was assumed.

## Open, deliberately

**Should a snap on plugin-contributed data be a refusal rather than a silent correction?**
SYMMETRY_PARITY writes `jointPos`/`tipPos` back into `spec["rig"]["bones"]`. Today it corrects
base-authored data, and its docstring's reasoning holds — "an asymmetric pair is a fixable authoring
slip". After this change it corrects **a plugin's submission**, so the shipped spec differs from what
the provider emitted, and the provider's own oracle will agree with itself while disagreeing with
what shipped.

Reviewer's view, recorded as a view: whichever way the refusal question goes, **route the snap
through `record["clamped"]`** — the channel `merge_spec_augmentation` already uses for
base-over-plugin overrides ("kept X over proposed Y"), attached to `spec["specAugmentation"]`. A snap
is the same category of event with no such record. It costs little and makes the override
attributable, which is the difference between a decided behaviour and one found by whoever debugs it
first.

This is a `spec-augmentation` question, not a partition one. It does not gate slice 1.
