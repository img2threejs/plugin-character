# Nami construction study — measured example, not a universal template

Read `character-construction-prior.md` to apply this study to another reference.
Machine-readable measurements: `priors/nami-construction-prior.json` (schema
`img2.character-construction-prior/1`). Source GLB SHA-256:
`c9af5f2942c2d2d6120b38cc0c4ae0245894fdd8bc2fc0d6a4643805ee8afe55`.

## Provenance and measurement boundary

- Asset: [Nami one piece 3d model — fatymazali](https://sketchfab.com/3d-models/nami-one-piece-3d-model-b382d37e085444e69eb3cdd306243830),
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Adapted source, not an image-only reconstruction;
  no endorsement implied. Franchise rights are not established by the fan-art asset licence.
- Job: `nami-sketchfab-8e496e5a`; GLB: `native/export/character.glb`, 9,130,632 bytes.
- Normalized display height H=1.75 m; this is not a canonical/real character height.
  Y-up, +Z front, anatomical left +X. Geometric pose estimate: A-pose, arms ~33.3° from vertical.
- Extraction: `python3 tools/extract_construction_prior.py --glb <job>/native/export/character.glb
  --body-mesh Body --out reference/priors/nami-construction-prior.json` from the character plugin.
- Geometry/UV/colour measurements are static. No new appearance, likeness, animation or device-performance
  acceptance is implied. Head/body landmark heuristics use 100 height bands (~17.5 mm per band).
- Supporting authoring source: `native/prepare_character.py`, SHA-256
  `ff70bf980e582ef1734af2d7406d5269510e66e610bc88cff3dfcbb7774076fb`.
  Preparation record: `native/preparation-evidence.json`, SHA-256
  `0b3eb73b6953e859902745f4e09c3de5ce562d9fcc999cf1bf3d44f739c36933`.
  Source settings below were read, not newly re-executed in this analysis.

## 1. Overall construction and geometry budget

23 meshes, 96,367 exported vertices, 178,840 triangles, 3 materials, 3 textures referencing one
2048×1024 PNG. Body node `Body` uses mesh `Cube.020`: 37,771 vertices / 72,144 triangles.
Hair `NurbsPath.002`: 26,717 vertices / 49,312 triangles. Garments include separate `BikiniTop`
(`Vert.005`, 3,351 vertices / 6,192 triangles) and `Jeans` (`Cube.014`, 21,324 exported vertices).
Name/geometry-based role shares: body 40.3%, hair 27.6%, garments 26.3%, remainder props/details/feet.

**Lesson:** assemble a coherent skin surface with independent hair/garment/detail components;
spend density where silhouette, facial reading and contact need it, rather than subdividing everything.
The geometric head region has ~4.07× torso triangles/m²; mean edge length is 4.67 mm in the head,
9.88 mm torso, 4.55 mm arms and 17.85 mm legs. Region boundaries are heuristic, not bone regions.

Source script lines 93–115 apply two levels of Blender `SUBSURF` with `subdivision_type='SIMPLE'`
and `uv_smooth='NONE'` to body/top/jeans before rigging. The preparation record reports body
1,939→37,771 vertices, maximum source-surface deviation 3.29×10⁻⁷ m. This is increased contact
sampling density while preserving the existing form/UV interpolation, NOT facial sculpting.
Native and exported counts can differ at UV/normal splits (jeans: 21,322 native vs 21,324 exported).

The GLB alone has 83.3% valence-6 interior vertices but only 37.6% exact neighbour midpoints.
Neither statistic recovers modifier history or proves smoothing. The source establishes SIMPLE.
Also, 17.9% of body triangles have a minimum angle below 10°: do not adopt this as ideal topology.

## 2. Face and proportion parameters

These dimensions are conditional on the inferred chin and face-detail roles, not anatomical truth.
Head excludes hair; `headRel.y=0` at inferred chin and `1` at skin crown. Eyes use mesh bbox dimensions,
not pupil centres; “eye”/“brow” assignments are geometric hypotheses with medium confidence.

| Parameter | Measured value | JSON location under `anatomy` |
|---|---|---|
| Skin head W × H × D | 183.6 × 216.8 × 200.1 mm | `head.observed` |
| Head W/H; D/H | 0.8466; 0.9228 | `head.observed` |
| Figure height / skin head height | 8.071 | `inferred.proportions.headsTall` |
| Floor→crotch / H; crotch→shoulder / H | 0.530; 0.305 | `inferred.proportions.segmentsFracOfH` |
| Eye bbox width; width / head width | 40.24 mm; 0.2192 | `face.layout` |
| Eye bbox W/H | 2.4918 | `face.layout.eyeAspectWidthOverHeight` |
| Inner-eye gap / eye width | 1.0820 | `face.layout.innerGapOverEyeWidth` |
| Eye bbox-centre separation / head width | 0.4564 | `face.layout.interocularCentreOverHeadWidth` |
| Eye-line height above chin / skin head height | 0.4267 | `face.layout.eyeLineHeadFrac` |
| Nose-tip height above chin / skin head height | 0.2802 | `face.noseTip.headRel.y` |

Seven independent face-scale meshes occur in the head. Candidate roles include paired eyes
`Cube.021`, brows `Cube.023` and inner-eye/lid details. The skin mesh also contains embedded paired
islands; do not assume every eye component is a separate named object. Mouth landmarks remain null:
no separate mouth mesh was identified. Inspecting the actual face atlas shows a painted mouth line,
nose mark, brows and jaw/neck shading; this does not rule out shape in the underlying skin mesh.
Hairline-to-brow distance is unknown because the fringe reaches below the inferred brow line.

**Lesson:** fit skull/jaw and eye placement explicitly, then separate eye/lid/iris details where needed.
Borrow the parameterization, not Nami's identity. Measure the next reference's eye corners, mouth,
jaw and head dimensions; fit camera before adjusting ratios. Build missing lip/eyelid geometry if
close-up/expression requirements demand it. Neither this four-joint rig nor painted mouth detail
supplies a facial animation system.

## 3. Skin and atlas strategy

The same painted image supplies skin, hair, eye/detail and clothing regions. Embedded image SHA-256:
`6ff6107450a1e664422f014a6fa573e3b58c872cfee3f84d8c425ccfb179148f`.
The dominant front-face island occupies approximately UV `[0.8817,0.0197]–[0.9957,0.4824]`,
about 233×474 pixels in the original atlas. Bbox area is not actual occupied UV area.
Area-weighted face texel density is ~2,051 px/m versus ~558 px/m for body below the neck (3.68×).
The construction module uses different region definitions/statistics; do not mix their density ratios.
Body geometry is largely mirrored; ~98.7% of matched mirrored UV pairs share coordinates. This saves
atlas space but cannot encode independent left/right identity marks without a new UV plan.

Vertex-UV samples: face mean sRGB `#f5ccb1`, median `#fad7c0` (4,001 samples); body mean
`#f8d1b8`, median `#fad4bc` (28,732 samples). These are density-biased samples of authored paint,
including features/shadows, NOT measured skin reflectance or a palette for the next person.

Exported skin material: metallic 0, roughness 0.5, base-colour atlas, double-sided; no normal,
roughness or browser SSS texture/extension. Source lines 123–140 set native IOR 1.4 and SSS weight
0.08/scale 0.002 m, but those native scattering settings are not exported browser scattering.

**Lesson:** the result combines coherent form, deliberate face texture allocation and painted broad
shading, not procedural pores or a skin scan. For another stylised character, author a new palette,
painted features and UV atlas. For de-lit PBR, remove baked lighting deliberately and author supported
maps; compare albedo-only/normal-off/lit views. Never substitute this image into unrelated UVs.

## 4. Hair, clothing, rig and transferable decisions

Hair has 33 welded connected components, median component dimensions ~336×64×36 mm.
Geometry classification suggests thick tube-like clumps, not individual hair strands. Use directional
masses/root coverage as a modelling principle; design the target's hairstyle rather than copying 33.

All 3,351 top vertices were sampled: signed nearest-skin distance min 0.190 mm, median 3.409 mm,
p95 7.949 mm, 0 negative vertex samples. Jeans: 8,000/21,324 stride samples, median 8.424 mm,
167 negative samples (2.09%), minimum −13.785 mm. Inspect those intersections; do not canonize them
as a garment fitting recipe. These stored-pose vertex samples do not cover triangle interiors or pulls.
Use the separate garment browser probes/gates for dynamic claims.

Only four skin joints: Root, Pelvis, Spine, Head; body has at most two influences/vertex and normalized
weights. This is a small global control rig, not a limb/face/finger rig. Nine body `_SOFT_*` masks cover
paired chest/hips/waist/cheeks plus abdomen. Source masks use smooth ellipsoidal fields and normalize
overlap; facial protection excludes central/high cheek areas. Re-derive anchors/radii and inspect
protected eye/lip geometry on the next mesh, rather than copying world coordinates or mask counts.

Carry forward: continuous form before density; independent visual layers; facial parameter fitting;
face-prioritized UV space; deliberate painted/PBR choice; source-safe refinement; normalized
weights/protected masks; independent visual and interaction checks. Do not carry forward fixed face,
skin colour, atlas coordinates, garment intersections or the four-joint rig as universal defaults.
