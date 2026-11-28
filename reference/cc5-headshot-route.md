# CC5 / Headshot external-asset route

Route ID: `cc5-headshot`. Explicit opt-in, independent of procedural reconstruction.
This is an agent route, NOT a new harness `--profile`: keep `domain.json` unchanged.

## Boundary

Real photo/scan → licensed CC5 + Headshot 3 → Blender Auto Setup → bpy bake/export
→ GLB → Three.js. Never generate a procedural substitute or rebuild an imported rig.
`bpy` controls Blender, NOT CC5/Headshot. CC5/Headshot authoring runs on Windows;
Blender authoring/export can run on macOS. No paid generation or image upload is implied.
Never call this route code-only. Do not claim a likeness from a generic/demo asset.

## 1. Admit the real source

Require an actual reference image/scan and consent to use the person's likeness.
Record local source paths/hashes, CC5/Headshot versions and content-use rights in
`character-route.json` in the job workspace. Include `route: "cc5-headshot"` and
`status: "blocked"` until the next real stage has evidence. Never infer product ownership,
licenses, export provenance or an application install from a directory name.
If Windows/CC5, a real reference, or the export is unavailable, name that missing prerequisite.
Complete available preflight work, but never label a substitute mesh as a CC5 result.

## 2. CC5 / Headshot handoff (licensed application)

- For photos, use Headshot 3 Image workflow; for scans, use its Mesh workflow.
- Refine likeness in front/profile/three-quarter views before proceeding.
- Export a clothed FBX with the body skeleton, facial morphs, accompanying JSON and textures.
  Keep the complete export folder together. Include motion clips only when actually authored.
- In Blender, use the official Auto Setup importer/Data Link, not bare FBX import: it builds
  the digital-human material graphs using the JSON/texture data.
- Save one imported character as a `.blend` project with textures packed or resolvable.
  Preserve the incoming project; the adapter writes only into a new output workspace.
- This saved Auto Setup project is the executable adapter's input. Raw FBX and photos are
  deliberately rejected; their authoring/import stages must not be silently skipped.

## 3. Blender runtime preflight

Use Blender/bpy >= 4.5.4 and the official `soupday/cc_blender_tools` add-on.
Read the add-on's version requirements when updating it. Installing the add-on executes
third-party Python; use the reviewed official checkout, not code bundled with an input asset.

For an isolated pip runtime, Python 3.11 with `bpy==4.5.15` and Auto Setup 2.4.5 have
passed preflight and invalid-source rejection on macOS arm64. Install bpy into a dedicated
virtual environment (`python3.11 -m venv ...`, then that environment's
`python -m pip install bpy==4.5.15`); clone the official add-on separately.
Do not modify an unrelated project's Blender environment.

```bash
B=/absolute/path/to/python-with-bpy
P=/absolute/path/to/plugin-character
A=/absolute/path/to/cc_blender_tools
"$B" "$P/tools/cc5_headshot.py" --addon "$A" --check
```

`runtime-ready` proves only bpy/add-on registration, not CC5 availability, asset readiness,
character creation or rendering. A missing runtime/add-on returns `blocked` and exit code 2.
The tool does not install dependencies, launch CC5, upload images or buy licenses.

The adapter loads the source before registering Auto Setup, creates process-local add-on
preferences without saving user preferences, disables interactive Data Link callbacks and
releases add-on preview resources on exit. Require exit code 0, not just a printed readiness
message: registration alone previously passed before a native shutdown crash.
The tested local layout uses `~/.img2/runtime/character-bpy/bin/python`,
`~/.img2/runtime/cc_blender_tools` and `~/.img2/plugins/character`.
The real-character bake/export and browser stages remain unverified until a genuine source
is available; no runtime probe certifies them.

## 4. bpy bake and GLB export

```bash
"$B" "$P/tools/cc5_headshot.py" --addon "$A" \
  --source /absolute/path/to/imported-character.blend \
  --out /absolute/path/to/new-character-job
```

The adapter uses `open_mainfile(use_scripts=False)`, requires exactly one Auto Setup
character with bones and facial morphs, checks missing texture files, saves a working copy,
then calls the official `ccic.baker` with target `GLTF` and `cc3.exporter` with
`EXPORT_BAKED_GLB`. It does not flatten the CC shader graph by guessing PBR constants.
An operator returning `FINISHED` is insufficient: require the baked target and real GLB.
Verify skinned nodes, appearance images and morph-target count; record the original hash.

Artifacts: `character.blend`, `character.glb`, bake textures and `export.json`.
`exported-unreviewed` is not visual acceptance. Failed runs may leave diagnostic artifacts
but never get a success receipt; use a new output directory after fixing the source.
Baking does not preserve every dynamic wrinkle/SSS/groom feature of the native shader.
Do not decimate, rebind, retarget or rewrite weights unless the user separately requests it.

Optional interaction layer: continue with `softbody-character-route.md` for authored region
masks and a Three.js size/press/drag/bounce deformer. Keep the accepted CC authoring master
and rig; prepare a new output copy. This composes with CC5/Headshot rather than replacing it,
and does not make native wrinkle, cloth or hair collision features survive the GLB handoff.

## 5. Three.js consumer

Use the destination app's Three.js version and `GLTFLoader`. Keep the imported skeleton,
morph dictionaries, authored names and clips. Do not convert to ObjectSculptSpec or a
procedural factory. Display scale/offset belongs on a parent Group, not on individual bones.

```js
import { Group, AnimationMixer } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const gltf = await new GLTFLoader().loadAsync('/assets/character/character.glb');
const displayRoot = new Group();
displayRoot.add(gltf.scene);
scene.add(displayRoot);
const mixer = new AnimationMixer(gltf.scene);
// Expose actual clips to the app's chooser; never invent a walk/idle clip.
const play = (clip) => { mixer.stopAllAction(); mixer.clipAction(clip).reset().play(); };
// Call mixer.update(deltaSeconds) in the app's existing render loop.
```

`scene`, the chooser, lights and render loop come from the destination app, not this adapter.
If no app is designated, request the destination before editing an unrelated showcase.
Do not promise unchanged Blender/Cycles skin or hair appearance in WebGL.

## 6. Acceptance evidence

Open the real browser route. Capture front, three-quarter, side and rear, plus close face,
hair and hands. Compare against the admitted reference, not a generated substitute.
Measure at least one actual skin deformation and facial morph; restore bind/neutral state.
For every supplied clip, sample motion and confirm the affected bones/vertices really move.
No source clips means no motion-preservation claim; pose stress and face tests still apply.
Record browser errors, renderer, viewport, source/output hashes, clip/morph inventory and captures.
Only mark accepted after likeness, materials and deformation pass; missing evidence is blocked.

## Sources

- https://www.reallusion.com/character-creator/headshot/
- https://www.reallusion.com/auto-setup/blender/default.html
- https://github.com/soupday/cc_blender_tools
- https://discussions.reallusion.com/t/format-changing-of-character-using-blender/13292
- https://docs.blender.org/api/current/bpy.ops.wm.html
