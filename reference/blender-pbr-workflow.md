# Blender PBR workflow for reference-matched characters

Use with `blender-character-route.md`, `blender-geometry-workflow.md`, `blender-source-assets.md` and `blender-export-parity.md`. Authoring guidance for a human or agent in Blender: no automatic texture transfer,
no automatic likeness, and no claim that a GLB reproduces a Cycles look.

## Scope and stage order

Geometry must already pass `blender-geometry-workflow.md`: **a texture cannot repair a wrong silhouette, fused eyelids, a mitten hand or coarse topology.** Then UVs → material setup → bake → inspect → export, in
that order. The material stage must not silently mutate frozen geometry: when a defect is genuinely geometric, return to the geometry stage, re-freeze, and re-run every downstream check (UVs, weights, masks, export
hashes) rather than repainting over it. When the cause is in the UV or the map, fix it there.

Skin and garments are separate surfaces with separate materials, maps and acceptance criteria: never drive skin from a fabric map, never tile cloth over a face. Hair, eyes, teeth, nails and accessories are their own
materials; eyes are not skin. Give each garment its own object and material, so weave scale, roughness and colour differ per garment and the soft-body region config can name them (`softbody-character-route.md`).

## UV texel allocation and pixel footprint

Allocate texels by **pixel footprint at the declared viewing distances**, not polygon count or one arbitrary 4K atlas.
Measure screen pixels per millimetre of surface; choose an explicit texels-per-screen-pixel target to derive required texel density.
Prioritize face and hands at their actual close-up distance; budget separate 0–1 atlas/map sets per material object as described below.
Record atlas dimensions, surface coverage, density and memory cost rather than assuming every region needs equal density or unlimited tiles.

Unwrap with intent — mark real seams (shoulder, side, crotch, sleeve, waistband, collar, hair part), keep weave direction continuous — then pack with a mipmap-safe margin (`bpy.ops.uv.pack_islands`, `margin_method`,
`margin`). **No implicit UDIM or multi-tile support in glTF:** deliver separately budgeted 0–1 atlases or material objects instead, or re-bake tiles into supported outputs before export. A configured object still
ships as one primitive.

## Transferring skin onto arbitrary UVs

A skin texture authored for a different head cannot be swapped onto your UVs: its features (eye position, brow, nose, mouth, ear, neck seam) live at UV coordinates your mesh does not have. Transfer needs
**landmark-aware correspondence**, and the Data Transfer modifier's nearest-surface UV mapping is **not** landmark solving — it copies UVs from the nearest source surface point, placing skin features wherever the
geometry happens to put them. First align or admit a source whose landmarks correspond to the destination's (an admitted, aligned source head, or an explicitly authored landmark correspondence), then transfer.

Keep the two UV roles explicit and separately named: the **source lookup UV** that reads the source skin, and the **destination bake UV** that receives it. For selected-source → active-target raw-colour transfer,
route source RGB through temporary Emission (strength 1), bake `type='EMIT'` into a fresh `sRGB` image, then restore the accepted material. Keep source lookup coordinates distinct from destination bake coordinates.

There is no one-click "apply any skin to any head" and no plugin command that does it: without a plausible shared head proportion the result yields a distorted face, so report that instead of shipping it. Garments
transfer more simply — tile in the garment's own UV space — because cloth has no facial landmarks.

## Seams, bleed and mirrored asymmetry

**Seam padding:** every island needs a margin wide enough that mip filtering at close range cannot pull the neighbouring island's colour across the seam; check at the real close-up distance, not at full-body
framing. **Visible bleed:** inspect seams in a close-up render for colour fringes — bleed means the margin is too small or the islands were packed with overlapping padding. **Mirrored asymmetry:** skin is not
symmetric. After a Mirror modifier or mirrored unwrap, the two face halves must not share one mirrored region when the source skin carries asymmetric marks (freckles, moles, scarring, uneven pigmentation, a
one-sided birthmark). Duplicate and offset the region instead of mirroring it, and verify by rendering both sides rather than reading the UV editor. Also check the neck/body seam and hairline for a visible colour
break.

## Preserving identity

The **reference** determines identity, tone and marks. Use the source skin for compatible surface detail, and record any deliberate colour-matching you perform; do not overwrite the reference's identity with the
source person's own marks. Keep the reference's identity features — eye shape and spacing, iris colour and size, brow shape, nose shape, mouth shape, lip fullness, jaw and chin, distinguishing marks — and their
placement. A texture pass may not move them; exclude or mask a map that would. Colour-match admitted surface detail to the reference,
record the deliberate edits, and retain the source creator and licence on the derived map (`blender-source-assets.md`).

**A source skin is not automatically better:** a scan-sourced skin can be more detailed and still less matched to this face, or worse in colour and ageing. Only a rendered A/B comparison under a fixed camera and
light decides which source to keep. If the user supplies their own licensed mesh or skin, keep its identity and licence; do not "improve" it with a generic skin.

