---
name: character
version: 0.1.0
description: Character rigging and animation for img2threejs — skeleton read from a GLB, skin conditioning across overlapping parts, clip measurement and naming, action design against target bands, and a twelve-check rig gate where an unmeasured check is never a pass.
---

# Character plugin — rigging and animation

Upgrades an img2threejs reconstruction from a static mesh to a rigged, animated one. **The base skill
stays the entry point; this cannot run alone.** Without it a character reference still reconstructs —
with no rig, no skinning and no bind. Less exact is the intended trade; useless is not.

## When this applies

Declared, never inferred. The base runs this track when the workspace state names it —
`--profile animated-character` — and never because a file, a component or an image happens to look
like a character.

## The rule everything else follows

> **Nothing about a rig is believed until it has been evaluated at a sampled time and compared
> against the value the track says it should have.** A clip that exists is not a clip that plays.

Two 1.5.1 bugs each produced a plausible scene with zero motion: eleven clips held actions, the mixer
held state, buttons dispatched, nothing moved. Neither was visible in code review. Both were found
only by measuring.

## What it contributes

| Tool | What it does |
|---|---|
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
