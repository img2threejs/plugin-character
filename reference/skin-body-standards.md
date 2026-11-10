# Skin/body standards and independent measurement

`skin-body-standards.json` orders S1–S8. Each check identifies a metric, comparison,
unit, provenance case and rationale. `behaviour` is a mechanism; `single-subject`
is a starting observation, not a universal prescription. The latter include island
tone, join counts, bone count and the explicitly declared hair-chain layout, material
scalars, and export tolerances. Re-derive those for the subject and record a reviewed
job-specific standards file; do not transplant the historical figures blindly.

An authoring agent writes and runs its own subject-specific bpy scripts. It retains the
admitted original, records permissions and attribution, and hands the reviewer the
source and output hashes, explicit object/vertex correspondence, selected atlas,
repair mask and stage artifacts. The independent measurer opens but does not save
the artifact. Run it in a separate process using the bpy Python interpreter:

```sh
"$B" tools/bpy_measure_skin_body.py --blend "$W/character.blend" \
  --baseline-blend "$W/baseline.blend" --catalogue reference/body-parts.json \
  --character "$ASSET_ID" --atlas "$IMAGE_NAME" --mirror-pairs "$W/pairs.json" \
  --source "body=$W/source.png:$SOURCE_SHA256" --composite-atlas \
  --resolution-baseline-blend "$W/other-resolution.blend" \
  --repair-mask "$W/repair-mask.json" --protected-mask "$W/protected-mask.json" \
  --island-mask "$W/island-mask.json" --reference-mask "$W/reference-mask.json" \
  --out "$W/evidence.json"
python3 tools/gate_skin_body.py --evidence "$W/evidence.json" --stage S5 --json
```

`--character` is a catalogue **asset ID**, not a default character. A mirror file is
`{"object_a":"...","object_b":"...","pairs":[[0,1]],"permutation":{"Left":"Right","Right":"Left"}}`;
indices refer to each named mesh, and the permutation must map every influencing bone.
Repeated, invalid or unmapped pairs count as unmatched. `--source NAME=PATH:SHA256`
is repeatable; supply independently pinned source hashes, not fresh hashes made after
editing. The receipt reports each actual and expected digest and match; the historical
metric name `original_changed_bytes` counts mismatching **sources**, not individual
bytes. SHA-256 equality is a content-integrity check, not a permission or rights claim.
The source file and output artifact must not be the same path when the output is being
authored. Mask inputs (`--repair-mask`, `--protected-mask`, `--island-mask`, and
`--reference-mask`) are JSON with `size: [width,height]` and a flat boolean `pixels`
array in Blender's bottom-up order. Protected pixels are compared exactly as Blender
decoded RGBA against the same-size baseline; the protected selection must be nonempty.
The island tone metric is the maximum absolute channel difference between the
encoded-sRGB median of the island and reference selections. Both masks must select
nonempty finite samples, and this painted-skin tolerance is single-subject.
`--composite-atlas` explicitly enables the W × 9W/8 layout check; without it the
check remains unmeasured. `--resolution-baseline-blend` or
`--resolution-baseline-glb` supplies a second, differently sized atlas for normalized
UV comparison, separate from the same-size pixel baseline.
A `region:<id>` vertex group is a neutral mask; `join-boundary` identifies
vertices whose internal edges are checked; `face-reference` identifies corresponding
face vertices for the position comparison. `--hair-prefix` explicitly declares hair
and selects hair bones by name; `--hair-absent` declares the chain check inapplicable.
Neither flag means hair was visually inspected. Multiple `--stage` flags select checks;
without them all stages are selected. For required checks the gate returns 0 when all
pass, 1 for any failure, or 2 for unmeasured/unusable evidence. Advisory results do not
change the exit code. A forbidden region is a failure and is named. A missing or
non-finite value, missing method/source, or wrong type or unit is never a pass.

