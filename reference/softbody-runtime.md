# Soft-body runtime integration and acceptance

Read `softbody-character-route.md` first for source admission, bpy preparation and sidecar schema.

## 3. Attach to the destination Three.js app

The plugin's diagnostic package pins Three.js 0.186.1. In a destination app, use its existing
Three.js dependency and one shared module instance. Validate compatibility rather than
loading a second copy from a CDN.

```js
import { attachSoftBodies } from './runtime/softbody.mjs';
const bodies = attachSoftBodies(gltf.scene, sidecar);
// A UI slider drives the actual region id, not a new morph target:
bodies[0].setSize('chest-left', 1.2); // valid range 0.6–1.5
bodies[0].setSoftness(0.7);          // valid range 0–1

// In the existing frame loop, before rendering:
mixer?.update(dt);
gltf.scene.updateMatrixWorld(true);
for (const body of bodies) body.update(dt);
renderer.render(scene, camera);

// On unload, BEFORE disposing the original GLB resources:
for (const body of bodies) body.dispose();
```

The runtime partitions affected triangles into a dynamic child mesh while the original mesh
renders the static complement. It shares the original skeleton and materials, preserves
attribute/material-group data and live morph influence state, and restores the incoming
geometry on disposal. It does not author a walk clip, facial rig or new skin weights.

The solver uses bounded time steps with four spring/damping substeps by default. It combines
weighted size deformation, oscillation, local indentation, surrounding bulge and drag/shear;
normals are recomputed on active geometry with blending at the static boundary. Coincident
UV-split vertices share area-normal accumulation only when their rest normals, deformation
masks, skin attributes and morph attributes agree; authored hard edges remain separate.
Typed buffers are prepared up front; do not rebuild controllers every frame.

The combined field is projected toward rest before normal updates: each triangle keeps
at least 15% of its rest-projected signed area and edges stay within 0.4–1.8× rest length.
The first unsafe point is checked even when a candidate collapses and recovers orientation.
One constrained triangle can reduce other regions' motion. This guard does not repair
degenerate source topology or guarantee collision freedom or validity after arbitrary skin/morph poses.

Use `impulse(regionId, localVector3)` to supply a measured local-space motion impulse when
an authored motion/controller needs inertial response. AnimationMixer moving bones alone is
not evidence of body oscillation. Do not invent motion or claim an automatic physics rig.

For motion-driven inertia, sample an authored region anchor through its bone's bind/current
matrices. Convert negative world velocity change into the mesh's pre-skin frame before
calling `impulse`; do not pass world vectors directly under a rotated/scaled rig.
Warm-start velocity history, clear it on clip restart, and scale impulse caps with `dt`.
Update mixer, world matrices, motion impulses, then soft bodies before rendering.

## 4. Connect pointer input in posed coordinates

Raycast the real scene and respect the nearest visible surface; do not poke a region through
an occluding body/clothing mesh. If the nearest hit's object is a controller's `dynamicMesh`:

- `token = body.press(intersection)` on pointer down;
- `body.move(token, intersection)` on drag over the same dynamic mesh;
- `body.release(token)` on up, cancel, lost capture, navigation or asset replacement.

Use pointer capture and disable camera orbit during an active press. Restore camera input
when the interaction ends. Limit concurrent contacts; do not leave a held press on touch cancel.
The runtime maps hit triangles from skinned/morphed world positions back to the rest surface
using barycentric coordinates. A bare `worldToLocal(hit.point)` is wrong under a bent skeleton.

`reset()` returns soft-body size/press/oscillation state to neutral without deleting the
caller's original morph state. `dispose()` restores source geometry and does not free shared
materials or textures. `attachSoftBodies` rolls back already attached controllers if a later
mesh/region fails validation.

## 5. Run the local diagnostic viewer

```bash
cd "$HOME/.img2/plugins/character"
npm ci --ignore-scripts
npm run demo:softbody
# Open http://127.0.0.1:8768/examples/softbody/
```

The initial fixture is a geometric surface with a real two-joint skin, a morph and a marked
hair-follow strip. It is deliberately **not a generated human**. It exercises size, protected
surface, softness, impulse, press/drag/release, posed picking, morph preservation and reset.
The viewer can also open a prepared local GLB plus its `softbody.json`; it does not upload
files and refuses external asset resource URLs. The diagnostic pose control is disabled for
user assets: do not rotate an arbitrary character's first bone.

If no destination app or real character exists, finish the executable diagnostic route and
report that character-specific visual acceptance is still blocked. Do not edit an unrelated
showcase or claim the fixture proves likeness/photorealism.

## 6. Acceptance for each actual character

1. Capture neutral and changed sizes from front, side, three-quarter and rear. Check seams,
   shading, protected anatomy, clothes and accessories; include hair/body overlap.
   Include face/skin close-ups; normal-map-off and clay comparisons distinguish geometric
   quantization from texture/PBR noise. Preserve facial landmarks when refining source geometry.
2. Measure actual vertex changes for size, held press, drag and release; confirm decay and
   finite bounded positions after a long frame. Compare firm and soft responses.
   Check triangle orientation/area, edge strain, coincident UV positions and smooth-normal
   continuity, not just finite coordinates or unit normals. Preserve authored hard edges.
   Compare the deformed and neutral surfaces in the same bone pose.
3. Bend the real skeleton and use a real Raycaster hit: the contact must remain on the posed
   surface. Exercise existing morphs/clips and check skinning, material groups and UVs survive.
4. Reset restores neutral soft geometry while retaining source morph state. Detach restores
   original geometry/resources. Reject missing/malformed masks instead of displaying a fallback;
   use preparation hashes to ensure the sidecar belongs to this GLB.
5. Benchmark the requested devices. Record frame time, dynamic triangle counts and renderer;
   desktop viewport emulation is not a phone performance result. This CPU surface solver is
   not a volumetric/FEM simulator or a universal cloth/hair collision solution.

Run the package's Node behavioral tests and existing Python regression suite after changes.
Set `IMG2_CC5_PYTHON` to a real bpy interpreter to include preparation roundtrip coverage.
