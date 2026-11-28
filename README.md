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
stays unscoped as `img2-character`. CLI and plugin implementation versions are released on
separate tracks; `cli/package.json` records the exact installer version and source pin. The package is installer-only —
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

Connected cloth pulls, color transitions and surface-support fields now require explicit per-input
calibration. The default viewer uses an independently authored Cartesian board/cloth rig, not a
third-party character. It demonstrates geometric mechanics only: no human/garment fidelity, native
acceptance or original-asset performance is claimed. Missing real calibration is refused; G4 stays
unmeasured without selected input limits. The generic probes and all gate thresholds remain intact.
See [`reference/garment-character-route.md`](reference/garment-character-route.md) and
[`reference/garment-acceptance.md`](reference/garment-acceptance.md).

### Composable skin route: `skin-body`

Generic skin texture, weights/masks, topology and head/hair tools use caller-owned references,
catalogues and calibration: classify atlas regions, measure tone in a named color space, repair only
within declared support, preserve source bytes and compare actual native/export data. The bundled
catalogue describes only the independent board/cloth primitive, not human measurements or a
reference skeleton. `skin_body_plan.py` requires and forwards the caller's `catalogueFile`.
Neutral-region policy and native/CC5 workflows remain supported. No asset rights are granted. See
[`reference/skin-body-distillation.md`](reference/skin-body-distillation.md), [`reference/skin-texture.md`](reference/skin-texture.md)
and [`reference/body-parts.md`](reference/body-parts.md).

**Agents write the bpy; the pipeline measures it.** Each stage S1–S8 (source/rights, skin texture, head/neck join, skeleton and
body parts, skin weights, neutral masks, material, export parity) has acceptance standards in
[`reference/skin-body-standards.json`](reference/skin-body-standards.json), a role contract for agents
([`reference/skin-body-agent-contract.md`](reference/skin-body-agent-contract.md)), a bpy-side measurer that never edits the
file (`tools/bpy_measure_skin_body.py`) and a gate over its evidence (`tools/gate_skin_body.py`; pass | fail | unmeasured).
It is a framework of standards and measurement, not an automatic photo-to-character converter: rights-cleared body, head and
atlas sources must be supplied.

**Reference-relative, not case-relative.** Two *related* reference characters are not a population, so no absolute number from
them is a norm and no case ranges are shipped. The extended standards (S2B skin authoring from a reference,
S9 geometry/topology/UV, S10 rig and pose deformation, S11 hair fit) judge a new character against its **own declared reference,
baselines and limits** (`reference-within`, `no-worse-than-baseline`, `declared-min`/`declared-max`, wildcard per-region/per-pose
metrics). See
[`reference/reference-relative-standards.md`](reference/reference-relative-standards.md).


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
| `runtime/garment-character/` | explicitly calibrated mechanics and independent synthetic viewer; integrity manifest |
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
every reason supplied — so the distinction lives in `reasons` and `evidence` instead. The aggregate
is blocking: its workspace mode executes the owned native and browser producers below, not a saved
diagnostic payload. Missing evidence/dependencies fail closed; wiring is not release qualification.

## Routed rig artifacts (D18, not release-qualified)

`route.json` requires explicit `rig` intent and declares local dependencies. Its distinct routed-only
terminal gate is data-registered for independent base whitelisting/pinning, not added to global
`gates.json`. This is not release qualification or acceptance authority. Existing optional
authoring/interaction routes are unchanged; the blocking `rigging` workspace gate shares the actual
routed evaluator. Explicit `--payload` mode is a diagnostic checklist check, not terminal authority.

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
  evidence reference for a separately authored blend-off control, a `baselineSource` reference
  for its authoring source/recipe, `roiSource` for independent ROI authorship, declared
  `creaseLuminanceMax` (0–255), and `axes` arrays for `clips/times/sides/azimuths`.
  Times are normalized clip fractions including 0 and 1; azimuths are degrees in [0,360).
  The control must preserve this subject's actual skeleton, clips and frozen geometry.
  Candidate-equal GLB hashes and equivalent effective skin weights (including reordered or
  duplicated influence slots) are refused. Both control bytes and authoring source stay hash-bound;
  source binding establishes freshness, not ownership or permission.
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

### Native build → freeze → bind → browser delivery

