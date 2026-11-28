# Changelog

All notable changes to **plugin-character** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Replace unclear-rights subject calibration, studies, measured tables and copied garment/rig
  receipts in HEAD with independently authored synthetic geometry/configuration and caller-data contracts.
  The garment viewer now requires explicit real-input calibration and uses `window.garmentStudio`;
  missing limits remain unmeasured. Plans forward the selected `catalogueFile` consistently.
  No original-asset fidelity, native acceptance, rights grant or history erasure is claimed; see `NOTICE`.
  G10, material, native/parity and required gate thresholds are unchanged. The former subject-specific
  advisory hair-layout table is removed; real hair count still requires the caller's declared reference.
- Replace the external-asset rig oracle with a genuinely skinned, project-authored primitive:
  six joints in deliberately non-node order, true inverse binds and translation/rotation/scale clips.
  The complete canonical report and GLB are pinned by `tests/fixtures/oracle-synthetic/manifest.json`;
  regenerate with `tools/generate_synthetic_rig_oracle.py`. Caller GLB/report pairs remain explicit.
- Require caller-selected cheek landmark factors, texture padding/repair gates, pigment curves and
  tone-deviation limits instead of historical subject presets. Generic image/mesh algorithms remain.
- Remove remaining historical rig-intake, bind-rendering and animation-observation prose.
  Animation regressions now use independently authored analytic tracks rather than copied clip
  measurements; threshold provenance explicitly describes retained legacy policy, not synthetic calibration.
- Measure moved garment triangle centres directly: rest-pose sag and clear corners cannot
  bound clearance after a lateral pull crosses a new ridge. Preserve existing clearance floors
  and correction passes; remove the unsound centre-pruning shortcut and its unused storage/parameter.
- Recognize valid empty garment evidence containers and report missing named gates instead of
  a layout error, while continuing to reject malformed container types.

- Decode and CRC-verify material PNGs and require exact upright RGBA equality with their
  bottom-up raw evidence, rather than accepting dimensions or matching filenames alone.
- Emit declared straight-alpha sRGB material pixels; unassociate framebuffer color in linear
  light and encode PNG bytes directly so partially transparent colors survive losslessly.
- Reject duplicate decision binding roles across distinct paths and give retained gate inputs
  individually addressable reserved roles; semantic image selection remains core-owned.
- Require a separately authored, source-bound G10 blend-off control; reject candidate-equal
  GLBs and equivalent effective skin influences even when containers or influence slots differ.
- Author the synthetic native control from the same saved subject before changing weights,
  preserving exact polygon/index order rather than regenerating a nondeterministically ordered sphere.
- Observe browser navigation/load promises together so a timeout closes the owned browser
  instead of escaping cleanup through an unhandled rejection.
- Keep disposable headless capture off the desktop credential store, avoiding cookie-store
  initialization stalls without retries, timeout increases or acceptance-threshold changes.
- Keep normal diagnostics for seam checks and separately capture original GLB materials as
  pose-bound PNG/RGBA evidence under fixed lighting. Core must consume actual material evidence
  as `render`; local paths remain outside semantic observations.
- Prepare plugin/runtime version 0.4.0 and matching current extraction/parity producer provenance.
  Keep the historical oracle byte-original; validate its old stamp and derive only the expected
  current producer stamp from product metadata, without normalizing output or excluding more fields.
  External-subject replay remains unverified.
- Add complete Node and Python test CI and a runnable VM-module capture command. Native/browser
  qualification and missing external oracle/showcase/base fixtures remain separate evidence.

### Added

- D18 rigged artifact extraction/admission from actual embedded GLB accessors: skin order,
  inverse binds, canonical skeleton/animation evidence, measured bounds and metric-anchor scale.
  Admission re-evaluates the twelve checks against hash-bound runtime, motion, freeze and raw
  rendered-sweep inputs; missing/stale producers block rather than producing an artifact.
