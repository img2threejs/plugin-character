# Rig, skin weights and soft interaction

Use with `blender-character-route.md` after geometry passes. Scope: one authored skeleton,
finite web-exportable weights, authored soft regions and a measured pointer interaction.
No neural mesh generation, no rig guessed from imported names, no live physics claim.

## 1. Derive the skeleton from the measured character

The bone set is a **derived result**, never a template. There is no fixed "22-bone" skeleton: the
count is whatever the measured anatomy and the admitted base asset support, and it is recorded.
Parentage is explicit, with no ambiguous indentation (one chain per side where the anatomy has
one):

```
Root -> Pelvis -> Spine -> Spine2 -> Chest -> Neck -> Head
Chest -> Clavicle.L -> UpperArm.L -> ForeArm.L -> Hand.L -> [fingers]
Chest -> Clavicle.R -> UpperArm.R -> ForeArm.R -> Hand.R -> [fingers]
Pelvis -> Thigh.L -> Shin.L -> Foot.L -> Toe.L
Pelvis -> Thigh.R -> Shin.R -> Foot.R -> Toe.R
Optional face: Head -> Jaw ; Head -> Eye.L ; Head -> Eye.R
```

Derivation rules:

- Take joint positions from the landmark measurements recorded in `blender-geometry-workflow.md`
  (shoulder, elbow, wrist, pelvis, hip, knee, ankle, plus sternum/clavicle/neck/head landmarks).
  Convert to the project's Blender space (Z-up, meters) and scale by the recorded figure height `H`.
  Bone head/tail run between consecutive landmarks; bone length is the observed segment length,
  not a canonical human ratio. **Never silently omit a required joint because its landmark is
  occluded.** Use the observed segment measure where one exists; otherwise place it from the
  admitted base asset or a recorded anatomical prior and mark that placement **inferred** with its
  uncertainty. An inferred position is never reported as a measurement. Omit a joint only when the
  capability it serves is explicitly outside the accepted scope, and list it as absent with that
  reason.
- Set bone roll so the bone's local axis matches the anatomical motion axis, and record the roll
  used per bone; a wrong roll shows up as a twisting elbow, not as a missing bone. Root sits at the
  world anchor and is not weighted. Record the forward axis and the character's left/right
  convention; Blender Z-up exports to glTF right-handed Y-up (metres), front toward +Z. Confirm
  the exported axis and the left/right sign from the exported file, not from this text.
- Import a base asset's skeleton only when it is admitted, editable and its joints are measured
  against the reference. Never map bones to an imported rig by name similarity, and never rebind
  an incoming rig (see `cc5-headshot-route.md`). The bone names you author are the single source of
  truth for the sidecar's `bone` field: it must be a joint that exists in the exported skin, never
  a request to create or rebind one.

## 2. Declare capability honestly
The job's `character-plan.json` states skeleton, face and finger scope per capability:
`present` (with joint and control names), `absent` (with the reason), or `unknown`.

- **Face/finger rig** — claim it functional only when it was authored AND exercised: a driven
  pose measurably moved the expected vertices (see §6). A painted iris, a texture-based smile or
  a "rig planned for later" is `absent`/`unknown`, never "functional".
- **Eye** — an eye capability means real eyeball volume in a socket, continuous eyelids with
  clearance, and iris/pupil placement that holds in neutral and in every claimed expression. A
  painted eye on a skin mesh is not an eye rig; declare it absent. **Jaw** — a jaw capability needs
  a jaw bone driving the lower face, not a bone that exists while the chin stays rigid.

## 3. Topology and destructive edits come before skinning
- Build a **continuous deforming surface** with edge loops at shoulder, elbow, wrist, hip, knee and
  ankle before any weights exist. Loops are what make a bend deform instead of crease.
- Apply **destructive** remesh, subdivision and fitting before the freeze. Leave no live
  subdivision/remesh modifier that silently rebinds after export: the exported mesh must be the
  applied one. Reopening geometry after the freeze revalidates UVs, weights, masks and export
  hashes; it does not bypass parity.
- Keep **skin, garments and hair as separate semantic surfaces** with their own material, UV set
  and weight treatment. Clothing follows the body by authored deformation (weights derived from
  the body surface it covers); it is never the body's own tissue retextured.

## 4. Weights that a web exporter can actually load

- Every deformable vertex has **at least one** influence; no unweighted deformable vertex remains.
  Zero-weight vertices either get a weight or leave the deforming set explicitly. Weights are
  finite, non-negative and **normalized**: `|1 − Σw| ≤ 2e-7` per vertex, matching the repo's own
  G4 threshold in `animation-contract.md`. **At most four influences per vertex** for the web
  export: trim to the four strongest and renormalize, and do not rely on a client reading
  `JOINTS_1`. `max skinIndex ≤ joints.length − 1`, checked against the exported skin's joint array.