The source is a saved, unbound `.blend` with an explicitly named armature, complete renderable mesh
and action rosters, and authored finite normalized one-to-four bone influences per vertex.
Destructive modifiers must already be applied. Already-bound meshes, morphs, imported NLA composition,
linked libraries and unpacked file images fail rather than being silently rebound or converted.
The native producer opens with scripts disabled, records the source frame and canonicalizes each
working mesh into world coordinates **before** freezing (source master and rig rest stay unchanged).
It measures source-world correspondence, exports the actual pre-bind mesh, freezes native geometry,
then adds only linear Armature modifiers. POSITION/UV/index accessors and vertex order must remain
byte-identical. bpy's extra skin-normal normalization is handled by preserving the actual pre-bind
NORMAL payload, never by tolerating normal-buffer drift; raw-bound export and correction hashes are
retained. No position, bind, skeleton, skin or clip bytes are repaired after freeze. Actual evaluated
native/browser world parity is still required independently.

`native-request.json` has exactly the native input below (paths/hashes are child-local):

```json
{"native":{"source":{"path":"source.blend","sha256":"ACTUAL_SOURCE_SHA256"},"spec":{"armature":"Rig","meshes":["Body"],"actions":["idle"]}}}
```

```bash
IMG2_CHARACTER_BPY_PYTHON=/absolute/path/to/venv/bin/python \
python3 tools/produce_routed_rig.py native --workspace CHILD_DIRECTORY \
  --request native-request.json --out .img2/artifacts/character/native-build
```

The new directory contains actual pre-bind `base.glb`, unmodified exporter `raw-bound.glb`, frozen-
normal-preserving `character.glb`, editable bound `character.blend`, measured `native.json`,
pre-bind `freeze.json`, and `native-inputs.json`.
Merge those input references with the admission request's `objectId`, independently authored `motion`,
`metricAnchor`, and a `sweep` reference. The sweep is an authored capture **plan** in the existing
format below, without frame `candidate`/`baseline` refs; cameras, interior ROIs, baseline GLB and
authorship sources must already be present and hash-bound. No automatic seam ROI, stance or metric
measurement is invented. Use a separately produced blend-off control with different effective skin
weights and a hash-bound `baselineSource`; renaming/repacking the candidate or declaring a
stock-linear self-control cannot authorize G10.

```bash
python3 tools/produce_routed_rig.py deliver --workspace CHILD_DIRECTORY \
  --request delivery-request.json --out .img2/artifacts/character/delivery
```

`deliver` requires the approved Node/browser/Three selectors below. It creates fresh runtime/RGBA
files, compares every exported vertex at five matched clip fractions with real bpy evaluated
positions, and runs existing admission before emitting D18. The existing documented native parity
limit is `1e-4 H`; no rig gate thresholds are changed. Split vertices are matched through actual
rest-world positions; ambiguous coincident vertices with differing deformation fail.
The routed terminal gate then independently repeats native export, binary freeze verification,
bound-master export and browser measurement. A saved native receipt or passing boolean never
substitutes for fresh execution; exact delivery GLB bytes and canonical freeze must reproduce.
The source master is never saved or modified.


`snapshot-input.json` contains `source:{path,sha256}` and optional
`assets:[{role,path,sha256}]`. The result is a fresh `{bindings,observations}` fragment for the base
controller's strategy/review/repair contexts. A `gate` asset must bind the current GLB and every
measurement input; changed evidence invalidates the snapshot. Unavailable views/candidates are not
invented. The base owns candidates, allowed operations, revision scope, consent/budget, decisions and
acceptance; this plugin neither imports it nor makes provider calls.

### Program-owned routed terminal gate

Registration is `routedTerminalGate: {id:"character-routed-terminal",
script:"tools/gate_routed_terminal.py"}`. The base must approve/pin this exact script and its
producer resources under the reviewed 3D gate contract, and independently rerun it. No marker,
old receipt, synthetic saved sweep or plugin decision can mark a child terminal.

```bash
IMG2_CHARACTER_NODE=/absolute/path/to/node22-or-newer \
IMG2_CHARACTER_BROWSER=/absolute/path/to/chromium \
IMG2_CHARACTER_THREE_ROOT=/absolute/path/to/reviewed/three-package \
IMG2_CHARACTER_THREE_SHA256=HOST_APPROVED_CANONICAL_PACKAGE_DIGEST \
IMG2_CHARACTER_BPY_PYTHON=/absolute/path/to/venv/bin/python \
python3 tools/gate_routed_terminal.py --workspace CHILD_DIRECTORY --artifact artifact.json
```

