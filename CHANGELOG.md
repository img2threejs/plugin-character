# Changelog

All notable changes to **plugin-character** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  Production Three selection now requires an explicit host root and reviewed canonical package
  digest, verified before/after capture and labelled host-approved rather than third-party attested.
  Missing approval or changed bytes fail closed; environment injection and pin mismatch have
  dedicated negative regressions.

### Qualification limits

- The global rigging gate remains non-blocking, and this route remains ineligible, until an actual
  complete browser/oracle run proves producer readiness. Synthetic sweep fixtures are not that proof.
- Static rigs can be extracted, but routed static delivery requires an approved measured static-rig
  gate applicability policy. Unsupported morph/multi-skin/external-resource representations block
  this new adapter without changing existing optional authoring or interaction paths.

## [0.3.0] - 2026-11-10

### Fixed

- Measure pose strain using the rest mesh triangulation while checking polygon topology, avoiding false topology failures when Blender changes a quad's tessellation during deformation.
- Restrict skin-authoring atlas overlap candidates to materials containing the named image, and select direct base-colour material measurements by atlas when one is supplied. Shader contribution and UV mapping still require inspection.
- Resolve the skin/body planner's bpy interpreter from `IMG2_HOME` or an explicit `--bpy-python`, instead of an author's machine path.
- Keep the independent skin-probe regression separate from the copied garment runtime's integrity manifest.

### Added

- Explicit `skin-body` route: the skin texture and body parts of reference characters as reusable knowledge and tools.
  `reference/skin-body-distillation.md` (19 rules, each with its case), `skin-texture.md`, `skin-atlas-authoring.md`,
  `body-parts.md` + `body-parts.json`, `head-hair-authoring.md`.
- Interpolation round (`reference/reference-relative-standards.md`): standards derived from the reference characters are reference-relative. New
  gate comparators `reference-within` (symmetric, or one-sided with `direction`), `no-worse-than-baseline` (`direction`,
  signed baselines), `declared-min` / `declared-max`, wildcard metrics that also expand over declared keys (omitting a region or
  pose can never pass), `severity: advisory` (`warn`, exit code unchanged) and merged stage fragments. The base S1–S8 checks
  that were fixed single-subject thresholds (island tone .08, export tolerances, hair chain count) are now declared limits /
  references / advisory; no case ranges are shipped.
- New stages as fragments: S2B `reference/skin-body-standards.s2b-skin-authoring.json` + `tools/skin_authoring.py`
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
  resolution-invariant UVs, save-pack-verify (fails on stale packed bytes), skin material spec/validator that reports
  what the export does not carry. A synthetic-atlas smoke reproduced the case numbers: neck gain
  `[1.09272,1.24632,1.36447]` vs the job's `[1.09091,1.24713,1.36620]`, 0 changed pixels outside the supports.
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
- `reference/robin-transfer-study.md`: measured native Robin adaptation, exact protected source
  correspondence, packed-image/export parity, actual nine-region mouse/touch, bounded garment
  replay, concave-ear sign confirmation and documented visual/physical/process limitations.
- Read-only `tools/extract_construction_prior.py` and `tools/character_prior/`: source-hashed GLB
  inventory, conditional anatomy/face/atlas measurements and construction hypotheses, with 118
  regression tests. A source-output alias is rejected; static normals use inverse-transpose transforms.
- `reference/character-construction-prior.md`: learn continuous form, regional contact density, face UV
  allocation and painted skin from an existing character, then refit them to the next reference.
  No measured prior is bundled: `tools/extract_construction_prior.py` generates one from a GLB you supply and may analyse.
  Preserve source attribution, null landmarks and heuristic limits; topology does not recover
  modifier history. Source SIMPLE subdivision preserves form, not a recovered smoothing operation.
- Explicit `garment-character` route, composed after native/admitted-asset preparation and
  `softbody-character`: connected garment (one cloth surface, pulls weighted by distance along it), in-place
  outfit change, round chest field and an outer-layer guarantee (the skin is never in front of the cloth).
  `reference/garment-character-route.md` (stages, parameters tagged `single-subject`/`behaviour`, honest
  scope, replay, limits) and `reference/garment-acceptance.md` (items `A1`–`A13`: delivered numbers,
  measuring command, counter-example that must fail).
- `runtime/garment-character/`: the delivered viewer runtime copied byte-identical with
  `manifest.json` (sha256 and size of every runtime file and node test); `tests/garment-character/` (47 node tests, `npm run test:garment`);
  `tools/extract_garment_parameters.mjs` + `reference/garment-parameters.json` (constants and 80 hand-read
  subject literals); `tools/skin_probes.js` (independent browser probe of skin versus cloth);
  `tools/gate_garment.py` (clean, coverage, phases, relative hard pull, exact release; `--sampling-declared`
  for matrices that record only a total sample count) with fixtures under `tests/fixtures/garment-gate/`.
- Scope: the viewer was developed against a licensed third-party asset that is not bundled, not a result
  of reference images alone. The route reproduces workflow, runtime, parameters and gates; it does not promise
  the same result from images, a likeness or general cloth physics. Evidence is headless Chromium with touch
  emulation; the outfit-change fall is outside the outer-layer guarantee.
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
  native source. The Robin fit/fabric export verifies all four garment tangent attributes and
  exact semantic colour/normal/roughness/metallic image channels against the packed native maps.
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
