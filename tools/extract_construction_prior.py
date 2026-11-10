#!/usr/bin/env python3
"""Extract a machine-readable construction prior from one character GLB.

Runs the three `character_prior` analysis modules over the same file and merges their output into
one document the img2 character skill can use as a template when a new character image arrives:

    {schema: 'img2.character-construction-prior/1', source, inventory, anatomy, construction, generatedBy}

    python3 tools/extract_construction_prior.py --glb character.glb --out prior.json
    python3 tools/extract_construction_prior.py --glb character.glb --out prior.json --skip anatomy

Each module exposes `analyze(glb_path, **options) -> dict` with `schema`, `observed`, `inferred` and
`limits` keys. A module that is missing fails the run loudly and by name -- a prior with a silent
hole in it would read as "that part has no facts". `--skip` is the explicit way to leave one out; a
skipped module is recorded as null and listed under `skipped`.

Exit codes: 0 = written, 1 = a module raised while analysing, 2 = bad usage, unreadable input, or a
module that could not be imported.

Pure Python 3.10+ stdlib.
"""

import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

SCHEMA = "img2.character-construction-prior/1"
MODULES = ("inventory", "anatomy", "construction")
SUMMARY_LINES = 20


def load_module(name):
    """Import `character_prior.<name>`, naming the module in the failure."""
    try:
        return importlib.import_module("character_prior.%s" % name)
    except ModuleNotFoundError as err:
        if err.name in ("character_prior", "character_prior.%s" % name):
            raise RuntimeError(
                "analysis module %r is missing: expected %s" % (name, os.path.join(TOOLS_DIR, "character_prior", name + ".py"))
            ) from err
        raise RuntimeError("analysis module %r could not be imported: %s" % (name, err)) from err
    except Exception as err:  # a syntax or import-time error in the module is still "that module is broken"
        raise RuntimeError("analysis module %r could not be imported: %s: %s" % (name, type(err).__name__, err)) from err


def measure_height(glb_path):
    """Height used for `source` when the inventory module is skipped: the reader's own measure."""
    import rig_glb_reference as rgr

    rig = rgr.read_rig(glb_path)
    height, source = rgr.derive_figure_height(rig)
    return round(height, 6), source


def summarise(prior):
    """At most SUMMARY_LINES lines of what was extracted, from the merged document."""
    src = prior["source"]
    lines = [
        "construction prior: %s" % src["path"],
        "  bytes=%d sha256=%s" % (src["bytes"], src["sha256"][:16]),
        "  H=%s m (%s)" % (src["heightM"], src["heightSource"]),
    ]
    inv = prior.get("inventory")
    if inv:
        budgets = inv["observed"]["budgets"]
        body = inv["inferred"]["bodyMesh"].get("mesh")
        lines.append("  inventory: %d meshes, %d verts, %d tris, %d joints, %d materials, %d images; body mesh %s" % (
            budgets["meshCount"], budgets["totalVertices"], budgets["totalTriangles"], budgets["jointCount"],
            budgets["materialCount"], budgets["imageCount"], body))
        roles = inv["inferred"]["budgetsByRole"]["roles"]
        share = ", ".join("%s %s%%" % (role, round(100 * (entry["triangleShare"] or 0), 1))
                          for role, entry in sorted(roles.items(), key=lambda kv: -(kv[1]["triangleShare"] or 0)))
        lines.append("  triangle share by role: %s" % share)
    for name in ("anatomy", "construction"):
        section = prior.get(name)
        if section:
            observed = section.get("observed", {})
            lines.append("  %s: %s; %d observed groups, %d inferred groups, %d limits" % (
                name, section.get("schema"), len(observed), len(section.get("inferred", {})), len(section.get("limits", []))))
    if prior["skipped"]:
        lines.append("  skipped: %s" % ", ".join(prior["skipped"]))
    return lines[:SUMMARY_LINES]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="extract_construction_prior.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--glb", required=True, type=Path, help="character GLB to analyse (read-only)")
    parser.add_argument("--out", type=Path, default=None, help="where to write the merged JSON prior")
    parser.add_argument("--body-mesh", default=None, help="mesh (or node) name of the body mesh; default autodetected")
    parser.add_argument("--skip", action="append", default=[], choices=MODULES, help="leave one module out (repeatable)")
    args = parser.parse_args(argv)

    glb = args.glb.expanduser()
    if not glb.is_file():
        print("error: GLB not found: %s" % glb, file=sys.stderr)
        return 2
    if args.out is not None:
        out = args.out.expanduser()
        if out.resolve() == glb.resolve() or (out.exists() and out.samefile(glb)):
            print("error: --out must not overwrite the input GLB", file=sys.stderr)
            return 2
    skipped = sorted(set(args.skip))
    active = [name for name in MODULES if name not in skipped]

    modules = {}
    for name in active:
        try:
            modules[name] = load_module(name)
        except RuntimeError as err:
            print("error: %s" % err, file=sys.stderr)
            return 2

    options = {}
    if args.body_mesh:
        options["body_mesh"] = args.body_mesh

    results = {name: None for name in MODULES}
    for name in active:
        try:
            results[name] = modules[name].analyze(str(glb), **options)
        except ValueError as err:
            # parse_glb and the modules raise ValueError for an input that is not a usable GLB
            print("error: %s.analyze rejected %s: %s" % (name, glb, err), file=sys.stderr)
            return 2
        except Exception as err:
            print("error: %s.analyze failed on %s: %s: %s" % (name, glb, type(err).__name__, err), file=sys.stderr)
            return 1

    data = glb.read_bytes()
    inventory = results["inventory"]
    if inventory is not None:
        figure = inventory["observed"]["figureHeight"]
        height, height_source = figure["heightM"], figure["heightSource"]
    else:
        try:
            height, height_source = measure_height(glb)
        except (ValueError, KeyError) as err:
            height, height_source = None, "unmeasured: %s" % err
    prior = {
        "schema": SCHEMA,
        "source": {
            "path": str(glb.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "heightM": height, "heightSource": height_source,
        },
        "inventory": results["inventory"],
        "anatomy": results["anatomy"],
        "construction": results["construction"],
        "skipped": skipped,
        "generatedBy": {"tool": "tools/extract_construction_prior.py", "python": sys.version.split()[0]},
    }
    if args.out is not None:
        out = args.out.expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(prior, indent=2, sort_keys=False, allow_nan=False) + "\n", encoding="utf-8")
    for line in summarise(prior):
        print(line)
    if args.out is not None:
        print("  wrote %s (%d bytes)" % (args.out, args.out.expanduser().stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
