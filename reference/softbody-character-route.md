# Soft-body character route

Route ID: `softbody-character`. This is an explicit agent route, not a new harness
`--profile`. It adds interaction to an existing character; it does not generate one.

## Keep source routes explicit

- Native authoring: reference → Blender/bpy geometry or admitted editable base → UV/PBR → rig.
  Follow `blender-character-route.md`; do not substitute neural mesh generation when rejected.
- Real-person likeness: photo/scan → licensed CC5/Headshot → Auto Setup/bpy → GLB.
  Follow `cc5-headshot-route.md`; this route does not replace that handoff or its checks.
- Otherwise legitimately obtained character: existing mesh → Blender/bpy preparation → GLB.
  Record source, rights and provenance; do not claim a measured real-person likeness.
- Any admitted GLB can use the same mask-driven Three.js runtime. Do not rebuild its rig,
  guess a skeleton from names, replace its source, or apply code-only factory gates.

The interaction implementation is original plugin code. A third-party demonstration may
explain the desired behavior, but its JavaScript, models and textures are not licensed inputs
merely because they are publicly downloadable.

## 1. Author the influence masks in Blender

Work on a copy of a character project. Preserve skin weights, rest/bind transforms, UVs,
materials, morphs and clips. Use distinct vertex groups for each independently moving
region: for example left/right chest and left/right hip. These names are examples, not
an anatomical detector. Paint finite weights in `[0,1]` with a smooth transition to zero;
exclude protected areas, arm contact surfaces and unrelated topology explicitly.

For joined hair/body geometry, paint a separate hair group where hair vertices follow a
region. A vertex must also have a region influence to follow it. Separate hair meshes need
their own masks and a matching center/radius in **loaded GLB mesh-local coordinates**;
hair-only regions cannot infer a body center. This is a weighted follower, not a hair/cloth
collision solver. Clothes, teeth, eyes and accessories are not silently stretched.

Input `regions.json`:

```json
{
  "version": 1,
  "meshes": [{
    "name": "Body",
    "hairGroup": "hair_follow",
    "regions": [{
      "id": "chest-left",
      "group": "chest",
      "vertexGroup": "soft_chest_left",
      "bone": "Spine2"
    }]
  }]
}
```

Use the actual unique object and bone names. `bone` is optional and must refer to an existing
joint, never a request to create/rebind it. Do not add `hairGroup` if no hair mask is authored.
For a hair-only region, explicit runtime center/radius must be calibrated after export; do not
copy Blender Z-up or world-space coordinates into a GLB-local sidecar.

## 2. Prepare with bpy, without overwriting the source

Requires a Python environment containing bpy. The existing isolated CC5 runtime can also
run this tool; this step does not need the CC Auto Setup add-on.

Each configured object needs single-user mesh data and one material slot in use (one glTF
primitive). Multi-primitive objects are rejected because GLTFLoader splits them into separate
meshes; prepare separate authored objects on the working copy, preserving their skin/morphs.
The runtime itself preserves material groups on meshes supplied directly.

```bash
B="$HOME/.img2/runtime/character-bpy/bin/python"
P="$HOME/.img2/plugins/character"
"$B" "$P/tools/prepare_softbody.py" \
  --source /absolute/path/to/character.blend \
  --config /absolute/path/to/regions.json \
  --out /absolute/path/to/new-softbody-job
```

Preparation exports scalar `_SOFT_*` custom attributes and optional `_HAIR`, preserving the
incoming rig rather than binding a new skeleton. Output includes `character.glb`, a working
`.blend`, `softbody.json` and `preparation.json`. Require the real exported attributes to have
the same vertex counts as POSITION, finite bounded weights and nonzero support. Require
skin data when the input is rigged and verify the original source hash is unchanged.
`prepared-unreviewed` is not acceptance of appearance, animation or mobile performance.
Mask validation checks count, range and membership in the authored value set, not per-vertex
correspondence after exporter splitting/reordering. Inspect region placement in the viewer.

Runtime sidecar format:

```json
{
  "version": 1,
  "meshes": [{
    "name": "Body",
    "hairAttribute": "_HAIR",
    "regions": [{
      "id": "chest-left",
      "group": "chest",
      "attribute": "_SOFT_CHEST_LEFT",
      "bone": "Spine2"
    }]
  }]
}
```

GLTFLoader lowercases custom attributes; the runtime resolves exact or lowercase names.
Mesh names must resolve uniquely. Influence overlap is normalized rather than multiplying
unbounded displacements. Centers/radii normally derive from the weighted rest surface
excluding hair. Advanced `center: [x,y,z]` and positive `radius` overrides are in the loaded
GLB mesh's **pre-skin local coordinates**, not anatomical constants.

Never simplify/reorder vertices after exporting the sidecar without carrying the custom
attributes through and validating the resulting GLB. Never use a sidecar from another asset.

## 3. Integrate, exercise and accept

Read `softbody-runtime.md` completely before attaching controllers or connecting pointer input.
It contains the Three.js API, posed-hit contract, diagnostic viewer command and actual-character
acceptance criteria. Preparation alone never passes that acceptance.

## 4. Dressing the prepared character

To add a connected garment, an outfit change and an outer-layer guarantee on top of a prepared
character, continue with `garment-character-route.md` (acceptance: `garment-acceptance.md`). It keeps
this route's solver and sidecar untouched and needs its masks, so finish and review this route first.


