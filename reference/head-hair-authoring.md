# Caller-calibrated head/neck and hair authoring

The pure NumPy tools operate on admitted caller geometry and explicit measurements. They do not establish likeness, source rights, renderer quality or native acceptance. No donor landmarks, head/hair placement, measured matrices or subject chain presets are shipped.

## Placement and topology

1. Supply donor maximum Z, positive scale, target crown and Y translation to `fit_similarity`. The transform's vertical translation is `crown_z-scale*max_z`; apply it to every selected part in the same world frame.
2. `clip_polygon_plane` interpolates each supplied corner attribute at the caller's cut plane. Normalize/prune downstream as needed. `boundary_rings` temporarily welds for analysis, not a source mesh edit.
3. `bridge_rings` angle-merges ordered star-shaped rings and reports strip incidence/angular mismatch/centre offset. Its assumed adjoining boundary incidence does not prove the actual adjacent meshes are welded or globally watertight. Verify correspondence independently.
4. `cheek_masks` retains explicit eligibility and landmark-based ellipsoid mathematics but requires keyword `calibration`: `center_x_over_eye`, `center_z_offset_over_span`, `radii_over_landmarks` (three positive factors), `medial_x_over_eye`, `iris_clearance`. No source-derived landmark ratios are defaults. The caller owns the measurements and eligibility. Both sides need at least eight active vertices; ambiguous/empty selections fail closed.

## Hair binding

This is separate from `rig_geodesic_skinning.py`, not a replacement for its policy. Weld seams for analysis, remap edges, classify explicitly eligible below-pin connected components and provide selected chain centre lines. Dominant-component classification assumes an unambiguous rear curtain and sided front components; it is not semantic segmentation.

Supply descending band centres, per-chain heights, positive width profile, explicit pin/blend and face-chain heights to `hair_weights`. Quintic interpolation shares head/chain influence. Weights below 1e-4 are removed and the remainder normalized; more than four influences is refused. Map rows through the seam inverse. `validate_binding` checks normalization, influence count, seam equality and root pinning. Root positions, chain counts and artistic profiles are input-specific, never borrowed defaults.

## Motion and preservation

Sample actual head transforms into world-space rest targets before `simulate_chain`. Fixed-root damped springs use stable semi-implicit substeps and project segment lengths to rest. Caller frequency, damping, strength and timestep must satisfy the stability check. `shape_quaternion` takes a caller-computed local `[w,x,y,z]` quaternion and explicit amplitude/cap in radians. The caller derives local rotations and writes keys; `assert_non_hair_channels_unchanged` compares full channel maps outside the declared hair set.

There is no continuous collision solver or automatic fit decision. Local manifold counts and sampled clearance do not prove global collision, source surface correspondence, donor fidelity or complete exported animation parity. Inspect real geometry/materials/motion and retain actual failures. See `skin-body-standards.md` and `../NOTICE`.
