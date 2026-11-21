#!/usr/bin/env python3
"""Synthetic native wiring diagnostic only: not a reference-derived character."""
import argparse
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gate_rigging import JOINTS


def build(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new("DiagnosticRig")
    rig = bpy.data.objects.new("DiagnosticRig", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    heads = {}
    for row in JOINTS:
        parent = heads.get(row["parent"], (0, 0, 0))
        local = row["localPosition"]
        point = [a + b for a, b in zip(parent, local)]
        heads[row["id"]] = point
        bone = data.edit_bones.new(row["id"])
        bone.head = (point[0], -point[2], point[1])
        bone.tail = (point[0], -point[2], point[1] + .025)
        if row["parent"]:
            bone.parent = data.edit_bones[row["parent"]]
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=.5, location=(0, 0, .5))
    body = bpy.context.object
    body.name = "DiagnosticBody"
    # Keep nonidentity production transforms: canonicalization must not be a
    # fixture-only escape from the translated/rotated/nonuniform-scale exporter case.
    body.rotation_euler = (.17, .23, .31)
    body.scale = (.9, 1.1, 1.0)
    bpy.context.view_layer.update()
    world = [body.matrix_world @ v.co for v in body.data.vertices]
    body.location.x -= (min(v.x for v in world) + max(v.x for v in world)) / 2
    body.location.y -= (min(v.y for v in world) + max(v.y for v in world)) / 2
    body.location.z -= min(v.z for v in world)
    bpy.context.view_layer.update()
    for polygon in body.data.polygons:
        polygon.use_smooth = True
    material = bpy.data.materials.new("DiagnosticOpaque")
    material.diffuse_color = (.6, .5, .4, 1)
    body.data.materials.append(material)
    root = body.vertex_groups.new(name="root")
    head = body.vertex_groups.new(name="head")
    for vertex in body.data.vertices:
        (head if vertex.co.z > .2 else root).add([vertex.index], 1, "REPLACE")
    rig.animation_data_create()
    bone = rig.pose.bones["head"]
    for frame, offset in ((1, 0), (13, .025), (25, 0)):
        bone.location = (offset, 0, 0)
        bone.keyframe_insert("location", frame=frame, group="head")
    action = rig.animation_data.action
    action.name = "nod"
    for curve in action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"
    bpy.context.scene.render.fps = 24
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 25
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("fixture refuses an existing source")
    build(args.out)
