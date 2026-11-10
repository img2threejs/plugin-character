# Blender-first reference character route

Route ID: `blender-character`. Choose for explicit Blender/bpy authoring, source-asset
character construction, or a reference-matched interactive character with no neural mesh generation.
This is an LLM/agent authoring workflow, not a harness `--profile` or a bundled photo-to-avatar CLI.
Do not call Tripo, CharacterGen, image-to-mesh services or substitute a previously generated mesh.
Keep `cc5-headshot` and code-only reconstruction separate; do not relabel their outputs as native work.

## Read by stage

1. Read `blender-geometry-workflow.md` for reference analysis and continuous surface construction.
2. Read `blender-source-assets.md`, then `blender-pbr-workflow.md` before acquiring or baking assets.
3. Read `blender-rig-interaction.md` before rigging or authoring soft regions.
4. Read `blender-agent-workflow.md` before assigning independent work.
5. Read `softbody-character-route.md` and `softbody-runtime.md` before export and browser integration.

## 1. Set the quality and evidence contract

- Read the actual reference images; record paths, hashes, dimensions and usage rights.
- Record silhouette, pose, visible landmarks, face proportions, hair, outfit, seams and material finish.
- Separate observed features from inferred depth/hidden surfaces. One image cannot establish exact
  3D anatomy, back geometry or identity fidelity. Request extra views only when a named target needs them.
- Record camera/projection, scale assumptions, intended close-up distance, target device and budgets.
  Do not report an assumed body height or generated back view as a measurement or an additional source.
- Write `reference-set.json` and `character-plan.json` in the job: route, observed/inferred anatomy,
  named parts/anchors, topology strategy, material roles, skeleton/face/finger scope, interaction regions,
  source permissions, camera batch and per-feature acceptance thresholds. Main session approves these.
- Make facial likeness, smooth skin, cloth detail and visible interaction separate acceptance items.
  A passing export, many agents, high polygon count or 4K atlas proves none of them.

## 2. Preflight the actual tools

Locate the installed character plugin; set `P` to that directory and `B` to a Python containing bpy.
Do not hard-code a developer's home directory into a job or silently install/change a global runtime.

```bash
"$B" -c 'import bpy; print(bpy.app.version_string); print(bpy.ops.export_scene.gltf.get_rna_type().identifier)'
"$B" "$P/tools/prepare_softbody.py" --help
```

Alternatively use a Blender executable with `--background --factory-startup --disable-autoexec
--python-exit-code 2 --python <job-script>`. Check the actual version's APIs before authoring.
Use an isolated runtime; never execute scripts embedded in downloaded `.blend` files.
The preflight proves tool availability only, not reconstruction or visual quality.

## 3. Author and verify in dependency order

1. **Reference/camera:** solve or explicitly estimate the matching camera; lock a reproducible view.
2. **Blockout:** match silhouette, proportions and pose using native bpy construction or an admitted,
   editable base asset. Preserve its provenance; do not claim imported anatomy was created from scratch.
3. **Surface:** author a continuous head/body, eyelid/lip loops, actual eye volumes and coherent hands.
   Fit hair and separate garment surfaces. Primitives may start a blockout, never masquerade as a face.
4. **Refinement:** finish geometry, retopology and destructive modifiers before UVs/skin/masks freeze.
   Inspect clay and silhouette views; neither textures nor soft-body settings may hide a shape failure.
5. **UV/PBR:** transfer admitted skin textures into the actual UVs; build region-specific fabric/skin
   maps, bake supported channels and inspect seams, texel density and albedo-only/normal-off controls.
6. **Rig:** place a measured bone hierarchy, normalize/limit weights, author the declared face/finger
   controls and clips, then inspect neutral parity and stress deformation in the exported GLB.
7. **Interaction:** paint soft/protected/follower masks, prepare the asset, and connect the existing
   posed-pointer and spring runtime. Measure the effect rather than presenting bone motion as jiggle.
8. **Review:** capture reference/front/quarters/profile/rear and face close-ups from the real browser;
   compare with the source under a fixed camera/light contract. Repair one causal group per iteration.

Record attempts and next action in `character-plan.json`. Default to three focused corrections per
stage and six total; stop earlier on a repeated failure/plateau. Reaching a limit never converts a
failed criterion into a pass. Report the cause and missing evidence instead of switching methods.

Keep reproducible job-local bpy source (`build_character.py` plus bounded component recipes), an
editable master `.blend`, source maps/material recipes and a separate export working copy.
The LLM must write and run the reference-specific authoring scripts; none is supplied by this route.
Do not claim automatic sculpting, retopology, UV transfer or likeness from these instructions alone.
Do not regenerate over a user's master. Every stage consumes the previously accepted artifact/hash.

## 4. Export the already-authored character

After the master, rig, textures and groups exist, follow the config schema in
`softbody-character-route.md`. Use actual object/group/bone names, not the following paths as assets.
Require one material primitive per configured object; split on the working copy before final freeze.

```bash
"$B" "$P/tools/prepare_softbody.py" \
  --source "$W/character.blend" --config "$W/regions.json" --out "$W/export-01"
```

Set `W` to the job directory. The output directory must not already exist. The tool copies/exports
an authored project; it does not accept a reference image or create missing anatomy, weights or maps.
Keep `preparation.json` as the integrity receipt: `prepared-unreviewed` is not visual acceptance.
Use stock glTF-supported images, joints, morphs and baked clips; Blender shaders, IK constraints,
cloth simulation and soft-body modifiers do not become live browser systems merely by exporting.
Read `blender-export-parity.md`: Preserve Volume versus linear skinning, morph normals/tangents,
SSS/cloth shading and baked-animation limits require checks on the actual browser artifact.

## 5. Required deliverables and stop conditions

- Source/reference and asset manifests; `character-plan.json`; runnable native build recipes;
  editable `.blend`; UV/source PBR files; skeleton/weight/pose evidence; authored region config.
- Prepared `.blend`, GLB, matching `softbody.json`, preparation receipt, and actual browser integration.
- Fresh readable screenshots, side-by-side reference comparison, exported hashes, pose/contact/decay
  metrics, unchanged protected/static areas, UV position/normal continuity and triangle/edge checks.
- Record appearance and interaction acceptance separately. Distinguish inspected surfaces from
  unobserved ones; record device performance only when measured on that device.
- If geometry, license, reference quality, capture or tool access blocks a required criterion, repair
  the cause or report that prerequisite. Never silently switch to neural generation, a generic avatar,
  a flat photo plane, procedural pore noise or a favorable distant camera.
- Do not spend credits, publish assets, upload private references or use restricted scan resources
  without permission. A local authoring route does not authorize paid/cloud processing.

## Official tool references

- [Blender retopology](https://docs.blender.org/manual/en/4.5/modeling/meshes/retopology.html)
- [Armature modifier](https://docs.blender.org/manual/en/4.5/modeling/modifiers/deform/armature.html)
- [glTF export](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html)

Use the installed version's documentation when it differs. This route defines work and evidence;
it does not promise photorealistic reconstruction from a single low-resolution image.