- **A BoneHeat operator returning `FINISHED` is not a deformation test.** Proof is a measurement:
  drive one joint and compare the moved vertex ring against the ring that must stay put. Flex the
  elbow; the forearm ring moves, the upper-arm ring does not, and the elbow loop moves smoothly
  with no collapsed or flipped triangles.

## 5. Rest pose, bind space and the exported skin

- **Preserve valid authored native bind transforms and inverse binds.** An admitted base asset's
  rest pose and inverse-bind matrices are authored data: keep them. Do not zero them or rebind a
  valid imported skin just to satisfy a procedural bind convention. The identity-bind rule
  belongs to the **procedural** route (`animation-contract.md` §R1), where the skeleton is authored
  from scratch. Apply it there; do not impose it on native authoring, whose rest pose already
  defines the bind.
- In either case avoid **double-applying** the display offset or the armature transform: take any
  display offset from the mesh bounds alone, and confirm it is not also inside the bind or the
  node transform. Units are metres in both spaces; Blender is Z-up and glTF is right-handed Y-up.
  Record the conversion as an explicit transform and verify the exported file, not this text.
- After export, inspect the **loaded** skin: read `skin.joints` order and the inverse-bind
  accessor with `../tools/rig_glb_reference.py`. The joint order is the skin's, never the traversal
  order and never the authoring order.
- **Neutral parity**: with the skeleton at rest, match the authored mesh within tolerance
  (≤ `1e-4 · H` per vertex). On mismatch inspect transforms, joint order, weights and inverse binds;
  repair the actual cause, not a re-freeze that hides it. The browser's deformation
  algorithm is not Blender's: read `blender-export-parity.md` before claiming pose parity, since
  it records the verified Blender/Three.js gaps that constrain this rig.

## 6. Exercise the rig in the actual GLB under Three.js

Load the **exported GLB** in the destination app (its own Three.js, one shared instance), never
the `.blend`. Drive and measure shoulder, elbow, wrist, hip, knee and ankle individually, plus
every declared face/finger control; an unmeasured control is not a working control. Capture neutral
and posed frames from the same camera and record the bone/vertex deltas. Confirm skinning, UVs,
material groups, morph targets and clips survive the export.

## 7. Soft regions: authored masks, not label-derived ones

Compose the already-authored project with `../tools/prepare_softbody.py`; its schema and command
live in `softbody-character-route.md`.

- Masks come from **real vertex groups the author painted**. A region id such as `chest-left` is
  an identifier only; nothing derives a mask from an anatomical label. The tool copies the
  authored groups to `_SOFT_*` scalar attributes and, optionally, `_HAIR`. **One material
  primitive per configured object:** the tool rejects multi-primitive objects because GLTFLoader
  splits them; split the surfaces on the working copy before preparing.
- Region `center`/`radius` are in the **loaded GLB mesh's pre-skin local space**; the tool derives
  them from the weighted rest surface excluding hair, and a hair-only region needs an explicit
  calibrated center/radius. Never copy Blender Z-up or world coordinates into the sidecar. A
  region only deforms smoothly if its area has **sufficient continuous topology** and an authored
  mask that falls smoothly to zero; a sparse or noisy mask gives a faceted field.
- **Protected surfaces stay unchanged** unless explicitly targeted: eyelids, lips, joint creases,
  eyeballs, teeth, accessories. Give them their own region or exclude them from the mask. Hair
  follow is a weighted follower: hair vertices move with a region they also influence, grow with
  the body and **never shrink into it**.

## 8. What the runtime does and does not promise

- The solver projects the combined field toward rest: each triangle keeps **≥ 15 %** of its rest
  projected signed area and edges stay within **0.4–1.8×** rest length, evaluated on the pre-skin
  rest surface. This is a rest-space guard; validity under **arbitrary posed** skin/morph
  deformation is not guaranteed. It is a bounded CPU surface-field solver — not volumetric, not
  FEM, not a cloth or hair collision solver. Blender softbody/cloth modifiers do **not** export as
  live glTF physics.
- Check UV **position** continuity and smooth-normal continuity across the deform region and UV
  splits; authored **hard edges stay hard**. Clip-driven jiggle needs a **measured** anchor
  acceleration converted into the mesh's pre-skin local impulse (sample the region anchor through
  the bone's bind/current matrices), warm-started velocity history, cleared on clip restart, with
  impulse caps scaled by `dt`. Bones moving alone is not jiggle.
- Pointer interaction must be real: raycast the posed scene, take the nearest visible surface,
  hold/drag/release with pointer capture, and release on pointer-up, pointer-cancel, lost-capture,
  navigation and asset replacement. `reset()` must return positions exactly to neutral while
  keeping the caller's morph state, and the static complement must not move. Measure a nonzero
  effect, decay back to rest, unit-length normals and non-degenerate triangles; acceptance details
  and the diagnostic viewer are in `softbody-runtime.md`.