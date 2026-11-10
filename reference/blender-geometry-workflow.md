# Reference-driven native Blender geometry

Use with `blender-character-route.md`. Construct an editable, continuous character rather than
requesting an image-to-mesh service. Match the reference before spending effort on micro-detail.

## Analyze before building

- Read face and body crops at native resolution. Mark pupil/eye corners, brow, nose base, mouth
  corners, chin/jaw, ear roots, shoulder/elbow/wrist, pelvis/knee/ankle and garment boundaries.
- Record image-space measurements and confidence. Do not invent depth, hidden fingers or back seams.
  Landmark detectors supply evidence, not anatomical approval; retain their model/version provenance.
- Separate identity-defining shape, expression, lighting, pigmentation, makeup and textile pattern.
  A shadow under a cheek is not automatically a geometric indentation or a permanent skin marking.
- Record perspective/orthographic uncertainty. Fit camera and pose before changing head proportions
  to compensate for perspective. Lock viewport, lens, target and scale for before/after captures.
- Choose a declared unit convention: Blender Z-up; exported glTF right-handed Y-up in meters.
  Record figure height `H`, whether measured or assumed, forward axis and anatomical left/right.
- Inventory semantic components: connected head/body, eyes, teeth if visible, hair, each garment,
  footwear and accessories. Record which surfaces need their own materials, rig and interactions.

## Choose an honest construction method

- Prefer an authored low-resolution control cage, cross-section/loft surfaces, BMesh topology,
  sculpt plus retopology, or a legally admitted editable human base fitted to measured landmarks.
- Use MakeHuman/MPFB or another asset only after the source/rights check in `blender-source-assets.md`.
  Preserve source meshes and attribution/provenance even if the license does not require credit.
- Describe imported anatomy as adapted source assets, not original reconstruction. Do not quietly
  import Tripo/CharacterGen output, paid scans or a different person's face to satisfy the silhouette.
- Use spheres/cubes/capsules for temporary blockout only. Join/retopologize into anatomical surfaces
  before accepting skin; detached nose/cheek lumps and fused painted eyes fail the face stage.
- Do not promise fully automatic photorealism. If the reference lacks enough face pixels for the
  requested viewing distance, request a usable close-up or record the bounded approximation.

## Shape in macro → meso → micro order

1. **Macro:** match height ratios, torso/pelvis width, limb lengths, head mass and pose. Compare the
   fixed silhouette and at least a side/quarter view; hidden-side decisions remain inferred.
2. **Head:** construct one coherent skull/jaw/face surface. Fit brow ridge, orbital depth, cheek,
   nose bridge/alar volume, mouth opening/lip contour and chin; do not smooth away facial landmarks.
3. **Eyes:** fit real eyeballs in sockets and continuous eyelids with clearance. Keep iris/pupil
   placement stable in neutral and claimed expressions; a painted eye does not prove an eye rig.
4. **Body/hands:** connect shoulder/hip transitions and build deformable joint loops. Separate fingers
   when visible or interactive; do not hide mitten topology in a texture or camera crop.
5. **Garments:** model garment thickness/openings, major folds and seam placement as needed by the
   viewing distance. Fit over the body with clearance for specified pose/size extremes. Cloth weave
   belongs in the material; silhouettes and large folds belong in geometry.
6. **Hair:** follow scalp/root layout and directional masses with front/side/rear coverage. Use
   admitted alpha cards or authored strands/clumps where supported; never a frontal-only shell
   claimed as complete hair. Mark the exact follower region; no automatic collision claim.
7. **Micro:** bake real surface detail into normal/roughness after the form passes. Do not use random
   displacement/noise, high gloss or pore texture to disguise a lumpy control mesh.

## Refine without destroying correspondence

- Inspect actual vertex spacing and triangle area, not just polygon count. Increase density where
  face silhouettes, eyelids/lips, fingertips and soft contact footprints need it; distribute it smoothly.
- Use Catmull–Clark/support loops/creases deliberately; inspect shrinkage and preserve openings.
  Smooth shading changes normals, not silhouette. More subdivision cannot repair wrong anatomy.
- Apply Mirror, remesh, destructive subdivision and fitting before final UV/skin/mask authoring.
  Retopologize sculpts with deformation-aware loops; automatic remeshing alone is not pose acceptance.
- Resolve accidental duplicates, internal faces, zero-area triangles, flipped normals, nonmanifold
  seams and unrelated overlaps. Preserve intentional material/UV/hard-edge splits with recorded intent.
- Avoid indiscriminate merge-by-distance: nearby lips, eyelids, fingers, hair and clothes may be
  intentionally separate. Keep anatomical asymmetry and reference-specific marks after symmetry work.
- Check body/garment/hair clearance in neutral and planned stress poses. Separate objects can still
  intersect; object names and Blender collision settings are not proof of web collision support.
- Freeze accepted topology and transforms before binding and masks. Reopening geometry requires
  revalidating dependent UVs, skin weights, morphs, contact masks and export hashes, not bypassing parity.

## Keep authoring reproducible

Write reference-specific native bpy scripts in the job; keep parameters and measured landmarks
separate from mesh operations. Save intermediate `.blend` checkpoints and a final editable master.
Use explicit objects/collections instead of accidental active selection, record the Blender version,
and avoid view-context-only operators in unattended scripts unless a valid context is provided.
Use BMesh/data APIs where practical. Load external `.blend` data with auto-execution disabled;
never execute downloaded Python or embedded handlers as an asset import shortcut.

Assign independent parts to separate files/collections using agreed units, origin, anchors, names
and seam boundaries. Keep one owner for assembled geometry and all edits to the main `.blend`.
Append component data through a reviewed integration script; do not concatenate competing scene
scripts that reset each other's scene. Integrate and inspect adjoining surfaces before freezing.

## Geometry acceptance before materials/rig

- Save clay, wireframe, silhouette and face-close-up renders. Compare the matching view with the
  reference; inspect quarter/profile/rear for real volume and attachment, not inferred likeness.
- Measure projected landmark/silhouette error against the job's declared tolerances. Record the
  actual values and uncertain landmarks; do not fabricate a universal likeness score or a pass.
- Inspect face/skin under raking light for geometric faceting, quantization, pinches and waviness.
  Compare normal-map-off and albedo-only views before attributing every defect to texture.
- Verify finite geometry, expected bounds/orientation, outward normals, intentional openings and
  connected deforming patches. Inspect joint bending on the control cage before final rig approval.
- Reopen the saved `.blend`, regenerate from the build script and compare named components/bounds
  and reference captures. A successful file save or a geometric diagnostic fixture is not a character.
- Advance only after geometry passes; then use `blender-pbr-workflow.md` and
  `blender-rig-interaction.md`. If a shape fails, return to its measured cause instead of repainting it.

## Tool references

- [Retopology](https://docs.blender.org/manual/en/4.5/modeling/meshes/retopology.html)
- [Modifier evaluation order](https://docs.blender.org/manual/en/4.5/modeling/modifiers/introduction.html)
- [Blender Python API](https://docs.blender.org/api/4.5/)