- Delivered-controller Three.js measurement producer for binding, distinct-vertex deformation,
  stop restoration and visible mesh coverage; raw RGBA seam-ROI sweep measurement with matched
  camera/pose evidence and the same subject's blend-off baseline.
  The baseline remains hash-bound source evidence outside the D18 renderable inventory.
- Rig-intent route card with dependency probes, fresh decision-context binding/observation
  fragments, retained diagnostic gate evidence and focused negative/actual-CPU-data tests.
- A distinct routed-only terminal gate, registered as data in the route card without changing
  global legacy gates. It binds child/reference/artifact identity, recomputes admission read-only,
  executes fresh local Chromium/CDP runtime and RGBA producers, and retains every resulting
  capture plus executable/producer hashes. Missing or stale producers cannot pass on old receipts.
  Bind restoration now also measures every deformed vertex. Host-only scoped Node/Chromium
  probes use the same exact executable resolution as the gate, with no downloads or alternate-install
  fallback. Includes negative/read-only tests and a separately opt-in real-browser diagnostic.
- Closed the pinned GLTFLoader browser module inventory with `SkeletonUtils.js`, including serving
  and receipt hashing, plus an offline native-ESM linking regression that rejects its omission.
- Allowlisted Node/Chromium child environments exclude loader/preload hooks and API credentials.
- Resolve terminal/native producer resources from the adjacent tools directory, independently
  of any project checkout root or workspace; isolated harness doctor can inspect the package.
  Production Three selection now requires an explicit host root and reviewed canonical package
  digest, verified before/after capture and labelled host-approved rather than third-party attested.
  Missing approval or changed bytes fail closed; environment injection and pin mismatch have
  dedicated negative regressions.
- Blocking rigging workspace evaluation now shares the routed native/browser evaluator; arbitrary
  saved diagnostic payloads no longer authorize terminal delivery. Explicit payload checks remain
  diagnostic. Missing native runtime or measurement inputs are non-passing, not exemptions.
- Owned native base-mesh → pre-bind binary freeze → additive linear bind → exported GLB/editable
  master production and D18 browser-delivery commands. Terminal admission reopens the bound source
  and master, reproduces exact delivery bytes, and compares real evaluated native poses with fresh
  browser vertices. Existing native `1e-4 H` parity and all twelve rig thresholds are preserved.
  Native Python invocation preserves isolated-venv symlinks; capture environments exclude hooks and
  credentials. Includes counterexamples and an explicitly synthetic, opt-in real bpy/browser smoke.
- Native working geometry is canonicalized to world space before freeze, preserving the source
  frame/snapshot and measured world correspondence. Frozen POSITION/UV/index/order remain exact;
  the authored pre-bind NORMAL payload is preserved through bpy's extra skin-normal normalization,
  with raw-bound bytes retained. No tolerance aliases frozen buffers or bypasses evaluated poses.

### Qualification limits

- Real-reference likeness, independent held-out visual quality and release eligibility remain
  unqualified. Native/browser diagnostics demonstrate only their explicitly measured boundaries.
- Static rigs can be extracted, but routed static delivery requires an approved measured static-rig
  gate applicability policy. Unsupported morph/multi-skin/external-resource representations block
  this new adapter without changing existing optional authoring or interaction paths.
- Third-party-derived garment/transfer measurements and missing source rights remain unresolved.
  Existing material is preserved pending a scoped provenance decision; source licensing is not
  an asset permission grant.

## [0.3.0] - 2026-11-10

### Fixed

- Measure pose strain using the rest mesh triangulation while checking polygon topology, avoiding false topology failures when Blender changes a quad's tessellation during deformation.
- Restrict skin-authoring atlas overlap candidates to materials containing the named image, and select direct base-colour material measurements by atlas when one is supplied. Shader contribution and UV mapping still require inspection.
- Resolve the skin/body planner's bpy interpreter from `IMG2_HOME` or an explicit `--bpy-python`, instead of an author's machine path.
- Keep the independent skin-probe regression separate from the copied garment runtime's integrity manifest.

### Added

