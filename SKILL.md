---
name: character
version: 0.3.0
description: Analyze GLB construction; author Blender characters from references, source UV/PBR, rig and verify Three.js soft interaction; route licensed CC5 and procedural rigs.
---

# Character plugin — rigging and animation

Keep native Blender authoring, procedural rigging, CC5 and soft-body interaction as explicit routes.
Use `blender-character` for reference-driven native authoring without neural mesh generation.
Keep the base img2threejs entry point for code-only reconstruction; do not mix its factory gates
with native `.blend` authoring or silently replace an existing source/rig.

For learning an existing model or carrying its construction into the next character, read
`reference/character-construction-prior.md` and `reference/character-transfer-exercise.md`; extract facts, then author and verify target-specific decisions.

## When this applies

Choose the route from the user's request, never from a character-looking filename:

- **`blender-character`**: reference → native Blender/bpy construction or admitted editable base →
  UV/source skin and cloth PBR → authored rig/masks → GLB → Three.js interaction. Read
  `reference/blender-character-route.md` first and its stage-specific references as work begins.
  Prefer this route when Blender/native authoring is requested; forbid Tripo or another neural
  mesh generator when rejected. Use useful independent agents, with one main integration owner.
  This is an authoring workflow, not a new harness profile or an automatic photo-to-avatar tool.
- **`cc5-headshot`**: real photo/scan → CC5 + Headshot 3 → Blender Auto Setup →
  `bpy` bake/export → GLB → Three.js. Read `reference/cc5-headshot-route.md` completely.
  This is an external-asset agent route, not a harness profile. Do not run procedural
  spec/generation gates, replace the imported mesh, or rebind an existing CC rig.
  CC5 requires a licensed Windows application handoff; `bpy` controls only Blender.
  Start with `tools/cc5_headshot.py --addon /path/to/cc_blender_tools --check` using
  a Python containing bpy. Stop honestly if real source/export/application access is missing.
- **`softbody-character`**: add local size/press/drag/bounce and hair-follow interaction to an
  existing authored Blender, CC5 or otherwise admitted GLB. Read
  `reference/softbody-character-route.md`, then `reference/softbody-runtime.md`.
  Prepare authored masks with `tools/prepare_softbody.py`; attach `runtime/softbody.mjs`
  without rebuilding the incoming rig. Use `examples/softbody/` for executable diagnostics.
  This composes after native Blender or CC5 authoring; it does not create missing anatomy or rigs.
  Use assets only with recorded permissions; never copy unlicensed demonstration code/assets.
  Do not claim geometric fixtures prove character likeness, collision handling or phone performance.
- **`garment-character`**: connected cloth-surface pulls, in-place outfit change, round chest field and
  outer-layer guarantee, after `softbody-character`. Read `reference/garment-character-route.md`
  and `reference/garment-acceptance.md`. Copy `runtime/garment-character/` byte-identical, re-derive
  subject values in `reference/garment-parameters.json`, measure with `tools/skin_probes.js`,
  judge with `tools/gate_garment.py`. Creates no anatomy, rig or likeness. The Nami example is an
  adapted CC BY 4.0 Sketchfab asset, not a result of reference images alone; this route reproduces
  runtime/workflow/gates, not an image-to-character guarantee.
- **`skin-body`**: the skin (da) **texture** and the body parts of Nami and Robin as reusable knowledge and tools — classify
  atlas regions, measure and match tone, fill/repair, details (iris, brows, lashes), transplanted-head composite and bridge,
  pack-and-verify, skin material; body-part catalogue, neutral soft-region masks, skin weights and mirror checks, head/neck
  join and hair chains. Read `reference/skin-body-distillation.md` (rules and their cases), then `reference/skin-texture.md`
  and `reference/body-parts.md`. Composes with `blender-character`; creates no likeness and grants no rights to donor heads,
  scans or franchise characters. Regions are neutral only (abdomen, waist, cheek/face, hair); the catalogue validator
  rejects anything else. Painted features are not measured reflectance; no pores, browser SSS or de-lighting are established.
  **Agents write the bpy; the pipeline measures it.** `reference/skin-body-agent-contract.md` gives each stage a role, inputs,
  forbidden actions and run commands; `reference/skin-body-standards.json` (S1–S8) and its stage fragments `…s2b-skin-authoring`,
  `…s9-geometry`, `…s10-rig`, `…s11-hair` state the acceptance criteria;
  `tools/bpy_measure_skin_body.py` (bpy python) measures the produced file without editing it and
  `tools/gate_skin_body.py` judges the evidence (unmeasured is never a pass); `tools/skin_body_plan.py` turns a character plan
  into ordered, file-owned subagent briefs. **Declare first:** the target's reference, baselines and limits are recorded before
  authoring (`declared.references/baselines/limits`); the gate judges against those. With two related subjects (Robin adapts
  Nami) no absolute cross-subject norm exists, so Nami/Robin numbers are `severity: advisory` ranges (`reference/nami-robin-interpolation.md`).
