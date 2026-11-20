# plugin-character

Character rigging and animation for [img2threejs](https://github.com/img2threejs/img2threejs), as an
[img2](https://github.com/img2threejs/img2) plugin.

```bash
img2 add img2threejs/plugin-character
```

## Public installer

A public npm installer is published separately so users do not need to clone the plugin
manually. The installer is a thin launcher for the shared `@img2threejs/img2` runtime and
fetches this plugin's source on first run; it does not include any rig, gate or skeleton
implementation. See [`CLI_QUICKSTART.md`](CLI_QUICKSTART.md) and [`cli/README.md`](cli/README.md).

```bash
npx --yes @img2threejs/character install --dry-run
npx --yes @img2threejs/character install --yes
npx --yes @img2threejs/character doctor
```

The npm package is scoped to `@img2threejs/character`; the executable installed into `PATH`
stays unscoped as `img2-character`. CLI executable version (`0.2.0`) and plugin source
version (`v0.2.0`) are released on separate tracks. This package is an installer only —
installing it is not a claim that a rig build, rig measurement, or rig gate has passed.

## What it is for

The base code-only img2threejs reconstruction produces a static mesh. This plugin can take it
from there: a skeleton read out of a GLB, skin conditioning, measured clips and a twelve-check
gate where **an unmeasured check is never a pass**. Native Blender and licensed CC5 authoring
use separate explicit routes below; their export and visual checks are not factory-generation gates.

### Blender-first authoring route: `blender-character`

For a reference-matched interactive character without Tripo/neural mesh generation:
**reference analysis → native bpy construction or admitted editable base → UV/source PBR →
authored skeleton and soft masks → GLB/sidecar → Three.js verification**.

Read [`reference/blender-character-route.md`](reference/blender-character-route.md). It routes to
continuous face/body geometry, CC0-first skin/fabric sources, UV transfer and material baking,
concrete rig/weight requirements, posed interaction and coordinator-owned agent handoffs.
Keep one integration owner and preserve editable `.blend`, build recipes, source permissions,
export hashes, reference comparisons and measured pose/contact/decay evidence.
Check [`reference/blender-export-parity.md`](reference/blender-export-parity.md) before accepting
browser skinning, skin/cloth shading, morph normals or baked animation as equivalent to Blender.

This is an actionable skill workflow, **not a bundled photo-to-avatar generator**. The LLM authors
and runs reference-specific bpy scripts. Existing `prepare_softbody.py` only exports an already
authored project. A single image cannot guarantee exact hidden anatomy or photorealistic likeness.
No new harness profile, neural service, paid asset purchase or automatic upload is introduced.


### Separate real-source route: `cc5-headshot`

Explicit opt-in: **real photo/scan → CC5 + Headshot 3 → Blender/bpy → GLB → Three.js**.
See [`reference/cc5-headshot-route.md`](reference/cc5-headshot-route.md) for the handoff,
runtime setup, export commands and browser acceptance checks.

CC5/Headshot authoring requires the licensed Windows applications. The Python adapter accepts
an imported Auto Setup `.blend`, not a photo, scan or raw FBX. It uses the official material
baker/exporter and preserves the incoming master. It never substitutes a procedural avatar.
This is an agent-level route, not a new harness `--profile`; `animated-character` is unchanged.

Preflight and non-CC source rejection have been exercised with bpy 4.5.15 and Auto Setup 2.4.5
on macOS arm64. Real CC5 conversion, likeness, clip preservation and Three.js rendering still
require an actual source and browser evidence; runtime readiness is not character generation.

### Composable interaction route: `softbody-character`

Keep either admitted asset route, then add **authored masks → bpy preparation → GLB/sidecar
→ Three.js soft-body**. This does not replace CC5/Headshot or generate a character.

- Separate dynamic region meshes and static complement; keep the original skeleton, skin,
  materials, UVs and live morphs. Size follows weights rather than scaling joints.
- Four-substep springs/damping; posed raycast press, local indentation, surrounding bulge,
  drag/shear and release; recomputed normals with a blended boundary.
- Hair-mask followers move with the region. This is not general cloth/hair collision.

See [`reference/softbody-character-route.md`](reference/softbody-character-route.md) for authoring
and export limits, and [`reference/softbody-runtime.md`](reference/softbody-runtime.md) for API
integration and acceptance. Use one material primitive per configured Blender object.

Run the original geometric diagnostic viewer from this plugin directory:

```bash
npm ci --ignore-scripts
npm run demo:softbody
# Open http://127.0.0.1:8768/examples/softbody/
```

The viewer also opens a local prepared GLB plus its `softbody.json`; no upload or third-party
character is included. Real-character appearance, clip playback and phone performance need
separate acceptance with the actual asset.

### Composable garment route: `garment-character`

After `softbody-character`, an admitted character can wear a **connected garment**: one cloth surface whose
pulls follow distance along the cloth, an in-place outfit change, a round chest field and an **outer-layer
guarantee** (the skin is never in front of the cloth), verified by an independent probe and a gate that
refuses a partial matrix. The delivered Nami viewer behind it is an adapted licensed Sketchfab asset
(CC BY 4.0), not something reference images alone produce; the route reproduces the workflow, the
byte-identical runtime, the measured parameters and the acceptance gates.
See [`reference/garment-character-route.md`](reference/garment-character-route.md) and
[`reference/garment-acceptance.md`](reference/garment-acceptance.md).

### Composable skin route: `skin-body`

The **skin texture** and the **body parts** of Nami and Robin, as tools and measured rules: classify atlas regions, measure
and match tone (encoded-sRGB vs linear light is named in every call), fill and repair without touching anything outside the
mask, add iris/brow detail, composite a transplanted head with a linear-light bridge, pack the saved bytes and verify them,
and state the skin material honestly (no pores, browser SSS or de-lighting were ever established). Body parts are catalogued
per asset and stage (Robin 80-bone rig vs 28-bone head component; Nami 4-joint vs 53-joint), with neutral soft-region masks,
mirrored-weight symmetry checks and hair chains. Regions are neutral only; the catalogue validator rejects anything else.
It grants no rights to donor heads, scans or franchise characters. See
[`reference/skin-body-distillation.md`](reference/skin-body-distillation.md), [`reference/skin-texture.md`](reference/skin-texture.md)
and [`reference/body-parts.md`](reference/body-parts.md).

**Agents write the bpy; the pipeline measures it.** Each stage S1–S8 (source/rights, skin texture, head/neck join, skeleton and
body parts, skin weights, neutral masks, material, export parity) has acceptance standards in
[`reference/skin-body-standards.json`](reference/skin-body-standards.json), a role contract for agents
([`reference/skin-body-agent-contract.md`](reference/skin-body-agent-contract.md)), a bpy-side measurer that never edits the
file (`tools/bpy_measure_skin_body.py`) and a gate over its evidence (`tools/gate_skin_body.py`; pass | fail | unmeasured).
It is a framework of standards and measurement, not an automatic photo-to-character converter: rights-cleared body, head and
atlas sources must be supplied.

**Reference-relative, not Nami-relative.** Nami and Robin are two *related* characters (Robin adapts Nami; the historical Robin eye
detector selected sunglasses), so no absolute number from them is a norm. The extended standards (S2B skin authoring from a reference,
S9 geometry/topology/UV, S10 rig and pose deformation, S11 hair fit) judge a new character against its **own declared reference,
baselines and limits** (`reference-within`, `no-worse-than-baseline`, `declared-min`/`declared-max`, wildcard per-region/per-pose
metrics); the Nami/Robin values are `advisory` ranges that warn but never fail. See
[`reference/nami-robin-interpolation.md`](reference/nami-robin-interpolation.md).


## The rule it is built around

> Nothing about a rig is believed until it has been evaluated at a sampled time and compared against
> the value the track says it should have. **A clip that exists is not a clip that plays.**

Two bugs in the pre-plugin build each produced a plausible scene with zero motion: eleven clips held
actions, the mixer held state, buttons dispatched, nothing moved. Neither was visible in code review;
both were found only by measuring. Every gate here traces to a failure that was measured, not imagined.

## Contents

| | |
|---|---|
| `tools/rig_*.py` | skeleton, skinning, bind space, mesh parity |
| `tools/anim_*.py` | clip measurement, action design, runtime emission |
| `tools/gate_rigging.py` | one gate row, twelve checks, every verdict reported |
| `tools/cc5_headshot.py` | isolated bpy/Auto Setup preflight and external-character bake/export |
| `tools/prepare_softbody.py` | source-safe authored mask export, sidecar and integrity receipt |
| `runtime/softbody.mjs` | skeleton-preserving size, spring, contact and hair-follow controller |
| `runtime/garment-character/` | byte-identical delivered garment viewer runtime, with `provenance.json` |
| `tools/gate_garment.py`, `tools/skin_probes.js` | outer-layer gate over recorded matrices; independent browser probe |
| `examples/softbody/` | local diagnostic viewer and prepared-GLB loading |
| `tools/skin_texture.py`, `tools/atlas_surface.py` | skin texture pipeline: tone measurement, fills, details, composite, pack-and-verify, skin material spec |
| `tools/body_parts.py`, `reference/body-parts.json` | body-part catalogue, neutral masks, mirrored-weight symmetry, catalogue validator |
| `tools/head_transplant.py`, `tools/hair_chain_rig.py`, `tools/bake_hair_motion.py` | head/neck join, cheek masks, hair chains and constant-length motion bake |
| `tools/gate_skin_body.py`, `tools/bpy_measure_skin_body.py`, `tools/skin_body_plan.py` | S1–S8 acceptance gate, bpy measurer and agent brief generator |
| `tools/bpy_measure_geometry.py`, `tools/bpy_measure_rig_motion.py`, `tools/bpy_measure_skin_authoring.py`, `tools/skin_authoring.py` | measurers and authoring core for S2B, S9, S10, S11 |
| `reference/` | the derivation, the measured thresholds, and the failure log |

Every threshold is a fraction of **figure height H**, never an absolute unit. Numbers marked
`single-subject` came from one rig and are starting values, not constants.

## Two design decisions worth knowing before reading the code

**One gate row, not twelve.** `img2_core.gate_runner` is sequential and stop-the-line: the first
non-passing blocking row halts the run and the rest are recorded as skipped. Twelve rows would surface
one failure and eleven skips. The aggregate preserves the point of the suite, which is seeing every
violation at once.

**`unevaluated` maps to `error`, and never appears in `status`.** A check whose input is absent is not
a pass. The verdict parser accepts only `pass|fail|error`, and an unrecognised status makes it discard
every reason supplied — so the distinction lives in `reasons` and `evidence` instead. The new
runtime and RGBA measurers below do not establish a complete real-subject browser/oracle run.
The legacy aggregate remains non-blocking until that proof exists; missing evidence still fails
routed terminal admission.

## Routed rig artifacts (D18, not release-qualified)

`route.json` requires explicit `rig` intent and declares local dependencies. It does **not** make
this plugin eligible: the required release-qualified blocking rig gate is still absent. Existing
optional authoring/interaction routes and the legacy gate declaration are unchanged.

`tools/rigged_artifact.py` has three offline entry points:

```bash
python3 tools/rigged_artifact.py extract character.glb --out extracted-rig
python3 tools/rigged_artifact.py admit --workspace WORKSPACE --request rig-admission-request.json
python3 tools/rigged_artifact.py snapshot --workspace WORKSPACE --request snapshot-input.json --out rig-snapshot.json
```

Extraction decodes the actual embedded GLB, skin joint order, inverse-bind matrices, hierarchy/rest
transforms, mesh attributes and animation input/output accessors. Skeleton and per-clip sidecars
are strict sorted compact UTF-8 JSON without a trailing newline. Their hashes are not the GLB hash.
Extraction alone is **not admission**. Unsupported morph/multi-skin/external-resource representations
fail explicitly; they are not converted or silently dropped.

Admission requests contain `objectId`, and `{path,sha256}` references for `glb`, `runtime`,
`freezeManifest`, `motion`, `sweep`. All evidence paths are relative to the child workspace; symlinks,
escapes and hash mismatches block. `metricAnchor` contains `nodes:[nodeA,nodeB]`, an independently
measured positive `metres` distance, a nonempty `method`, and a `{path,sha256}` `source`. Scale is
computed from that distance divided by the GLB nodes' actual rest-world separation. The GLB must
already have a measured bottom-centre pivot in glTF's Y-up/+Z-forward frame; normalize **before**
freezing, never by changing geometry or bind matrices during admission.

- **Runtime producer:** import `measureRig` from `runtime/rig-measurements.mjs` in the viewer and
  pass `{root,clips,controller,glbSha256,meshIds}`. Hash the exact GLB bytes given to GLTFLoader.
  `controller.seek(name,time)` / `stop()` must be the **delivered** controller, not a second mixer.
  Pause external tickers and use a disposable loaded copy initially in bind pose.
  `meshIds` maps loaded meshes to `node:N/primitive:P` from GLTFLoader's actual parser associations;
  use the same stable identities for the pre-bind freeze. Persist the returned JSON as `runtime`.
  The probe compares actual PropertyBinding values to track interpolants over every clip, transforms
  every distinct vertex, measures post-stop restoration, and records actual visible mesh coverage.
  Missing bindings/controllers fail; tiny meshes are not padded to claim 64 distinct vertices.
- **Motion evidence:** `motion` contains the current `glbSha256`, explicit `landmarkNodes` for
  `hip/head/hand.l/hand.r/foot.l/foot.r`, independent node-id `sideLabels`, and `stance` intervals
  keyed by actual clip name. `sideLabelSource` and `stanceSource` are hash-bound evidence references.
  Stance/contact evidence must come from the subject, not an inferred gait label. The adapter samples
  positions/scales from the GLB again; missing stance never becomes a passing foot-contact check.
- **Rendered sweep:** `sweep` is `img2.character-sweep` v1, with current `glbSha256`, a `baselineGlb`
  evidence reference for the blend-off control, `roiSource` reference for independent ROI authorship,
  declared `creaseLuminanceMax` (0–255), and `axes` arrays for `clips/times/sides/azimuths`.
  Times are normalized clip fractions including 0 and 1; azimuths are degrees in [0,360).
  The control must preserve this subject's actual skeleton, clips and frozen geometry.
  `frames` cover the complete Cartesian product without duplicates. Each has
  `clip/time/side/azimuth`, integer `width/height`, and evidence references
  `candidate/baseline/roi/camera`. Candidate/baseline are raw RGBA8 transparent-background diagnostic
  captures at that same camera/pose.
  `camera` records both `glbSha256` and `baselineGlbSha256`, matching `clip/time/side/azimuth`,
  and actual finite 16-component `projectionMatrix` / `matrixWorld` values.
  ROI is one 0/1 byte per pixel marking expected interior skin seams, never the silhouette.
  Transparent ROI pixels measure background-through-split;
  opaque dark pixels are a separately reported crease diagnostic, **not** a skin classifier.
  Ambiguous antialiased/translucent ROI pixels, missing raw bytes/views or missing control block.
  Capturing those views and authoring trustworthy seam ROIs still require the actual browser harness.

Admission re-runs all twelve checks using actual GLB binding, freshly sampled clips, runtime evidence,
raw sweep pixels and the pre-bind freeze. A failure retains a content-addressed diagnostic gate record
but emits no new `artifact.json`. Success writes the D18 manifest with hashed GLB/evidence files,
canonical skeleton/clip references and measured scale. Receipts alone cannot authorize it.
The blend-off baseline GLB remains available in the workspace and hash-verified through the bound
gate/admission inputs, but is excluded from D18 `files[]` when distinct from the delivery GLB.
It is source evidence, not an alternate renderable. Delivery remains bound by
`rig-admission.json.inputs.glb`; consumers must never select the first filename by extension.
Static skeletons can be extracted with `clips:[]`, but routed delivery remains blocked: the existing
animated gate has no approved measured static-rig applicability policy.

`snapshot-input.json` contains `source:{path,sha256}` and optional
`assets:[{role,path,sha256}]`. The result is a fresh `{bindings,observations}` fragment for the base
controller's strategy/review/repair contexts. A `gate` asset must bind the current GLB and every
measurement input; changed evidence invalidates the snapshot. Unavailable views/candidates are not
invented. The base owns candidates, allowed operations, revision scope, consent/budget, decisions and
acceptance; this plugin neither imports it nor makes provider calls.

Focused checks (requires the existing img2 core link and declared Three.js dependency):

```bash
node --test tests/rig-measurements.test.mjs
python3 -m unittest discover -s tests -p test_rigged_artifact.py
python3 -m unittest discover -s tests -p test_gate_rigging.py
python3 -m unittest discover -s tests -p test_domain_declaration.py
```

The new Python positive case executes real GLB/Three CPU data but uses explicitly synthetic RGBA
fixtures. It is protocol evidence, **not** real-browser, Blender parity, visual quality or release proof.

## Tests

```bash
python3 -m unittest discover -s tests
```

```bash
npm ci --ignore-scripts
npm run test:softbody
npm run test:garment
# Optional real Blender preparation regressions:
IMG2_CC5_PYTHON=/absolute/path/to/python-with-bpy \
python3 -m unittest discover -s tests -p test_prepare_softbody.py
```

To include the real bpy rejection/lifecycle regression, provide the isolated Python executable
and official add-on path:

```bash
IMG2_CC5_PYTHON=/absolute/path/to/python-with-bpy \
IMG2_CC5_ADDON=/absolute/path/to/cc_blender_tools \
python3 -m unittest discover -s tests -p test_cc5_headshot.py
```


`tests/test_oracle_replay.py` is the correctness oracle for the extraction: a byte comparison against
a frozen run on a real 113-node GLB. It is deliberately a byte comparison — a semantic assertion has
to enumerate what matters, and the point of an oracle is to catch the change nobody predicted.

## Licence

Apache-2.0.