- Explicit `skin-body` route: generic caller-data texture/body-part tools and workflow documentation.
  The current catalogue inventories project-authored primitives; no historical subject catalogue is shipped.
  See `reference/skin-body-distillation.md`, `skin-texture.md`, `skin-atlas-authoring.md` and `body-parts.md`.
- Interpolation round (`reference/reference-relative-standards.md`): standards derived from the reference characters are reference-relative. New
  gate comparators `reference-within` (symmetric, or one-sided with `direction`), `no-worse-than-baseline` (`direction`,
  signed baselines), `declared-min` / `declared-max`, wildcard metrics that also expand over declared keys (omitting a region or
  pose can never pass), `severity: advisory` (`warn`, exit code unchanged) and merged stage fragments.
  Subject-specific island-tone, export and hair-count checks require caller declarations; no measured
  source ranges or fixed subject hair layout are shipped.
- New stages: S2B `reference/skin-body-standards.s2b-skin-authoring.json` + `tools/skin_authoring.py`
  (reference-patch tone targets, per-pixel L*, feathering only inside adjacent bands, mirror consistency, bounded padding) +
  `tools/bpy_measure_skin_authoring.py`; S9 `…s9-geometry.json` + `tools/bpy_measure_geometry.py` (landmark ratios, mirror
  coverage and error, welded topology, UV overlap/gutter/density, budgets); S10 `…s10-rig.json` and S11 `…s11-hair.json` +
  `tools/bpy_measure_rig_motion.py` (fixed-triangle strain statistics under a pose sweep, quaternion continuity, hair
  clearance). The rig/hair measurer is partial (rebase trusts supplied deltas, loop lacks vertex/velocity seam, scalp coverage
  uses caller rays, joint section checks the head plane only) and documented as such in `reference/rig-motion-standards.md`.
- Agents + bpy layer for the skin/body route: `reference/skin-body-standards.json` (S1–S8 acceptance checks, each tagged
  `single-subject` or `behaviour` with its case), `tools/bpy_measure_skin_body.py` (opens a `.blend`/GLB under bpy and
  measures source hashes, protected-region pixels, repair-mask boundary, island tone, UV/weight/mirror parity, bone groups,
  hair chains, neutral masks and material without editing it), `tools/gate_skin_body.py` (pass | fail | unmeasured, exit
  0/1/2; unmeasured is never a pass; forbidden region ids fail), `tools/skin_body_plan.py` and
  `reference/skin-body-agent-contract.md` (role, ownership, forbidden actions, run commands per stage). A real-bpy test
  builds a synthetic character, measures it, passes S1, S2, S4, S5 and S6 together and fails on a perturbed pixel, source
  hash, island tone, UV and weight. S3, S7 (export maps/browser SSS) and S8 stay unmeasured without join, export or GLB
  evidence by design.
- `tools/skin_texture.py` (+ `tools/atlas_surface.py`): skin texture pipeline as pure-numpy cores — UV region
  rasterisation with an overlap report, tone measurement that names its colour space, island fill, neck shadow lift,
  root-paint repair that cannot wrap across image edges, detail/iris recolour, composite and linear-light bridge with
  resolution-invariant UVs, save-pack-verify (fails on stale packed bytes), skin material spec/validator
  that reports what the export does not carry. Current tests use independent small synthetic arrays;
  historical asset-specific tone gains and claimed measured comparisons are no longer distributed.
- `tools/body_parts.py` + `reference/body-parts.json`: body-part catalogue per asset and stage, neutral soft-region mask
  evaluation, mirrored-weight symmetry check that reports unmatched/ambiguous pairs instead of passing, and a validator
  that rejects region ids outside the neutral allowlist.
- `tools/head_transplant.py`, `tools/hair_chain_rig.py`, `tools/bake_hair_motion.py`: similarity fit, plane clip, welded
  ring bridge with a manifold report, cheek masks, seam-equal hair chain weights, constant-length spring bake (no
  collision solver).
- `reference/character-transfer-exercise.md`: parameterized second-character construction and
  fixed-view causal correction. Accept a pose/outfit-appropriate reference before authoring;
  a seated swimsuit image is not standing silhouette evidence. An authorized generated turnaround
  may serve as an explicitly synthetic target after actual-image inspection and user design review;
  disclose cost/visibility and retain operation provenance, scale checks and occlusion limits.
