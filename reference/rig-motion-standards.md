# Rig, deformation and hair measurements

These are same-subject comparisons, not anatomical norms. Related reference characters share a source, and no comparable posed triangle sweep across independent subjects was established. Supply independently reviewed reference values, per-sample baselines, project limits and their provenance to the evidence gate. Missing data is unmeasured, not a pass. The measurer opens the blend without saving it; work on a disposable copy if other tools have auto-save behavior.

## Invocation and declarations

Run `bpy_measure_rig_motion.py --blend FILE --armature NAME --body NAME --poses POSES.json --chains CHAINS.json --joint-sections SECTIONS.json --face-ids GROUP --hair OBJECT --rest-reference REBASE.json --out evidence.json`. Optional inputs may be omitted; their metrics then remain unmeasured. `--face-ids` names a body vertex group. World Z bounds define H. Inputs and scene coordinates must use metres for the 1 mm count. No inputs select regions automatically; authorize only neutral regions.

* Sections JSON: `{"sections":[{"bone":"Joint","axis":[0,0,1],"interval":[0.4,0.6]}]}`. Axis and interval are world-space; the slice plane goes through the head. Closed, single connected, degree-two contours only; an open, ambiguous, or vertex-coincident slice is omitted. The length-weighted contour centroid is compared to the head. Contour membership and every plane within the interval are not checked.
* Chains JSON: `{"mirror_plane":{"normal":[1,0,0],"offset":0},"mirror_pairs":[["L","R"]],"strips":[{"axis":[0,0,1],"vertices":[0,1],"chain":["A","B"],"influence":"B","direction":1,"transitions":[[0.4,0.6]]}]}`. Coordinates are world-space; a strip must have unique projected coordinates and positive chain mass. The selected influence is divided by chain mass. Declare protected transitions explicitly.
* Poses JSON: `{"poses":[{"name":"bend","bones":{"Joint":[1,0,0,0]}}],"regions":{"leg":[0,1]},"head_bone":"Head","hair_roots":{"vertices":[0]}}`. Region entries are fixed loop-triangle indices. Poses may instead name an `action` and `frames` (including subframes). Names and frame values identify wildcard metrics, and baselines must be declared independently for each metric. Fixed triangles are compared using a 3D-to-2D tangent deformation gradient, singular values and area ratio. `details.strain_samples` records each region/frame, p99, maximum, p01, severe counts and excluded degenerate rest triangles. Topology-changing modifiers invalidate correspondence. Severe thresholds are diagnostics only: deep-knee compression persisted after the spike was fixed, so inspect p01, p99, counts and review views together.
* `loops` in poses JSON specifies objects such as `{"action":"Walk","start":1,"end":30,"bones":["Root","Head"],"root":"Root","displacement":[0,0,0]}`. Declared displacement is removed before root comparison. These are endpoint-only bone orientation and root position checks, not vertex or velocity seams.
* `--rest-reference` accepts `{"samples":[{"before_world_delta":[1,0,0,0],"after_world_delta":[1,0,0,0]}]}`. Quaternion comparison is sign-invariant. These are supplied observations, not independently extracted from the before/after blends; provenance and coverage of keys, midpoints and affected bones must be independently verified.
* Hair contact uses nearest surface and three-ray parity only when every body edge has exactly two incident triangles. A parity disagreement or open body makes the result indeterminate. Counts aggregate the worst rest or supplied pose sample; signed penetration depth, crossings, local exception zones and continuous-time collision are not measured. `scalp_paint_mask` in the pose JSON can supply `texels`, each with world-space `origin`, `direction` and `max_distance`; the tool counts rays not hitting hair at rest. These rays must be constructed from an independently declared mask and registered scalp surface; they are not a texture-to-surface rasterizer or proof of silhouette quality. Inspect front, profile, rear and ears. Root drift is relative to the evaluated Head rigid transform, for explicitly declared root vertex indices.

Gate inputs require `declared.references`, `declared.baselines` and `declared.limits`, keyed by metric (including expanded region/pose suffix); this measurer does not manufacture them. Merge independent declarations into the evidence before gating. A scalp mask must be declared absent explicitly to mark it not applicable.

## Failure modes and limits

Weight-only correction cannot repair incorrect pivots. Inspect native weights, transforms, modifiers and pose before choosing a causal correction; compare each declared region and pose against its own baseline.

Rest rebasing must preserve represented world-delta rotations, not copy local quaternion components across different rest frames. Sign-only quaternion repair preserves rotations.

Hair exceptions and root tolerances are explicitly approved caller baselines, not a universal penetration allowance. Face-rigid and loop checks likewise use the selected reference; generic advisory loop diagnostics do not certify visual quality.

Preserve rest triangle indices when measuring deformation: native tessellation may change under pose even when polygon topology is unchanged. No historical subject strain, clearance or sample-count receipt is shipped.

## Explicitly unmeasured

Continuous-time collision, segment/triangle intersections, gait/stance velocity, complete parent-edge manifest, exact bind-pose label, silhouette fidelity, pose seam vertex/velocity continuity, and automatic extraction/coverage validation of before/after rest rebasing are unmeasured. Open-body inside tests are indeterminate. Geometric manifold edge counts alone do not establish absence of self-intersection. Visual review is required and has no automatic check.
