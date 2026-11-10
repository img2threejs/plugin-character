# Blender → glTF → Three.js parity

Read before exporting the frozen native character. Validate the installed exporter and browser
versions; the limits below are evidenced for Blender 4.5 and Three.js 0.186.1. A beautiful Cycles
render is not evidence that the delivered GLB has the same deformation or shading.

## Freeze and record the actual representation

- Retain the editable master and export from a separate working copy. Record source/export hashes,
  transforms, mesh/primitive counts, UV layers, joints, morph targets, clips and material extensions.
- Apply destructive geometry operations before final UV/weights/masks. Do not enable `export_apply`
  as a universal bake: Blender warns that Apply Modifiers prevents shape-key export and excludes
  Armatures. Inspect the actual exported targets; do not infer preservation from Blender's UI.
- Retain the existing `prepare_softbody.py` contract. This document adds checks, not a replacement
  exporter, a new CLI flag or permission to change the source master.

## Skeletal and animation parity

- Record Armature `use_deform_preserve_volume`. Blender's Preserve Volume uses quaternion
  deformation; stock glTF/Three.js skinning blends weighted bone matrices. The same bone rotations
  therefore do not establish the same surface. Do not call sampling a conversion of that algorithm.
- Compare the same exported shoulder/forearm/hip bend and twist poses against Blender, especially
  joint volume and silhouette. Prefer a verified linear-skinning authoring baseline when targeting
  the stock browser; require separate evidence for any custom deformation implementation.
- Sample supported IK/constraint results into joint/object animation when required, then play the
  exported clips and check endpoints. Check driver-driven expressions separately. Export settings
  and a Blender action name do not establish a playable clip or correct evaluated deformation.
- Do not confuse “not live” with “automatically baked.” Blender cloth/soft-body caches are not
  automatically converted into glTF morph animation. Require a supported, exercised representation
  for any retained simulation; otherwise report the missing motion. No live collision is implied.

## Skin and textile shading parity

- Keep Cycles skin appearance and browser approximation as separate acceptance surfaces.
  Principled Random Walk/Skin SSS does not transfer through this stock exporter/loader path.
  `KHR_materials_volume` models thickness/absorption and needs a separate transmission extension;
  it does not model skin scattering. Thickness maps, baked albedo and a volume-extension name
  are not proof of live SSS. Inspect ears/face backlighting.
- Bake supported color, normal and roughness channels into final UVs rather than shipping an
  unevaluated procedural graph. A Combined bake includes lighting; it is not lighting-free albedo.
- Do not overstate the limitation: supported sheen/anisotropy extensions can carry cloth properties.
  Inspect actual exported extension fields and loaded browser parameters, then compare appearance;
  exporter support alone does not prove parity or device cost.
- Treat base-color/emissive RGB as sRGB and normal/roughness/metallic/occlusion as linear data.
  Use tangent-space +Y normals. Convert a documented DirectX −Y input deliberately, not by guess.
  GLTFLoader already applies glTF texture conventions, including `flipY=false`; do not blindly flip
  the green channel or `normalScale.y` again when replacing a loaded texture.

## Facial keys, normals and UV seams

- Inspect exported morph POSITION/NORMAL deltas and loaded `geometry.morphAttributes`. glTF morph
  deltas are relative; missing normal deltas do not mean “recompute normals automatically.”
- Prefer a consistent normal representation across facial targets and inspect mixed omissions.
  Three 0.186.1's loader substitutes base normals for an omitted NORMAL when another target has it;
  do not assume that mixed case is a zero-delta fallback or patch the dependency without a repro.
- Do not promise morph-correct tangent shading merely by enabling `export_morph_tangent`: this
  pinned loader handles morph position/normal/color, not morph tangent attributes.
- Record whether tangents are exported or the renderer derives its frame. Three's derivative frame
  is not an automatic MikkTSpace preprocessing pass. Match bake/tangent conventions and UVs.
- Preserve deliberate UV/hard-edge splits. Coincident positions and unit normals alone do not prove
  normal-mapped skin is seamless. Use padding appropriate to the real atlas resolution/mip levels.
- Capture neutral, claimed expressions, joint extremes and expression + pose + contact combinations.
  Compare raking-light views with normal maps on/off and at mipmapped distances. Check positional,
  normal and visible shading continuity without welding distinct lips, fingers or garment layers.

## Evidence and limits

Save Blender/browser paired captures with matched pose, camera and lights; GLB inspection; loaded
material/morph inspection; source hashes; and unambiguous failure notes. A two-bone diagnostic can
prove export wiring and interaction, not a production skeleton, facial quality or reference likeness.
Do not claim arbitrary material graphs, volume conservation, collision or a measured frame budget
from these checks. Follow the actual rig/contact gates in `blender-rig-interaction.md` separately.

## Primary references

- [Blender Armature / Preserve Volume](https://docs.blender.org/manual/en/4.5/modeling/modifiers/deform/armature.html)
- [Blender glTF mesh, material and animation export](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html)
- [Blender export operator / apply and morph options](https://docs.blender.org/api/4.5/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf)
- [glTF skin, morph and texture semantics](https://github.com/KhronosGroup/glTF/blob/main/specification/2.0/Specification.adoc)
- [Volume excludes scattering](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_materials_volume/README.md)
- [Pinned Three.js loader](https://unpkg.com/three@0.186.1/examples/jsm/loaders/GLTFLoader.js)
- [Pinned linear skinning shader](https://unpkg.com/three@0.186.1/src/renderers/shaders/ShaderChunk/skinning_vertex.glsl.js)
- [Pinned normal-map tangent frame](https://unpkg.com/three@0.186.1/src/renderers/shaders/ShaderChunk/normalmap_pars_fragment.glsl.js)
