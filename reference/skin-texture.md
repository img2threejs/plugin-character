# Caller-calibrated painted skin texture

`tools/skin_texture.py` is a NumPy array pipeline. Inputs are top-down stored-sRGB RGB (uint8 or finite floats in [0,1]); Blender pixel buffers are bottom-up and must be converted explicitly. Painted base color is not measured reflectance. No subject palette, measured tone table or source texture is bundled.

- `rasterize_regions(positions, triangles, loop_uv, image_shape, predicates, origin, overlap_policy)` selects whole triangles using caller predicates, samples texel centres and reports shared/empty/degenerate/off-image coverage. Exclude ambiguous UV ownership; UV proximity is not 3D adjacency.
- `measure_tone(rgb, mask, statistic, color_space, luminance_gate)` requires nonempty finite samples. Encoded-sRGB and decoded linear-light gates select different pixels; name the intended mode. RGB luminance coefficients are color-science definitions, not an asset palette.
- `fill_skin_island(..., dilation, protected_mask)` requires an explicit padding count, uses selected-channel medians and bounded four-neighbour propagation, and preserves bytes outside support. Supply protected neighbouring islands.
- `lift_shadow(..., params)` requires all of `dark_luminance`, `dilation`, `blur_iterations`, `strength`, `darkness_gate`; no historical repair preset is used. The returned support includes feather/blur propagation. Selection and lighting interpretation remain the caller's responsibility.
- `repair_root_paint(..., recipe, iterations=...)` requires an explicit iteration count, boxes, saturation ranges and nearby clean samples. It performs bounded harmonic fill only inside spatial/pigment eligibility, never wrapping image edges. Warm-pigment eligibility is not semantic root detection.
- `repair_color_line` accepts explicit line colors, spatial box and feather/residual gates; chromaticity does not establish that pigment is a shadow.
- `recolor_details` requires caller boxes, eligibility and palette, including `background_distance`, `highlight_luminance`, `highlight_saturation`, `iris_curve` (offset, range, exponent) and `brow_gain` (three-channel vector). No hidden source feature thresholds remain. Protect highlights and authored details; a box does not establish ownership.
- `recolor_iris` requires explicit hue, pigment thresholds and optional UV coverage; it preserves nonselected texels. A full-map count is not a covered-UV count.
- `tone_match_report(..., deviation_limit=...)` uses the caller's explicit deviation limit, never a historical diagnostic.
- `build_composite` and `atlas_surface` implement a fixed geometric atlas format with exact body-byte copy and linear-light bridge; see `skin-atlas-authoring.md`.
- `save_pack_verify` saves/reloads actual PNG bytes and rejects stale packed bytes. `pack_blender_image` packs explicit verified bytes. Verify the final export independently.
- `skin_material_spec` requires explicit native scalars/maps; `validate_skin_material` independently compares exported maps/scalars and color spaces. Native scattering does not imply browser SSS or micro-detail.

Admit sources and permissions separately. Repairing a seam color cannot fix a geometric misalignment. No pores, de-lighting, anatomical fidelity, visual quality, continuous collision or legal approval follows from these tools. Deterministic tests use independently authored small arrays, not copied native receipts. Real S1–S11 acceptance needs caller-owned sources/catalogues/calibration and actual measurements.
