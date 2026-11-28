# Skin atlas authoring

Use `tools/atlas_surface.py` with caller-owned bottom-up pixel arrays after geometry and UV cuts are established. This preserves a generic atlas-layout algorithm, not subject measurements or appearance.

The body must be opaque uint8, width W and height W/2, W divisible by eight. `composite_atlas` copies body bytes exactly. Two donor squares of side W/2 occupy the next band; half-sized squares use the documented texel-centre 2x resampling rule. The final W/8 rows are reserved for an independently baked bridge. Composite size is W by 9W/8.

Remap body `(u,4v/9)`, face `(u/2,4/9+4v/9)` and neck `(u/2+1/2,4/9+4v/9)`. These ratios follow the tile geometry; they are not reconstructed anatomical ratios. Supply project-approved sizes instead of treating a former output resolution as a standard.

For each ring, sample at angles `2π(i+.5)/W`. `neck_strip` accepts owner-edge UVs and source atlases or pre-sampled colors. Decode sRGB, interpolate in linear light with bounded smoothstep, re-encode and quantize. The layout's resolution-scaled padding is an algorithmic format policy, not a measured body property; validate its endpoints at the selected resolutions. Padding must leave a positive blend interval.

`color_line_repair` takes explicit shadow/target colors, normalized spatial box, residual gate and feather widths. It cannot infer pigment ownership or lighting. Pixels outside support must remain byte-identical; `assert_zero_change_outside_mask` checks that boundary. Do not use a global recolor to conceal geometry problems.

No texture images, donor placement, subject palette, measured repair counts or native evidence are bundled. These functions do not cut geometry or weld the join; inspect real correspondence, filtering, shading and source permissions separately. See `../NOTICE`.