- Read-only `tools/extract_construction_prior.py` and `tools/character_prior/`: source-hashed GLB
  inventory, conditional anatomy/face/atlas measurements and construction hypotheses, with 118
  regression tests. A source-output alias is rejected; static normals use inverse-transpose transforms.
- `reference/character-construction-prior.md`: learn continuous form, regional contact density, face UV
  allocation and painted skin from an existing character, then refit them to the next reference.
  No measured prior is bundled: `tools/extract_construction_prior.py` generates one from a GLB you supply and may analyse.
  Preserve source attribution, null landmarks and heuristic limits; topology does not recover
  modifier history. Source SIMPLE subdivision preserves form, not a recovered smoothing operation.
- Explicit `garment-character` route: connected surface fields, transitions, contact and independent probes.
  Current runtime dimensions and selections are explicit per-input calibration; the default scene/configuration
  is independently authored synthetic geometry, not original-character acceptance evidence.
- `runtime/garment-character/` integrity manifest records all runtime/test hashes and sizes.
  `tools/extract_garment_parameters.mjs` generates generic mechanics constants and synthetic configuration;
  `tools/generate_synthetic_reference.py` generates primitive catalogue and constructed gate contract inputs.
  No copied browser/native receipts or source-literal measurement inventory is shipped.
- Explicit `blender-character` skill workflow: reference/camera analysis, native bpy geometry,
  source-asset rights, UV/skin/fabric PBR, skeleton/weight authoring, soft regions and browser evidence.
  Includes coordinator-owned agent handoffs; rejects neural mesh fallback when the user forbids it.
  This is authoring guidance using existing export/runtime tools, not an automatic avatar generator.
- Native export/browser parity guidance for quaternion versus linear skinning, stock skin SSS,
  morph normal/tangent support, UV shading and sampled animation versus live simulation.
- Raw Base Color baking through temporary Emission, with verified saved-pixel encoding and material
  restoration. Distinguish diffuse-lobe colour from raw RGB and neutral self-bakes from authored detail.

- Explicit `cc5-headshot` agent route, independent of procedural reconstruction and the
  unchanged `animated-character` harness domain.
- `tools/cc5_headshot.py`: bpy/Auto Setup preflight; saved Auto Setup character input;
  official glTF material bake and GLB export; source-hash, skin, morph and image checks.
  Export receipts remain `exported-unreviewed` until real visual/deformation acceptance.
- Route documentation for the licensed Windows CC5/Headshot handoff and Three.js consumer.
- Export-integrity tests and an opt-in real bpy regression: reject a non-CC `.blend` without
  crashing, changing the source or producing a fake output.
- Composable `softbody-character` route for admitted CC5 or AI/stylized assets, without
  replacing either source route or rebinding their skeletons.
- `tools/prepare_softbody.py`: authored vertex-group masks, source-preserving bpy export,
  GLB custom attributes, sidecar and an explicitly unreviewed integrity receipt.
- `runtime/softbody.mjs`: dynamic/static triangle partition, weighted size controls,
  four-substep spring/damping, posed raycast indentation/bulge/drag/release, normals and
  hair-mask following; shared skin/morph state and reversible disposal.
- Original local diagnostic viewer with local GLB/sidecar loading; Node behavioral tests
  and optional real-bpy preparation regressions.

### Fixed

- Preserve tangent-space fabric PBR in `tools/prepare_softbody.py`: request glTF tangents when
  used materials contain normal-map nodes, without applying geometry modifiers or changing the
  native source. Fabric export requests tangent attributes and supports independently comparing semantic
  colour/normal/roughness/metallic image channels against caller-owned packed native maps.
  Blender's global tangent option can still warn on an unrelated non-normal-mapped n-gon surface;
  do not alter protected anatomy merely to silence that unused-tangent warning.
