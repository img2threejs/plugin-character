# What two characters can and cannot teach — Nami and Robin

Question asked: from Nami and Robin, what can be extrapolated or interpolated into standards for building *other* characters?
Answer in one line: **methods, definitions and invariants transfer; numbers do not.** The standards that came out of this analysis are
therefore *reference-relative*: a new character is judged against its own declared reference, and the two cases appear only as
advisory sanity ranges.

## The data problem
- **Two samples are not a population.** Robin is adapted from Nami: they share body geometry (direct correspondence recorded in
  `evidence/nami-native-construction.json:37-60`), the corrected rig, and much of the atlas. Agreement between them is mostly the same
  asset seen twice.
- **One of Robin's measurements is invalid.** The historical Robin eye detector selected the sunglasses: eye line / head height 0.921207
  and eye separation / head width 0.388151 are false positives (`evidence/construction-prior.json:8816-8828,9654-9666`). Any proportion
  built on them is void; the nose estimate depends on the same bound.
- **Robin's prior is pre-donor-head.** Its colours, densities and head box describe the historical head, not the later transplant.
- **Measurement frames differ.** Heights come from heuristic silhouette bands; hair and accessories change H without a body edit.

## What each area yields

| area | transfers as | does not transfer | evidence |
|---|---|---|---|
| geometry | the *definitions*: height-normalised landmarks, arm angle against vertical, mirror coverage **and** error, welded boundary/non-manifold counts, UV overlap/gutter, area-weighted texel density | heads-tall (7.648546–8.071166), shoulder/H (.161609–.170202), A-pose 33.333063–33.521570°, face:body density 3.677–3.694, UV shared-pair .98643–.98654 — descriptive of two related bodies | `GeometryScout` |
| skin texture | the *procedure*: semantic regions, reference patches, encoded vs linear-light statistics, feather only inside adjacent bands, bounded padding, zero change outside support | the palette (#f5ccb1 / #eecbb5 …), densities, `.08` deviation flag, L* means — sampled from painted, density-biased vertices | `SkinHairScout` |
| rig | *how to place joints*: from mesh sections, not copied heights (knee .47475 vs section .60–.62; ankles 37.42 mm apart); rebasing by world-delta conjugation (0.596454 rad → 2.27e-7 rad); quaternion sign continuity (92 → 0) | absolute heights, bone counts (80 vs 53), gait speeds (they are two clips of one character) | `RigMotionScout` |
| weights | monotone chains, mirror checks, fixed-triangle strain statistics under a pose sweep (17.118× → 1.0096×; knee p99 2.039 → 1.489) | any absolute strain cutoff — Nami has no comparable sweep; deep-knee compression persisted after the spike was fixed | `RigMotionScout` |
| hair | clearance with an *approved-exception baseline*, root pin drift, exposed-scalp-paint area | chain counts, pin height 1.63 m, spring settings, the 236 approved inside vertices (an exception, not an allowance) | `SkinHairScout` |

## How this changed the pipeline
1. **Comparators:** `reference-within`, `no-worse-than-baseline` (with `direction`), `declared-min` / `declared-max`, wildcard metrics that
   also expand over *declared* keys (so omitting a region or pose from the evidence cannot turn a gate into a pass), and
   `severity: advisory` (reported `warn`, never changes the exit code).
2. **Declare first:** the integration owner records the target's reference, baselines and limits before authoring; the gate judges the
   built character against *those*.
3. **New stages** (fragments next to `skin-body-standards.json`): S2B skin authoring from a reference, S9 geometry/topology/UV,
   S10 rig and pose deformation, S11 hair fit. Their measurers (`bpy_measure_skin_authoring.py`, `bpy_measure_geometry.py`,
   `bpy_measure_rig_motion.py`) never edit the file.
4. **Advisory ranges:** the Nami/Robin numbers above live in advisory checks tagged `single-subject`.

## Still unmeasured, by design or by gap
Pores/micro-detail/de-lighting (never authored); hand and foot lengths; camera-calibrated landmarks; posed self-intersection;
continuous-time hair collision; gait (not implemented); the rig measurer's rebase (trusts supplied deltas), loop (no vertex/velocity seam),
scalp coverage (caller-supplied rays) and joint-section interval membership are partial — see `rig-motion-standards.md`.
A third, *independent* character would be the first real test of any of these ranges.