Node/browser overrides select existing absolute executables, never filenames/commands from child JSON.
Without them the gate uses **PATH `node` / PATH `chromium` only**, with no alternate-install fallback.
The native selector preserves the venv interpreter symlink invocation (realpath would discard its
site-packages); target executable bytes are hashed separately. Its fallback is exact PATH `python3`.
Route probes are `character-node>=22.0`, `character-chromium>=1.0`, `character-bpy>=4.3` and
`python3>=3.10`. Probe native availability using the selected interpreter with
`-I -B tools/bpy_capture_routed_rig.py --probe`: successful JSON binds `executable`, `bpyVersion`,
`bpyModule`; missing bpy or an older runtime exits 2. Native jobs use `-I -B` and OS-only environments.
Both browser executable version probes are bounded/no-shell. CDP and actual native/browser parity
are exercised, not inferred from versions. Paths, versions and executable/producer hashes are retained.
No executable, package or browser download is performed.

Three.js additionally requires the absolute host-owned `IMG2_CHARACTER_THREE_ROOT` and an
independently reviewed `IMG2_CHARACTER_THREE_SHA256`; neither can come from child/model/workspace
JSON. There is no production Node resolver override or self-approved digest fallback.
The approved digest is SHA256 of strict canonical UTF-8 JSON (sorted keys, compact separators,
no trailing newline) for `{kind:"img2.character-three-package",version:1,files:[{path,sha256}]}`,
with files sorted by path. The exact inventory is:

- `build/three.core.js`
- `build/three.module.js`
- `examples/jsm/loaders/GLTFLoader.js`
- `examples/jsm/utils/BufferGeometryUtils.js`
- `examples/jsm/utils/SkeletonUtils.js`
- `package.json`

Both gate and producer verify those actual bytes before and after execution and require version
0.186.1. Provenance is labelled **host-approved**, not third-party cryptographic attestation.
The fixed served/hashed module map includes both GLTFLoader utility imports; it never fetches
unlisted dependencies.

Node/version probes and Chromium receive allowlisted environments: OS temp/home/locale essentials,
a fixed system PATH, and only the explicit approved host selectors needed by Node. Chromium gets
OS essentials only. `NODE_OPTIONS`, `NODE_PATH`, native/script preload variables, proxies and API
credentials are not forwarded. A temporary ESM loader may aid offline tests only; it is not a
production dependency-selection or approval mechanism.

The gate requires child-local `state.json` with the base-created `routeChild` identity and
`artifacts.reference` bound by `routeChild.cropSha256`. It validates the exact D18 artifact hash,
object, all files and actual GLB skeleton/clip sidecars, then recomputes authoritative admission
read-only. It launches its own isolated local Chromium profile with pinned Three.js 0.186.1, runs
the actual runtime producer, and renders every required matched candidate/control frame. All new
RGBA buffers are measured again; missing views, empty/off-camera ROIs, dependencies, invalid
bindings, frozen-mesh drift or stale inputs block. Fresh stop restoration includes **every actual
skinned vertex**, in addition to node transforms.

The consumer keeps the opaque, source-sided normal diagnostic for G10 only, then renders the
candidate's original GLB materials at the same pose/camera with fixed neutral hemisphere and
directional lights. Every pose gets separate `N-material.rgba` (WebGL bottom-up) and
`N-material.png` (top-down) evidence; original materials/textures are not replaced or recoloured.
The fresh sweep records `materialCapture: "original-material-fixed-lighting-v1"` and binds
`frame.material` (PNG) / `frame.materialRgba` separately from diagnostic `candidate` / `baseline`.
The material buffers are straight-alpha RGBA8 in sRGB, with transparent RGB canonicalized to
zero. The producer unassociates the sRGB framebuffer's blended color in linear light, then
encodes a top-down PNG directly from those bytes; it does not round-trip through Canvas2D's
lossy low-alpha backing store. `measurement.materialPixels` declares this representation.
Binding requires Pillow to decode and CRC-verify the actual 8-bit PNG, checks dimensions,
and compares every decoded RGBA pixel against the vertically flipped raw buffer, including alpha.
Core owns the bounded semantic image inventory, canonical posed `render` selection and distinct
static `rest-render` role. Input order is not a semantic pose-selection contract; core must not
score normals as materials or disclose local paths in observations.
These captures do not by themselves prove material fidelity, likeness, arbitrary viewer behavior
or unseen-pose Blender equivalence. Independent stance/side-label sources, ROIs and metric anchors
remain required.

