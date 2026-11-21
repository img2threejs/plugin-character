#!/usr/bin/env python3
"""Owned native base-mesh -> freeze -> additive bind -> export measurement.

Run only with a host-selected isolated Python containing bpy. The input blend is
never saved. No operators, callbacks, Python text or executable paths come from it.
This producer deliberately rejects already-bound/imported rigs rather than rebinding.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_glb_freeze import preserve_normals
from prepare_softbody import _gltf_properties


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_geometry(meshes, rig):
    return {"meshes": {obj.name: {
        "matrixWorld": [v for row in obj.matrix_world for v in row],
        "position": [list(v.co) for v in obj.data.vertices],
        "polygons": [list(p.vertices) for p in obj.data.polygons],
        "uv": {uv.name: [list(v.uv) for v in uv.data] for uv in obj.data.uv_layers},
        "weights": [[(obj.vertex_groups[g.group].name, g.weight) for g in v.groups]
                    for v in obj.data.vertices],
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
    } for obj in meshes}, "rig": {"matrixWorld": [v for row in rig.matrix_world for v in row],
        "bones": [{"name": b.name, "parent": b.parent.name if b.parent else None,
                   "matrixLocal": [v for row in b.matrix_local for v in row], "deform": b.use_deform}
                  for b in rig.data.bones]}}


def points(bpy, obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = evaluated.to_mesh()
    try:
        # Explicit Blender Z-up -> glTF Y-up conversion. Do not normalize the asset.
        return [[p.x, p.z, -p.y] for v in data.vertices for p in [evaluated.matrix_world @ v.co]]
    finally:
        evaluated.to_mesh_clear()


def export(bpy, path, *, skins):
    supported = _gltf_properties(bpy)
    settings = {"filepath": str(path), "export_format": "GLB", "check_existing": False,
                "use_selection": True, "export_apply": False, "export_skins": skins,
                "export_morph": False, "export_animations": True, "export_force_sampling": True,
                "export_animation_mode": "ACTIONS", "export_frame_range": False,
                "export_reset_pose_bones": True, "export_yup": True,
                "export_rest_position_armature": True, "export_anim_slide_to_zero": True,
                "export_def_bones": False, "export_all_influences": False}
    required = {"export_apply", "export_skins", "export_animations", "export_force_sampling",
                "export_animation_mode", "export_frame_range", "use_selection",
                "export_rest_position_armature", "export_anim_slide_to_zero"}
    if not required <= supported:
        raise ValueError("native glTF exporter lacks required controlled options")
    # REST disables evaluated animation in bpy even when the exporter visits frames.
    # Keep rest bind extraction explicit, but evaluate real POSE animation while exporting.
    modes = {obj: obj.data.pose_position for obj in bpy.context.selected_objects if obj.type == "ARMATURE"}
    for obj in modes:
        obj.data.pose_position = "POSE"
    bpy.context.view_layer.update()
    try:
        result = bpy.ops.export_scene.gltf(**{k: v for k, v in settings.items() if k in supported})
    finally:
        for obj, mode in modes.items():
            obj.data.pose_position = mode
        bpy.context.view_layer.update()
    if "FINISHED" not in result or not path.is_file():
        raise ValueError("native GLB export did not finish")


def scene_roster(bpy, spec):
    """Use the same complete renderable-mesh eligibility before either export."""
    visible = {o.name for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render}
    if visible != set(spec["meshes"]):
        raise ValueError("native capture must include every renderable mesh")
    rigs = {o.name for o in bpy.context.scene.objects if o.type == "ARMATURE"}
    if rigs != {spec["armature"]}:
        raise ValueError("native capture must include only the approved armature")
    rig = bpy.data.objects[spec["armature"]]
    meshes = [bpy.data.objects[name] for name in spec["meshes"]]
    if rig.type != "ARMATURE" or any(o.type != "MESH" for o in meshes):
        raise ValueError("native armature/mesh declarations do not match actual objects")
    if any(o.hide_render or o.hide_get() for o in meshes):
        raise ValueError("declared native mesh is hidden")
    return rig, meshes


def capture(job, out):
    import bpy
    if bpy.app.version < (4, 3, 0):
        raise ValueError("producer-dependency-missing: character-bpy>=4.3")
    source = Path(job["sourcePath"]).resolve(strict=True)
    source_sha = sha(source)
    if source_sha != job["sourceSha256"]:
        raise ValueError("native source blend hash changed")
    if out.exists():
        raise ValueError("native output directory must be new")
    spec = job["spec"]
    if set(spec) != {"armature", "meshes", "actions"}:
        raise ValueError("native spec requires only armature, meshes and actions")
    for name in ("meshes", "actions"):
        if (not isinstance(spec[name], list) or not spec[name]
                or any(not isinstance(v, str) or not v for v in spec[name])
                or len(set(spec[name])) != len(spec[name])):
            raise ValueError("native mesh/action declarations must be nonempty and unique")
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
    if bpy.data.libraries or any(o.library or o.override_library for o in bpy.data.objects):
        raise ValueError("linked native libraries/overrides need an explicit packaging producer")
    if any(i.source == "FILE" and not i.packed_file for i in bpy.data.images):
        raise ValueError("native file images must be packed before capture")
    rig, meshes = scene_roster(bpy, spec)
    if any(o.modifiers or o.data.shape_keys for o in meshes):
        raise ValueError("apply destructive modifiers before freeze; already-bound/morph meshes unsupported")
    if set(spec["actions"]) != {a.name for a in bpy.data.actions}:
        raise ValueError("declare the complete native action roster; no silent clip omission")
    if rig.animation_data and rig.animation_data.nla_tracks:
        raise ValueError("native NLA composition requires a dedicated parity producer")
    bones = {b.name for b in rig.data.bones if b.use_deform}
    for obj in meshes:
        if obj.parent and obj.parent != rig:
            raise ValueError("native mesh has a foreign parent")
        for v in obj.data.vertices:
            weights = [g.weight for g in v.groups if obj.vertex_groups[g.group].name in bones and g.weight > 0]
            if (not weights or len(weights) > 4 or any(not math.isfinite(w) for w in weights)
                    or abs(sum(weights) - 1) > 2e-7):
                raise ValueError("author normalized finite one-to-four bone influences before binding")
    out.mkdir(parents=True)
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    source_geometry = native_geometry(meshes, rig)
    source_rest = {o.name: points(bpy, o) for o in meshes}
    # Canonicalize the WORKING mesh's world frame before freezing. The source master
    # and rig rest transforms are untouched; Blender otherwise bakes object matrices
    # only on the skinned export, silently changing its local POSITION representation.
    from mathutils import Matrix
    for obj in meshes:
        matrix = obj.matrix_world.copy()
        if not matrix.determinant():
            raise ValueError("singular mesh transform cannot define frozen normals")
        obj.data = obj.data.copy()
        obj.data.transform(matrix)
        if matrix.determinant() < 0:
            obj.data.flip_normals()
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    rest = {o.name: points(bpy, o) for o in meshes}
    all_source = [p for values in source_rest.values() for p in values]
    height = max(p[1] for p in all_source) - min(p[1] for p in all_source)
    tolerance = height * 1e-4  # Existing native world-parity limit, before freeze.
    frame_delta = max(math.dist(a, b) for name in rest for a, b in zip(rest[name], source_rest[name]))
    if not tolerance > 0 or frame_delta > tolerance:
        raise ValueError("pre-freeze canonical frame failed actual source-world parity")
    frozen = native_geometry(meshes, rig)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [rig, *meshes]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = rig
    # Attach every declared action to the working armature for ACTIONS export.
    # These tracks are producer-owned, not imported NLA composition.
    rig.animation_data_create()
    active = rig.animation_data.action
    for name in spec["actions"]:
        if active and active.name == name:
            continue
        action = bpy.data.actions[name]
        track = rig.animation_data.nla_tracks.new()
        track.name = name
        track.strips.new(name, int(action.frame_range[0]), action)
    export(bpy, out / "base.glb", skins=False)
    for obj in meshes:
        modifier = obj.modifiers.new(name="img2-owned-linear-bind", type="ARMATURE")
        modifier.object = rig
        modifier.use_deform_preserve_volume = False
    if native_geometry(meshes, rig) != frozen:
        raise ValueError("binding changed frozen native geometry/weights/rest rig")
    export(bpy, out / "raw-bound.glb", skins=True)
    normal_preservation = preserve_normals(out / "base.glb", out / "raw-bound.glb", out / "character.glb")
    samples = {}
    rig.data.pose_position = "POSE"
    rig.animation_data_create()
    for track in rig.animation_data.nla_tracks:
        track.mute = True
    for name in spec["actions"]:
        action = bpy.data.actions[name]
        rig.animation_data.action = action
        start, end = map(float, action.frame_range)
        if not end > start:
            raise ValueError("native action has no positive frame range")
        frames = []
        for fraction in (0, .25, .5, .75, 1):
            frame = start + (end - start) * fraction
            bpy.context.scene.frame_set(math.floor(frame), subframe=frame - math.floor(frame))
            bpy.context.view_layer.update()
            measured = {o.name: points(bpy, o) for o in meshes}
            if any(len(measured[o.name]) != len(rest[o.name]) for o in meshes):
                raise ValueError("native evaluated topology changed")
            frames.append({"fraction": fraction, "meshes": measured})
        samples[name] = frames
    rig.animation_data.action = active
    for track in rig.animation_data.nla_tracks:
        track.mute = False
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    if native_geometry(meshes, rig) != frozen or sha(source) != source_sha:
        raise ValueError("native source/geometry/rest rig changed during measurement")
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "character.blend"), check_existing=False)
    receipt = {"kind": "img2.character-native-capture", "version": 1,
               "sourceSha256": source_sha, "spec": spec, "blenderVersion": bpy.app.version_string,
               "producerSha256": sha(__file__), "baseGlbSha256": sha(out / "base.glb"),
               "glbSha256": sha(out / "character.glb"), "nativeGeometry": frozen,
               "restWorld": rest, "poseSamples": samples,
               "sourceGeometry": source_geometry,
               "frameNormalization": {"method": "working-mesh-world-before-freeze",
                                      "maxSourceWorldDelta": frame_delta, "tolerance": tolerance},
               "normalPreservation": normal_preservation,
               "files": [{"path": p.name, "sha256": sha(p)} for p in
                         (out / "base.glb", out / "raw-bound.glb", out / "character.glb", out / "character.blend")]}
    if "masterPath" in job:
        master = Path(job["masterPath"])
        if sha(master) != job["masterSha256"]:
            raise ValueError("bound native master changed before replay")
        bpy.ops.wm.open_mainfile(filepath=str(master), load_ui=False, use_scripts=False)
        saved_rig, saved_meshes = scene_roster(bpy, spec)
        saved_rig.data.pose_position = "REST"
        bpy.context.view_layer.update()
        if native_geometry(saved_meshes, saved_rig) != frozen:
            raise ValueError("bound native master changed frozen geometry/weights/rest rig")
        for obj in saved_meshes:
            if (len(obj.modifiers) != 1 or obj.modifiers[0].type != "ARMATURE"
                    or obj.modifiers[0].object != saved_rig or obj.modifiers[0].use_deform_preserve_volume):
                raise ValueError("bound native master does not retain the owned linear binding")
        bpy.ops.object.select_all(action="DESELECT")
        for obj in [saved_rig, *saved_meshes]:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = saved_rig
        check = out / "master-check.glb"
        export(bpy, check, skins=True)
        if sha(check) != normal_preservation["rawBoundGlbSha256"] or sha(master) != job["masterSha256"]:
            raise ValueError("bound native master does not reproduce exact delivery rig/geometry/clip bytes")
        check.unlink()
    (out / "native.json").write_bytes(canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    try:
        if args.probe:
            import bpy
            if bpy.app.version < (4, 3, 0):
                raise ValueError("producer-dependency-missing: character-bpy>=4.3")
            print(json.dumps({"kind": "img2.character-bpy-probe", "version": 1,
                              "executable": str(Path(sys.executable).absolute()),
                              "bpyVersion": bpy.app.version_string,
                              "bpyModule": str(Path(bpy.__file__).resolve())}))
            return 0
        if args.input is None or args.out is None:
            raise ValueError("--input and --out are required for capture")
        capture(json.loads(args.input.read_bytes()), args.out)
    except Exception as error:
        print("native capture blocked: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