## Albedo rules

**De-lit albedo.** Base colour carries no scene lights, shadows, specular highlights, baked ambient occlusion or direct/indirect lighting. For raw Base Color, bake its RGB through temporary Emission, not its diffuse lobe.
`type='DIFFUSE'` with `pass_filter={'COLOR'}` removes lighting but can still attenuate colour through the material's diffuse-lobe energy model; it is not necessarily raw Principled Base Color.
Preserve any needed alpha separately. Emission does not remove shading already painted into a source skin: de-light that source independently and retain the original for reference.

**Gentle geometric-derived skin detail, not fabricated pore noise:** derive micro detail from the actual surface (bake a normal from the geometry, or use a real displacement/micro-scan source) and keep it subtle. Do
not generate random pore or speckle noise, do not use noise to disguise a lumpy control mesh, and do not bake detail the runtime cannot show at the target distance.

## Skin and cloth material response

- **Skin: metallic 0.** It is a dielectric — author `Metallic` as 0.0 (or an image whose blue channel is 0) and keep metallic maps out of the skin material.
- **Skin: varied but bounded roughness.** Not one constant, not a mirror: author a bounded range (forehead/nose/cheek rougher than lips and some oily zones). A plausible starting range is roughly 0.3–0.8, but that
  is a starting hypothesis for this character, not a universal skin acceptance threshold — verify by reading the baked map's histogram and by the rendered A/B. Protect **lips and eyelids**: lips are glossier but
  never mirror-like, eyelids are thin and catch highlights; do not let a cheek roughness or normal map bleed across them.
- **Cloth: weave scale and direction** must match the garment's real-world size. Use the vendor's tile metadata plus the actual observed thread count: a 500 mm tile does **not** establish 0.5 mm yarn spacing, and a
  20 cm tile can be correct for a torso that repeats it several times. Keep weave direction consistent along the warp/weft axes; rotate the UVs, not the texture, when the pattern must run vertically on a sleeve.
- **Cloth: separate material response.** Cloth is generally rougher than skin, with sheen at grazing angles rather than gloss and a subtle specular response. **One material response per garment**: never reuse the
  skin material for cloth, and never reuse one garment's maps for another with a different weave scale.

## Blender node setup for glTF

- Build materials from **Principled BSDF** nodes, using the inputs the glTF exporter recognises (Base Color, Metallic, Roughness, Normal, plus the `glTF Material Output` group's `Occlusion` input for an AO map).
- **Colour spaces:** decode each source correctly — an EXR colour map may be scene-linear, a PNG colour map is usually sRGB, and data maps are linear. On output, glTF expects base-colour and emissive RGB in sRGB and
  data maps (normal, roughness, metallic, occlusion) in linear. Set the Image Texture node's *Color Space* (or the image's *Color Space* in Image Settings); a normal map read as sRGB is a wrong normal map even when
  the numbers look plausible.
- **Normals:** tangent space, **OpenGL (+Y)** — glTF defines +X right, +Y up, +Z toward the viewer. If the source is DirectX (+Y down), flip the green channel deliberately; do not rely on the exporter to guess. Keep
  the Normal Map node in its default Tangent Space mode, and follow the loader convention in `blender-export-parity.md` before flipping anything at runtime.
- **Packing:** use occlusion **R**, roughness **G**, metallic **B**, with a recognized channel-separation graph and linear packed data.
  Inspect exported channel values, UVs and sampler settings; recognized packing does not guarantee byte-identical image files.
- **AO:** bake AO once, into the occlusion slot or a standalone AO map. Do not multiply AO into base colour *and* also ship an occlusion map: that darkens twice. AO-in-albedo is a legacy approximation, not the
  preferred workflow.
- **Displacement** may author geometry before freeze. Bake microdetail to a supported normal map for the stock GLB path;
  a Blender displacement node does not become live browser deformation. The configured soft-body surface field is a separate system.

## What does not survive the GLB handoff

glTF/Three.js do **not** automatically carry Blender subsurface scattering, procedural nodes, cloth simulation, soft-body modifiers, IK constraints or hair/groom systems. Bake the supported image maps, retain the
editable sources and the material recipe with the job, and document the web approximation; do not promise a Cycles look in WebGL.

Optional `KHR_materials_*` extensions (sheen, clearcoat, transmission, anisotropy, specular, IOR, volume) exist and Blender can export some of them — use `blender-export-parity.md` for the pinned support actually
verified, then inspect the exported extension fields and the loaded material in the browser. Exporter support alone proves neither parity nor device cost, and do not claim the runtime always downgrades incoming
materials to `MeshStandardMaterial`. Do not invent custom SSS or other runtime shader APIs.