Evidence uses `skin-body-evidence/1` with `subject`, optional `stage_scope`,
`declared`, and `measurements`; each metric has `value`, `unit`, `method`, and
`source`. SHA-256 compares each named source against its independently recorded
digest; it does not establish rights, exact changed-byte counts, or the integrity of
unpinned files. Baseline comparison only proceeds for matching mesh names, vertex
counts, polygon order and UV loop counts; it does not discover reliable correspondences
across topology changes or GLB vertex splitting. Browser material behaviour remains
unmeasured without independent job-specific evidence. For cross-resolution UV and
face checks it assumes the explicit corresponding indices are meaningful. It reads
only PNG IHDR bit depth,
compares Blender-decoded RGBA pixels, and reads direct image-to-base-colour links.
Export gaps in normal/roughness maps or browser SSS must be reported as
`unmeasured-by-export`, not as proof of presence. A full gate therefore may be
unmeasured even when the implemented structural checks pass.

These checks establish only the stated numeric and structural properties of the
selected artifacts, not likeness, visual quality, redistribution permission, skin
reflectance, collision, or browser subsurface scattering. Join-edge incidence is a
local boundary test, not a whole-body watertightness proof. Visual and rights review
remain independent decisions.

## Reference-relative checks, advisory ranges and stage fragments

Two related subjects cannot establish a population norm, and the historical Robin eye
detector selected sunglasses. Only reference-relative declared values are valid: the
advisory per-case ranges for heads-tall, shoulder, pose, density and UV sharing were
removed, and the target character's declared reference, baselines and limits are the
only thresholds. A `"severity": "advisory"` check still appears as `warn` on failure,
and missing evidence remains `unmeasured`. Both appear in `reasons` without changing
the gate status. Severity defaults to `required`.

For example, an evidence receipt can include:

```json
{
  "declared": {
    "references": {
      "eye_width": {"value": 0.12, "tolerance": 0.01, "source": "reviewed target reference"}
    },
    "baselines": {
      "deformation_error": {"value": 0.02, "factor": 1.1, "epsilon": 0.001, "source": "baseline measurement"}
    },
    "limits": {
      "root_drift": {"value": 0.03, "source": "project budget"}
    }
  },
  "measurements": {
    "eye_width": {"value": 0.125, "unit": "ratio", "method": "landmark measurement", "source": "target artifact"},
    "deformation_error": {"value": 0.022, "unit": "m", "method": "mesh comparison", "source": "target artifact"},
    "root_drift": {"value": 0.02, "unit": "m", "method": "trajectory comparison", "source": "target artifact"}
  }
}
```

With matching check units, `reference-within` normally passes when the absolute
difference from the declared reference is at most the positive finite tolerance.
An explicit `direction` makes it one-sided: `lower-is-better` accepts values at
most reference + tolerance, while `higher-is-better` accepts values at least
reference - tolerance.

`no-worse-than-baseline` defaults to `lower-is-better`: for a nonnegative baseline,
the value must be at most baseline × factor + epsilon. With `higher-is-better`, it
must be at least baseline / factor - epsilon. Factor defaults to 1 and must be
positive; epsilon defaults to 0. For negative baselines an explicit epsilon is
required, and factor is not applied: the upper or lower bound is baseline + epsilon
or baseline - epsilon respectively.

`declared-min` and `declared-max` compare against the inclusive project limit in
`declared.limits[metric] = {"value": ..., "source": ...}`. Missing or non-finite
limits and other missing or invalid declarations are unmeasured. Results include
`used` with the values actually applied. The example is an excerpt: a complete
receipt also needs the evidence schema and subject.

A metric containing `*` expands to the union of matching measurement names and
matching keys in declared references, baselines and limits. Each expanded metric
requires its own measurement and applicable declaration; a declared but missing
measurement is unmeasured. The check fails if any matching metric fails, otherwise
is unmeasured if any is unmeasured or none match, and passes only when all pass.
Its `detail` lists individual names and verdicts.

Repeat `--standards FILE` to merge explicit standards files. Stages sharing an ID
are combined and check IDs must be unique across all files. With no explicit files,
the gate loads `skin-body-standards.json` followed by sorted
`skin-body-standards.s*.json` fragments in the reference directory. Use
`--standards-dir DIR` to choose another directory for that default discovery;
`--stage` filters the merged stages.
