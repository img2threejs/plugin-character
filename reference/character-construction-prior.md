# Learn construction from an existing character

Use for analysing an admitted model and carrying its construction lessons into the next character.
This is analysis feeding the existing authoring route, not an image-to-avatar generator or a new profile.
No measured prior is bundled. The skill ships only the extractor `tools/extract_construction_prior.py`; generate
a prior from your own rigged or static GLB that you have the right to analyse, and keep it with the job.
Load its JSON only for the sections needed.
Before transferring to a new identity, use `character-transfer-exercise.md` for parameterized authoring,
fixed-view correction loops, target-specific paint and evidence of what actually transfers.

## 1. Extract facts before choosing a recipe

Record the source's author, URL, licence and permitted reuse. Analyse a local GLB read-only:

```bash
# Run from the installed character plugin; choose the real skin mesh/node, not the clothing.
python3 tools/extract_construction_prior.py --glb /path/character.glb \
  --body-mesh Body --out /path/job/construction-prior.json
```

Use Python 3.10+ stdlib; no Blender, network service or account is required for extraction.
The output includes the GLB SHA-256, normalized dimensions, inventory, anatomy, construction and limits.
Exit 0 means extraction succeeded, NOT visual acceptance. Exit 1 is an analysis error; 2 is invalid
input/options or a missing module. `--out` cannot alias the input. Explicit `--skip anatomy` or
`--skip construction` records null sections and `skipped`; never treat missing facts as zero or passed.

Inspect these sections instead of reading the entire prior into context:

| Question | JSON path |
|---|---|
| Parts, materials, images, joints, masks, actual budgets | `inventory.observed` |
| Body selection, semantic roles, axes | `inventory.inferred` |
| Height-band silhouette, depth and arm separation | `anatomy.silhouette` |
| Conditional head dimensions, separate face-detail bounds | `anatomy.head`, `anatomy.face.features` |
| Eye layout, nose candidate, face proportions | `anatomy.face.layout`, `anatomy.face.noseTip` |
| Landmark method/confidence, pose, segment ratios | `anatomy.inferred` |
| Face/body UV allocation, authored colour samples | `anatomy.atlas` |
| Vertex/triangle spacing, symmetry, UV overlap, weights, hair components | `construction.observed` |
| Stored-pose garment offsets and sampling coverage | `construction.observed.garmentClearance` |
| Construction hypotheses, NEVER recovered modifier history | `construction.inferred` |

For example, use `json.load(...)['anatomy']['face']['layout']` to read only the face layout.
Check each module's `limits` and body selection; their heuristics can disagree. Re-run with an
explicit body override after inspecting the real mesh. Inventory budgets count each mesh once;
construction counts node instances. Anatomy currently selects one primitive, not a merged body.

## 2. Separate evidence classes

- **Observed:** exported buffer/material/image values or measurements under a declared method.
- **Conditional measurements:** head/eye ratios depend on inferred chin/feature identity; preserve
  that dependency and confidence. Eye mesh bbox centres are not detected pupils or anatomical IPD.
- **Inferred:** part roles, landmarks, pose class, hair type and likely construction patterns.
- **Source-corroborated:** authoring script/modifier settings, backed by a hash and source location.
  GLB topology alone cannot establish the original cage, subdivision algorithm or edit history.
- **Unknown:** unsupported/occluded properties, absent mouth landmarks, unmeasured runtime results.
  Keep nulls and limitations. Do not turn an unobserved feature into a modelling prescription.

Confirm important roles against the actual mesh/atlas or renders. Keep screenshots and image crops
separate from numerical results; numeric extraction alone does not inspect appearance.
Stored bind-pose clearance samples are not animation collision proof or a watertight inside test:
sign follows the nearest skin normal. Open surfaces, bad normals and overlapping skin need inspection.

## 3. Apply the lesson to a NEW reference

Add a `constructionPrior` section to the job's existing `character-plan.json`, not a second plan:
source hash/path; adopted construction choices; target-measured overrides; inferred/unknown values;
and named acceptance criteria. Treat it as an authoring decision record, not an executable schema.

1. **Measure the target first.** Fit camera/pose; record image-space head height/width, eye corners,
   eye spacing, nose, mouth, jaw, body silhouette, hair masses and garment boundaries with confidence.
   Keep unknown depth separate. Follow `blender-geometry-workflow.md`, not a fixed template from a reference character.
2. **Borrow structure, replace identity parameters.** Reuse continuous skin plus separate eyes/details,
   region-specific density, intentional UV mirroring and separate garment/hair layers when appropriate.
   Replace head/body/eye/garment ratios with the new target's measurements. For an unobserved value,
   retain a labelled prior hypothesis; never present it as measured from the new image.
3. **Author the macro/meso surface.** Fit a low-resolution continuous control cage or an admitted base;
   establish skull/jaw/orbit/nose/lips and silhouette before refinement. Use measured ratios from a reference only
   as an explicit starting hypothesis for a compatible style, not as universal anatomy.
4. **Allocate detail where it reads.** Resolve eye/lid/jaw contours geometrically; allocate face UV
   area and localized geometry for the intended camera and contact footprint. More triangles alone
   do not create a better face. SIMPLE subdivision adds spacing, not smoothness or missing anatomy.
5. **Rebuild materials for the target.** Choose painted stylisation or de-lit PBR deliberately. Sample
   new colour regions, record baked shadows, and bake into the new UVs. Do not paste a reference character's atlas,
   its UV box, palette or roughness onto an unrelated character as a skin-matching method.
6. **Fit clothing and hair to this surface.** Re-derive clearance, thickness, root layout and anchors;
   never inherit source intersections. Use `garment-character-route.md` only for compatible connected
   garments. A jacket/skirt needs its own interaction design, not copied halter/cup classifications.
7. **Keep rig scope honest.** Reuse normalized weights and protected soft masks as principles;
   author actual limb/face/finger controls if required. Four control joints do not support a walk rig.
8. **Verify the new export.** Extract a second prior with the same declared axes/units/body selection.
   Compare target ratios, spacing, UV density and clearance. Then inspect fixed-camera clay/albedo/lit
   face/front/quarter/profile/rear renders and exercise the real interaction. Numeric deltas are not
   a likeness score; run the existing route's export/probe/gates separately.

## Scope and counter-examples

Extraction assumes Y-up, metre-scale, +Z-facing humanoids in a useful neutral pose. Bake transforms
and supply an inspected export when this is not true. Skinned geometry uses stored bind positions,
not evaluated joint deformation; static nodes use rest-world transforms. Non-cancelling inverse
binds, several skins, posed/bent bodies or extra high props require a source-side normalized export
before interpreting ratios. Unsupported PNG formats retain UV/header evidence, not invented colours.

Promotion: replace recollection with `extract_construction_prior.py` and preserve source hashes.
Regression cases include inside versus outside garments, non-uniform static scale, wrong weight
sums, mirrored/asymmetric bodies, missing face details, unsupported PNGs and source-output aliases.
Regular/alternating triangle grids must leave construction history unknown. Case: on a reference character, a 37.6%
exact-neighbour-midpoint share initially produced a false smoothing conclusion despite a source
`SIMPLE` modifier. Source corroboration takes precedence; the extractor now leaves it null.