## One material primitive per configured object, and the freeze order

Each object the soft-body runtime configures needs single-user mesh data and exactly **one material slot in use**, i.e. one glTF primitive. Multi-primitive objects are rejected because `GLTFLoader` splits them into
separate meshes and the region masks would no longer resolve. If a garment, hair or accessory needs its own material, make it its own authored object rather than a second slot on one object. Preserve rig, morphs and
vertex order when splitting (`softbody-character-route.md`), then verify unique names, unchanged skin joint order and intact morph targets.

Order: 1. geometry, topology and transforms frozen and accepted. 2. UVs unwrapped, packed, padded and inspected. 3. Materials authored, colour spaces assigned, maps baked. 4. **Only then** skin weights, morphs,
soft-body masks and vertex groups. 5. Export. After the freeze there is no geometry or topology mutation: reopening the mesh invalidates the UVs, weights, masks and export hashes, so re-validate instead of
re-freezing quietly.

## bpy bake and export, at instruction level

Use a Python containing bpy (see `blender-character-route.md` for the runtime and `B`/`P` conventions) and check the installed version's API before authoring; the snippet below uses the Blender 4.5 API as published.

**Bake** — Cycles Render ▸ Bake or `bpy.ops.object.bake(...)`: raw Base Color uses `type='EMIT'` from the temporary RGB→Emission graph above; restore the accepted material afterward. Never use `COMBINED` for albedo.
During baking, use an `sRGB` colour destination and `Non-Color` normal/data destinations; verify saved pixels against a known linear→sRGB calibration. Re-tagging existing bytes alone is not colour conversion.
For high-to-low transfer, use `use_selected_to_active=True` with fitted `cage_extrusion`/`cage_object`, `use_cage` and `max_ray_distance` as applicable. A self-bake without authored shader/high-poly detail can legitimately be neutral +Z, even on curved meshes; it cannot invent pores or folds.
For normals use `type='NORMAL'`, `normal_space='TANGENT'`, swizzle `R=POS_X, G=POS_Y, B=POS_Z`; use `target='IMAGE_TEXTURES'`, `save_mode='INTERNAL'` and seam padding via `margin`/`margin_type`.
The material needs an active Image Texture node with a fresh destination image; use `use_clear=True` so stale pixels cannot survive. Inspect saved maps and normal-on/off renders under raking light.

```python
# Bake authored normal detail; matching undetailed source/target can yield a valid neutral +Z map.
bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT',
                    normal_r='POS_X', normal_g='POS_Y', normal_b='POS_Z',
                    margin=16, use_clear=True)
```

**Export** — `prepare_softbody.py` performs the final GLB export from the authored `.blend`; there is no mandatory duplicate manual export followed by a re-export. If you export by hand for inspection, use
`bpy.ops.export_scene.gltf(...)` with `export_format='GLB'`, `export_materials='EXPORT'`, `export_image_format='AUTO'` (may retain compatible JPEG/PNG; packing or alpha can change encoding—inspect actual output). PNG metadata alone does not define a glTF texture's colour/data role.
`export_texcoords=True`, `export_normals=True`, `export_tangents=True` when a normal map is present, `export_morph=True` for facial shapes, `export_skins=True`, and `export_apply=False` (applying modifiers
prevents shape-key export; see `blender-export-parity.md`). Export from a copy of the master, never over it.

## Appearance acceptance renders

Render and compare, under one fixed camera and one fixed light setup, in the real browser. Four passes, each isolating one thing:
- **albedo-only** — unlit/emission-only base colour, so nothing but the colour map is visible (not "no roughness variation" under scene lights).
- **normal-off** — lit, with the normal map disconnected.
- **clay** — uniform grey, no maps.
- **PBR beauty** — the shipped look.

Capture face close-ups (front/quarter), garment-scale views at declared viewing distances, and full front/side/rear under a locked render contract.
Compare the estimated reference view and record unknown source lighting. Track which passes retain each defect to localize causes, not to prove a sole cause from one pass.
Record capture files, light rig, viewport and browser errors. Missing evidence is blocked, not passed.

## Tool references

- [Cycles baking](https://docs.blender.org/manual/en/4.5/render/cycles/baking.html) · [glTF export](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html) ·
  [Image Texture](https://docs.blender.org/manual/en/4.5/render/shader_nodes/textures/image.html) · [Image Settings](https://docs.blender.org/manual/en/4.5/editors/image/image_settings.html) ·
  [Principled BSDF](https://docs.blender.org/manual/en/4.5/render/shader_nodes/shader/principled.html) · [Data Transfer](https://docs.blender.org/manual/en/4.5/modeling/modifiers/modify/data_transfer.html) ·
  [glTF materials spec](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) · [three.js MeshStandardMaterial](https://threejs.org/docs/pages/MeshStandardMaterial.html)
