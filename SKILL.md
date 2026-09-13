---
name: character
version: 0.3.0
description: The character track for img2threejs — the humanoid sculpt spec and its derived rig, anatomy landmarks and figure-drawing canon, skeleton read from a GLB, skin conditioning across overlapping parts, clip measurement and naming, action design against target bands, and a twelve-check rig gate where an unmeasured check is never a pass.
---

# Character plugin — the character track

Serves the whole character track: the humanoid sculpt spec, its derived skeleton, and the rig and
animation that follow. **The base skill stays the entry point; this cannot run alone.** Without it a
character reference still reconstructs — as a generic object, with no humanoid decomposition, no rig,
no skinning and no bind. Less exact is the intended trade; useless is not.

Since 0.3.0 the base owns none of this. It authors a skeleton spec and merges what this plugin
publishes; the humanoid template, the rig derivation and the figure-drawing canon live here.

## When this applies

Declared, never inferred. The base runs this track when the workspace state names it —
`--profile character` — and never because a file, a component or an image happens to look like a
character.

`animated-character` is withdrawn. It was a second profile that omitted the Stage R gates, which is
how animation shipped broken in 1.5.1; there is one id now, and a static build skips a rig step with
a recorded reason.

## The rule everything else follows

> **Nothing about a rig is believed until it has been evaluated at a sampled time and compared
> against the value the track says it should have.** A clip that exists is not a clip that plays.

Two 1.5.1 bugs each produced a plausible scene with zero motion: eleven clips held actions, the mixer
held state, buttons dispatched, nothing moved. Neither was visible in code review. Both were found
only by measuring.

## What it contributes

| Tool | What it does |
|---|---|
| `character_spec_template.py` | The humanoid track: component tree, derived rig, materials, build passes and review targets, authored into an empty dict |
| `emit_spec_augmentation.py` | Publishes that as `spec-augmentation-v1`, which the base pulls at `spec-authoring`. Takes no `--spec`: the base pulls, a plugin never writes into the base's spec |
| `humanoid_proportions.py` | Public figure-drawing canon for a reference-free figure, labelled as canon and never as measured evidence |
| `rig_glb_reference.py` | Reads skeleton, **skin joint order**, inverse binds and clips from a GLB; samples its channels into a measurable payload |
| `rig_mesh_parity.py` | Freezes geometry buffers, then proves rigging only added to them |
| `rig_skin_conditioning.py` | Proximity weight blending across overlapping parts |
| `rig_geodesic_skinning.py` | Weights from distance measured *through the solid*, so influence does not leak across an air gap |
| `anim_clip_features.py` | Measures a clip, classifies it, names it, and decides whether it loops |
| `anim_action_design.py` | Target bands and gait/ballistic/reach primitives; authored clips must satisfy the classifier |
| `anim_emit_runtime.py` | Emits the bind space and controller as TypeScript |
| `gate_rigging.py` | One gate row, twelve checks, every verdict reported |

## Hard rules

1. **Read the rig from the GLB.** The skin's joint ordering is the authority — never traversal order,
   never node names. A GLB's clips target *its* node indices and its `skinIndex` values address *its*
   joint array; fed to a procedurally authored skeleton they index a different rig and shred the mesh.
2. **Repair before the freeze; after the freeze, only ADD.** Rigging may add `skeleton`, `skinIndex`
   and `skinWeight`. Positions, normals, uvs and indices are evidence. If parity fails, the rigging is
   wrong — never re-freeze to make it pass.
3. **Bind at identity in attached mode**, and take the display offset from the mesh bounds alone.
   Attached mode recomputes `bindMatrixInverse` from `matrixWorld` every frame, so `matrixWorld`
   cancels out entirely.
4. **`updateMatrixWorld(true)` before `new THREE.Skeleton(...)`.** `calculateInverses()` reads each
   bone's current world matrix; constructed first it captures identity, the rest pose never cancels,
   and the model renders a corpse while reporting `bound: true`.
5. **An unmeasured check is not a pass.** The gate reports `error` when an input is absent, and says
   which input. Four of the twelve checks have no producer yet, so that is the honest verdict today.

## The track in the checklist

Installing this plugin registers the `character` profile: the base splices this plugin's
`domain.json` — three setup steps before `local-spec-search`, then nine rig steps appended AFTER the
base's FINAL steps. The step order is canonical here and pinned by
`tests/test_domain_declaration.py`; repair precedes the freeze, the freeze precedes every rig step,
parity is verified after the bind.

The three setup steps read this plugin's grimoire pages, extract anatomy landmarks, and emit
`spec-augmentation.json`. `character-landmarks` runs before `character-spec-augmentation` because the
second reads what the first writes — order inside the group, which the anchor does not buy.

`specCollection: "character"` points the mandatory local-evidence search at this plugin's own
collection. Note that it REPLACES the collection searched rather than adding one, which is why
`docs/specs/vocabulary/` carries byte-identical copies of the base's `core_3d` records: without them
a character run would search less than a generic one.

Working-directory contract: rig steps run from the base checkout, which is also the workspace.
Every tool invocation therefore carries an explicit `--out <name>` or `--payload <path>` — never
rely on workspace auto-resolution, which refuses checkout-shaped directories.

**Where the gate payload goes.** The `rig-gates` checklist step assembles
`rig-gate-payload.json` at the WORKSPACE ROOT and runs
`gate_rigging.py --payload rig-gate-payload.json`. The terminal `gates.json` sweep instead reads
the fixed confined path `.img2/artifacts/character/rig-gate-payload.json` — copy the payload there
if you want the terminal sweep to evaluate it. The gate is declared `blocking: false` until the
four producer-less checks gain producers (re-block trigger in the CHANGELOG); an honest fail is
recorded in the aggregate without halting it.

## Reference material

- `reference/animation-contract.md` — the routing file, read at the start of the rig stage
- `reference/character-rigging-animation-1.5.2.md` — the derivation, the measured thresholds, and the
  failure log behind every rule above

Every threshold is a fraction of **figure height H**, never an absolute unit. Numbers marked
`single-subject` came from one rig and are starting values, not constants.

## Tests

```
python3 -m unittest discover -s tests
```