Decision snapshot fragments reject duplicate roles even when paths differ, including a second
`source`. Retained gate inputs have unique `gate-input:0`, `gate-input:1`, … roles in bound-input
order, deduplicated by path. `gate-input` and the `gate-input:` prefix are reserved for that
transport inventory; they are not semantic view labels or permission/qualification claims.

No original artifact, incumbent capture, mesh, skeleton or bind matrix is rewritten. Actual new
captures and their measurement index are retained under `.img2/artifacts/character/terminal-live/`
and `terminal-measurements/`. The verdict is `img2.gate-verdict` v1 with
`evidence.artifact:{path,sha256}` binding the exact checked artifact, separate reference/subject
bindings and actual measurement evidence. Missing producers return a non-passing verdict.

Read-only checks and negative coverage do not require enabling the live integration test.
To execute the separately opt-in **real-bpy/browser synthetic-geometry diagnostic**, configure the
same existing native/Node/browser executables and host-approved Three package and set
`IMG2_CHARACTER_RUN_LIVE_TESTS=1`; this is not independent-subject or release qualification.

Focused checks (requires the existing img2 core link and declared Three.js dependency):

```bash
node --test tests/rig-measurements.test.mjs
npm run test:capture
python3 -m unittest discover -s tests -p test_rigged_artifact.py
python3 -m unittest discover -s tests -p test_gate_routed_terminal.py
python3 -m unittest discover -s tests -p test_routed_native.py
python3 -m unittest discover -s tests -p test_gate_rigging.py
python3 -m unittest discover -s tests -p test_domain_declaration.py
```

The new Python positive case executes real GLB/Three CPU data but uses explicitly synthetic RGBA
fixtures. It is protocol evidence, **not** real-browser, Blender parity, visual quality or release proof.

The complete real-producer diagnostic is also directly runnable (the directory must be new):

```bash
python3 tests/native_routed_smoke.py --workspace /absolute/new/disposable-character-smoke
```

It creates explicitly synthetic native geometry with nonzero deformation, executes native build,
owned browser delivery and the actual terminal CLI's independent replay, and retains
`smoke-result.json`. It never substitutes Chrome for bpy or calls fixture data an expert corpus.


## Tests

The non-native suite needs the pinned NumPy/Pillow test dependencies and declared Three.js.
Python tools load `img2_core` from the exact CLI dependency, not an unrelated pip package.
Use a disposable home; absent oracle/showcase/base fixtures are explicitly unverified, not passes.

```bash
npm ci --ignore-scripts
npm --prefix cli install --ignore-scripts --no-audit --no-fund
python3 -m pip install --only-binary=:all: -r requirements-test.txt
npm test
npm --prefix cli test
TEST_HOME=$(mktemp -d)
mkdir -p "$TEST_HOME/img2"
HARNESS="$PWD/cli/node_modules/@img2threejs/img2"
ln -s "$HARNESS" "$TEST_HOME/img2/harness"
HOME="$TEST_HOME" IMG2_HOME="$TEST_HOME/img2" IMG2_HARNESS_DIR="$HARNESS" \
  PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

CI is configured to run the complete Node suite (including experimental VM modules) and one-process Python
discovery on Python 3.10/3.12 with Node 24; native/browser and external subject qualification
remain separate, opt-in gates.

```bash
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


`tests/test_oracle_replay.py` compares the complete canonical rig report against a project-authored,
genuinely skinned primitive with three animation clips. Its local GLB/report/hash manifest are generated
by the repository-maintenance script `scripts/generate_synthetic_rig_oracle.py`, not a workspace runtime CLI. Caller asset/report pairs can be supplied explicitly.

## Licence

Apache-2.0.

Historical asset-specific studies, calibration, measured tables and copied evidence have been replaced
in HEAD with independently authored synthetic geometry/configuration and caller-data contracts.
This does not erase history, grant rights to historical or caller assets, or constitute legal approval.
See [NOTICE](NOTICE). Synthetic fixtures do not waive source admission, G10, material or native/parity gates.