- **Procedural rigging**: the base runs the original track only when workspace state
  explicitly names `--profile animated-character`. Follow the rules below.

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
| `runtime/garment-character/` | Byte-identical delivered viewer runtime: `garment.mjs`, `garment-field.mjs`, `cloth-contact.mjs`, `chest-field.mjs`, `softbody.mjs`, `picking.mjs`, `viewer.mjs`, no-store `serve.py`; `provenance.json` pins every hash |
| `skin_probes.js` | Browser probe, independent of the guard: signed distance of every garment vertex and triangle centre to the CPU-skinned body; inside = more than 0.3 mm under it |
| `gate_garment.py` | Five checks (clean, coverage, phases, hard pull, exact release) over recorded matrices; an unrecorded value is `unmeasured`, never a pass |
| `extract_garment_parameters.mjs` | Regenerates the constants in `reference/garment-parameters.json` from the runtime; a test fails on drift |
| `extract_construction_prior.py` | Read-only GLB inventory, conditional anatomy/face/atlas measurements and construction hypotheses; save source-hashed priors for target-specific authoring |
| `skin_texture.py` | **Skin texture**: UV region rasterisation with overlap report, encoded- vs linear-light tone measurement, island fill, neck shadow lift, root-paint repair that cannot wrap edges, detail/iris recolour, composite via `atlas_surface.py`, save-pack-verify, skin material spec/validator, tone-match report |
| `atlas_surface.py` | Composite atlas (W × 9W/8), linear-light neck strip with resolution-invariant UVs, bounded colour-line repair that provably changes nothing outside its mask |
| `head_transplant.py`, `hair_chain_rig.py`, `bake_hair_motion.py` | Similarity fit, plane clip, welded ring bridge with manifold report, cheek masks; seam-equal hair chain weights; constant-length spring bake (no collision) |
| `body_parts.py`, `reference/body-parts.json` | Per-asset/stage body-part catalogue, neutral-region mask evaluation, mirrored-weight symmetry check (never silently passes), catalogue validator |
| `bpy_measure_skin_body.py`, `gate_skin_body.py`, `reference/skin-body-standards.json` | Independent measurement of a produced `.blend`/GLB (source hashes, protected pixels, repair-mask boundary, island tone, UV/weight/mirror parity, bone groups, hair chains, neutral masks, material) and a gate over it: pass \| fail \| unmeasured, exit 0/1/2 |
| `bpy_measure_geometry.py`, `bpy_measure_rig_motion.py`, `bpy_measure_skin_authoring.py` | Measurers for S9 (landmark ratios vs a declared reference, mirror coverage and error, welded topology, UV overlap/gutter/density, budgets), S10/S11 (joint sections, rest mirror, weight reversals, pose-sweep strain statistics on fixed triangles, quaternion continuity, hair clearance/root drift — partial, see `rig-motion-standards.md`) and S2B (region tone, uniformity, mirror, density, padding) |
| `skin_authoring.py` | Skin base tone authoring from reference patches (encoded sRGB and per-pixel L*, feathering only inside adjacent bands, mirror consistency, bounded padding); painted base tone only — no pores, micro-detail or de-lighting |
| `skin_body_plan.py` | Generates the ordered, file-owned agent briefs per stage from the standards and a character-plan input; refuses sources without a rights note and any non-neutral region |

## Procedural rigging hard rules

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
5. **An unmeasured check is not a pass.** The blocking workspace gate executes native source replay,
   actual browser binding/deformation/stop/visibility measurements, and evaluated-pose parity.
   Missing dependencies or inputs return `error`; saved passing payloads are not terminal authority.

## Garment hard rules

1. **Distance along the surface, not through the air.** Cups, ribbons, neck loop and band are one mesh; weight
   every vertex by its Dijkstra distance along it. Case: the earlier build left the neck loop at 0 mm in a
   ribbon pull and tore junctions at 14.4× (ribbon|cup) and 7.4× (cup|band); the field gave 1.31× / 1.27×.
2. **Verify the outer layer with an INDEPENDENT probe, never the guard's own measure.** Case: in the outfit
   change the guard's measure read 0 while the probe found ribbon samples up to 13 mm inside the skin, so the
   fall is stated as outside the guarantee.
3. **Keep each vertex's real rest gap, not a clamp.** Case: a thin clearance clamp snapped barely-moved
   cup-bottom vertices 9 mm toward the skin and tore the cloth from the band.
