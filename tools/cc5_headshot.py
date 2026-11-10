#!/usr/bin/env python3
"""Export a genuine Auto Setup character through bpy; never generate or replace it.

Run with a Python containing bpy, or `blender -b --factory-startup
--disable-autoexec --python-exit-code 2 --python tools/cc5_headshot.py -- ...`.
CC5/Headshot and FBX import remain explicit licensed-application handoffs.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


def glb_inventory(path):
    with Path(path).open('rb') as stream:
        header = stream.read(20)
        if len(header) != 20:
            raise ValueError('GLB header is incomplete')
        magic, version, total, length, kind = struct.unpack('<4sIIII', header)
        if magic != b'glTF' or version != 2 or kind != 0x4E4F534A:
            raise ValueError('Not a GLB 2 JSON document')
        if total != Path(path).stat().st_size or length > total - 20:
            raise ValueError('GLB length does not match the file')
        doc = json.loads(stream.read(length))
    meshes = doc.get('meshes', [])
    return {
        'meshes': len(meshes),
        'skins': len(doc.get('skins', [])),
        'skinnedNodes': sum('skin' in node for node in doc.get('nodes', [])),
        'morphTargets': sum(max((len(p.get('targets', [])) for p in m['primitives']), default=0) for m in meshes),
        'animations': [a.get('name', str(i)) for i, a in enumerate(doc.get('animations', []))],
        'materials': len(doc.get('materials', [])),
        'images': len(doc.get('images', [])),
    }


def check_export(before, after):
    if not after['meshes'] or not after['skins'] or not after['skinnedNodes']:
        raise ValueError('Export has no usable skinned character')
    if after['morphTargets'] < before['morphTargets']:
        raise ValueError('Export lost facial morph targets')
    if not after['images']:
        raise ValueError('Export has no appearance textures')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def runtime(addon_path, source=None):
    import bpy
    import addon_utils
    if bpy.app.version < (4, 5, 4):
        raise ValueError('Auto Setup route requires bpy/Blender >= 4.5.4')
    addon_path = addon_path.resolve(strict=True)
    if addon_path.name != 'cc_blender_tools' or not (addon_path / '__init__.py').is_file():
        raise ValueError('--addon must point to the official cc_blender_tools package')
    # Load before enabling: file loading can reset preferences and invalidate
    # UI resources registered in the previous Blender database.
    if source is not None:
        if source.suffix.lower() != '.blend' or not source.is_file():
            raise ValueError('--source must be a saved Auto Setup .blend character, not a photo or raw FBX')
        bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
    sys.path.insert(0, str(addon_path.parent))
    # default_set creates process-local AddonPreferences; never save_userpref.
    addon = addon_utils.enable('cc_blender_tools', default_set=True, persistent=True)
    if addon is None or not hasattr(bpy.context.scene, 'CCICBakeProps'):
        raise ValueError('Auto Setup could not register in this bpy runtime')
    # Batch conversion must not reconnect the interactive CC/Blender Data Link.
    timer = addon.link.reconnect
    if bpy.app.timers.is_registered(timer):
        bpy.app.timers.unregister(timer)
    for handlers, callback in ((bpy.app.handlers.load_pre, addon.link.disconnect),
                               (bpy.app.handlers.load_post, addon.link.reconnect)):
        if callback in handlers:
            handlers.remove(callback)
    return bpy, addon


def shutdown(bpy, addon):
    import addon_utils
    # Upstream unregister clears icons but retains their preview collection and
    # pending reconnect timer. Both must be freed before bpy's interpreter exits.
    timer = addon.link.reconnect
    if bpy.app.timers.is_registered(timer):
        bpy.app.timers.unregister(timer)
    icons = addon.iconutils.ICONS
    addon_utils.disable('cc_blender_tools', default_set=True)
    if icons is not None:
        bpy.utils.previews.remove(icons)
        addon.iconutils.ICONS = None


def export(bpy, addon, source, out):
    if source.suffix.lower() != '.blend' or not source.is_file():
        raise ValueError('--source must be a saved Auto Setup .blend character, not a photo or raw FBX')
    if out.exists() or out == source.parent or out in source.parents:
        raise ValueError('--out must be a new directory outside the source project')
    source_hash = digest(source)
    props = bpy.context.scene.CC3ImportProps
    characters = [cache for cache in props.import_cache if cache.get_armature()]
    if len(characters) != 1:
        raise ValueError('Source must contain exactly one imported Auto Setup character')
    cache = characters[0]
    armature = cache.get_armature()
    bpy.ops.object.select_all(action='DESELECT')
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    objects = addon.exporter.get_export_objects(cache, False)
    meshes = [obj for obj in objects if obj.type == 'MESH']
    before = {'meshes': len(meshes), 'bones': len(armature.data.bones),
              'morphTargets': sum(max(0, len(obj.data.shape_keys.key_blocks) - 1)
                                  for obj in meshes if obj.data.shape_keys)}
    if not before['meshes'] or not before['bones'] or not before['morphTargets']:
        raise ValueError('Character needs meshes, a body rig and exported facial morph targets')
    missing = [image.name for image in bpy.data.images if image.source == 'FILE'
               and not image.packed_file and not Path(bpy.path.abspath(image.filepath)).is_file()]
    if missing:
        raise ValueError('Missing source textures: ' + ', '.join(missing))
    out.mkdir(parents=True, exist_ok=False)
    # Save only into the new workspace; never overwrite the incoming master.
    master = out / 'character.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(master), check_existing=False)
    settings = bpy.context.scene.CCICBakeProps
    settings.target_mode = 'GLTF'
    settings.target_format = 'PNG'
    settings.bake_path = str(out / 'textures')
    result = bpy.ops.ccic.baker('EXEC_DEFAULT', param='BAKE')
    if 'FINISHED' not in result or cache.baked_target_mode != 'GLTF':
        raise ValueError('Auto Setup did not complete the glTF material bake')
    glb = out / 'character.glb'
    result = bpy.ops.cc3.exporter('EXEC_DEFAULT', param='EXPORT_BAKED_GLB',
                                filepath=str(glb), include_anim=True, include_selected=False)
    if 'FINISHED' not in result or not glb.is_file():
        raise ValueError('Auto Setup returned without producing a GLB')
    after = glb_inventory(glb)
    check_export(before, after)
    if digest(source) != source_hash:
        raise ValueError('Incoming master changed during export; do not accept this run')
    bpy.ops.wm.save_as_mainfile(filepath=str(master), check_existing=False)
    report = {'route': 'cc5-headshot', 'status': 'exported-unreviewed',
              'source': str(source), 'sourceSha256': source_hash,
              'blender': bpy.app.version_string, 'autoSetup': list(addon.bl_info['version']),
              'glb': glb.name, 'glbSha256': digest(glb), 'before': before, 'after': after,
              'unverified': ['CC5/Headshot provenance and rights', 'clip preservation and pose stress',
                             'Three.js rendering', 'multi-angle likeness and material fidelity']}
    (out / 'export.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Check runtime only; never claims asset readiness')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--out', type=Path)
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    if not args.check and (args.source is None or args.out is None):
        parser.error('--source and --out are required unless --check is used')
    try:
        bpy, addon = runtime(args.addon, None if args.check else args.source.resolve())
        try:
            report = ({'route': 'cc5-headshot', 'status': 'runtime-ready',
                       'blender': bpy.app.version_string, 'autoSetup': list(addon.bl_info['version']),
                       'assetStatus': 'not-evaluated', 'generationStatus': 'not-run'} if args.check else
                      export(bpy, addon, args.source.resolve(), args.out.resolve()))
        finally:
            shutdown(bpy, addon)
        print(json.dumps(report, indent=2))
        return 0
    except (ImportError, OSError, RuntimeError, ValueError, KeyError) as error:
        print(json.dumps({'route': 'cc5-headshot', 'status': 'blocked', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
