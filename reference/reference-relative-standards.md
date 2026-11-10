# What two related reference characters can and cannot teach

Question: from two related reference characters, what can be extrapolated or interpolated into standards for building *other* characters?
Answer in one line: **methods, definitions and invariants transfer; numbers do not.** Standards are therefore *reference-relative*: a new
character is judged against its own declared reference, baselines and limits. No per-case numeric range is shipped as a standard.

## The data problem
- **Two samples are not a population.** The two reference characters are related: they share body geometry, the corrected rig and much of
  the atlas. Agreement between them is mostly the same asset seen twice.
- **One measurement is invalid.** The historical Robin eye detector selected the sunglasses, so eye-line and eye-separation proportions
  built on it are false positives and void; the nose estimate depends on the same bound.
- **Robin's prior is pre-donor-head.** Its colours, densities and head box describe the historical head, not the later transplant.
- **Measurement frames differ.** Heights come from heuristic silhouette bands; hair and accessories change H without a body edit.

## What each area yields

| area | transfers as | does not transfer |
|---|---|---|
| geometry | the *definitions*: height-normalised landmarks, arm angle against vertical, mirror coverage **and** error, welded boundary/non-manifold counts, UV overlap/gutter, area-weighted texel density | heads-tall, shoulder/H, A-pose angle, face:body density and UV shared-pair ranges: descriptive of two related bodies |
| skin texture | the *procedure*: semantic regions, reference patches, encoded vs linear-light statistics, feather only inside adjacent bands, bounded padding, zero change outside support | the palette, densities, deviation flags and L* means: sampled from painted, density-biased vertices |
| rig | *how to place joints*: from mesh sections, not copied heights; rebasing by world-delta conjugation; quaternion sign continuity | absolute heights, bone counts, gait speeds |
| weights | monotone chains, mirror checks, fixed-triangle strain statistics under a pose sweep | any absolute strain cutoff: no comparable independent sweep exists |
| hair | clearance with an *approved-exception baseline*, root pin drift, exposed-scalp-paint area | chain counts, pin height, spring settings, approved inside-vertex counts (an exception, not an allowance) |

## How this changed the pipeline
1. **Comparators:** `reference-within`, `no-worse-than-baseline` (with `direction`), `declared-min` / `declared-max`, wildcard metrics that
   also expand over *declared* keys (so omitting a region or pose from the evidence cannot turn a gate into a pass), and
   `severity: advisory` (reported `warn`, never changes the exit code).
2. **Declare first:** the integration owner records the target's reference, baselines and limits before authoring; the gate judges the
   built character against *those*.
3. **New stages** (fragments next to `skin-body-standards.json`): S2B skin authoring from a reference, S9 geometry/topology/UV,
   S10 rig and pose deformation, S11 hair fit. Their measurers (`bpy_measure_skin_authoring.py`, `bpy_measure_geometry.py`,
   `bpy_measure_rig_motion.py`) never edit the file.
4. **Case ranges removed:** the advisory `single-subject` ranges that embedded values of the related characters were deleted; only
   reference-relative declared values are valid.

## Still unmeasured, by design or by gap
Pores/micro-detail/de-lighting (never authored); hand and foot lengths; camera-calibrated landmarks; posed self-intersection;
continuous-time hair collision; gait (not implemented); the rig measurer's rebase (trusts supplied deltas), loop (no vertex/velocity seam),
scalp coverage (caller-supplied rays) and joint-section interval membership are partial — see `rig-motion-standards.md`.
A third, *independent* character would be the first real test of any numeric range.