4. **Never smooth a contact correction without a final one-sided guard.** Case: the 1 mm neighbour bound left
   6.1 mm of the neck loop (78 samples) inside the skin until the guard lifted along the skin normal only.
5. **Serve with no-store and show a build stamp.** Case: the user was shown a stale build; read the stamp
   (`guard-1`) before trusting any result.
6. **A clean subset is not a pass.** `gate_garment.py` fails on a missing matrix cell (angle, side, outfit,
   touch, tissue, combo) even when every recorded case is clean; judge the whole matrix.

## The rig track in the checklist

The `animated-character` profile splices `domain.json` into the base: two character setup steps, then nine rig steps AFTER FINAL steps. `tests/test_domain_declaration.py` pins this order; repair precedes freeze, freeze precedes rigging, parity follows binding.
The static `character` domain stays in-repo and owns those assets.

Rig steps run from the base checkout/workspace. Always pass `--out <name>` or `--payload <path>`; auto-resolution refuses checkout-shaped directories.
`rig-gates` writes workspace-root `rig-gate-payload.json` and runs `gate_rigging.py --payload rig-gate-payload.json`.
The terminal sweep is blocking and independently executes owned native/browser producers against the
hash-bound routed artifact, source blend and reference. Copying `rig-gate-payload.json` cannot pass it.
Use `tools/produce_routed_rig.py native` then `deliver` (README command contract); the terminal gate
replays the source again. Explicit `--payload` remains diagnostic only. Synthetic native wiring
diagnostics do not establish real-reference likeness or release qualification.

## Reference material

- `reference/animation-contract.md` — the routing file, read at the start of the rig stage
- `reference/character-rigging-animation-1.5.2.md` — the derivation, the measured thresholds, and the
  failure log behind every rule above
- `reference/blender-character-route.md` — native authoring entry, artifacts and export handoff
- `reference/blender-geometry-workflow.md` — reference analysis, continuous anatomy and surface gates
- `reference/blender-source-assets.md` and `reference/blender-pbr-workflow.md` — rights, UVs and maps
- `reference/blender-rig-interaction.md` and `reference/blender-agent-workflow.md` — rig, regions and owners
- `reference/blender-export-parity.md` — skinning, shader, morph and tangent export boundaries
- `reference/cc5-headshot-route.md` — real-source, licensed CC authoring and bpy export
- `reference/softbody-character-route.md` — authored masks and source-safe bpy preparation
- `reference/softbody-runtime.md` — runtime API, diagnostic viewer and acceptance
- `reference/garment-character-route.md` — stages, parameters (each tagged `single-subject` or `behaviour`),
  honest scope, replay commands and known limits
- `reference/garment-acceptance.md` — measurable acceptance items `A1`–`A13` with delivered numbers,
  measuring commands and the counter-examples that must fail
- `reference/garment-parameters.json` — extracted constants and hand-read subject literals
- `reference/skin-body-distillation.md` — start here for the skin/body route: 19 rules, each with its case
- `reference/skin-texture.md`, `reference/skin-atlas-authoring.md` — the skin texture pipeline and the atlas formulas
- `reference/body-parts.md` (+ `body-parts.json`), `reference/head-hair-authoring.md` — body parts, weights, masks, head and hair
- `reference/skin-body-standards.md` (+ `.json`), `reference/skin-body-agent-contract.md` — what must be true (S1–S8), how it is measured, and how agents + bpy produce it
- `reference/nami-robin-interpolation.md` — what two related characters can and cannot teach; why standards are reference-relative
- `reference/skin-authoring-from-reference.md`, `reference/body-geometry-standards.md`, `reference/rig-motion-standards.md` — S2B, S9 and S10/S11 recipes, limits and failure logs

Express the procedural rig track's distance thresholds relative to **figure height H**; preserve
the declared units of angles, weights, ratios and runtime parameters. Numbers marked
`single-subject` came from one rig and are starting values, not constants.

## Tests
```bash
python3 -m unittest discover -s tests
node --test tests/garment-character/*.test.mjs   # or: npm run test:garment
node --test tests/skin-probes.test.mjs           # or: npm run test:probes
python3 -m unittest tests.test_skin_texture tests.test_atlas_surface tests.test_body_parts tests.test_head_transplant tests.test_hair_chain_rig tests.test_bake_hair_motion
python3 -m unittest tests.test_gate_skin_body tests.test_bpy_measure_skin_body tests.test_skin_body_plan
python3 -m unittest tests.test_skin_authoring tests.test_bpy_measure_skin_authoring tests.test_bpy_measure_geometry tests.test_bpy_measure_rig_motion
"$HOME/.img2/runtime/character-bpy/bin/python" -m unittest discover -s tests -p 'test_bpy_measure_*.py'   # real bpy: any Python containing bpy
```