- Independent skin probes now classify triangle bounds in posed world space, retain crossing
  triangles, use conservative nearest-distance bounds and fall back outside the coarse ROI.
  Four geometric regressions fail before and pass after; the old pruning could falsely report clean.
- Prevent soft-body field foldover and excessive edge strain using an analytic
  rest-to-candidate topology guard; preserve coincident UV vertices and static boundaries.
- Add curved-surface contact/release and first-collapse regression coverage.
- Keep smooth shading continuous across UV splits during contact without blending authored
  hard edges or different skin/morph/deformation fields; add hard-edge regression coverage.
- Add explicit camera framing to the diagnostic viewer for close-up asset inspection.

### Runtime notes

- Native workflow smoke exercised bpy 4.5.15 source-preserving preparation with original packed
  2×2 PBR maps, two-bone weights, a morph target and a clip. Flat/smooth diagnostic meshes loaded
  in Three.js and exercised posed pointer drag/release/reset with protected/static geometry intact.
  These fixtures are not reference avatars or proof of facial rigging, likeness or photorealism.

- Tested preflight and source rejection on macOS arm64 with bpy 4.5.15 / Auto Setup 2.4.5.
  Load the source before registering the add-on, create process-local preferences, disable
  interactive Data Link callbacks and release the preview collection before interpreter exit.
  Omitting this lifecycle handling caused shutdown crashes during the runtime smoke.
- Real CC5 character conversion and browser acceptance have not been exercised without a
  real reference and an imported Auto Setup project. No photorealistic avatar is implied.
- Soft-body smoke used original diagnostic geometry, bpy 4.5.15 and Three.js 0.186.1:
  unchanged source hash, exported masks, two-joint skin, morph and an exercised animation clip.
  Browser size/hair deformation, posed press/drag/release and neutral reset were observed;
  this is not evidence of real-character likeness or mobile-device performance.

## [0.2.0] — 2026-09-03

### Added

- **The `animated-character` domain declaration** (`domain.json`): the two character setup steps
  (verbatim base-relative — the static `character` domain stays in-repo and owns those assets) and
  the nine Stage R rig steps, appended after the base's FINAL steps via the registry's `rigSteps`
  vocabulary (harness ≥ 0.2.3). This plugin is now the canonical owner of the rig-step ORDER; the
  two-file pin in `tests/test_domain_declaration.py` guards it, and the freeze-before-bind rationale
  lives in that file's docstring. OpenSpec change: `extract-animated-character` (two-adversary
  review; command deviations from the old in-repo strings are enumerated in its design D4).
- **`gate_rigging.py --payload <path>`** — the checklist-step mode: an explicit payload path with no
  workspace resolution, because the base pipeline's workspace is its checkout, which
  `resolve_workspace` refuses. `--workspace` remains the terminal `gates.json` mode.
- Reference-doc drift pins (content hashes) for the two contract documents `rig-contract-read`
  reads from `{plugin_dir}/reference/`.

### Changed

- **The `rigging` gate is declared `blocking: false`.** Four of its twelve checks have no producer
  yet, an unevaluated check is honestly an `error`, so the gate cannot return `pass` on a healthy
  rig — a blocking declaration would halt any sweep on an honest verdict. **Re-block trigger:** the
  four producers exist and the gate passes the oracle rig. A fail is still recorded in the
  `img2.gate-run` aggregate; it just does not stop it.
- `clip-measure` writes `clip-features.json` (the base step was stdout-only): `--out` is required
  because bare cwd resolution would hit the checkout refusal.
- `plugin.json`: version 0.2.0, `requires.harness: ">=0.2.3"` (the release that admits `rigSteps`).

### Rollback

Reverting to 0.1.0 removes the domain declaration: `--profile animated-character` fails loud naming
the available profiles, and an in-flight workspace is refused until a provider returns — it resumes
unchanged when one does. The base-side module deletion rolls back by `git revert`, not `img2 remove`.

[Unreleased]: https://github.com/img2threejs/plugin-character/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/img2threejs/plugin-character/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/img2threejs/plugin-character/compare/5b12a14...v0.2.0
