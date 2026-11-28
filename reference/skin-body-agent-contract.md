# Skin and body: agent authoring contract

This plugin ships standards, independent measurement and helpers, **not an automatic
photo-to-character converter**. A human must supply rights-cleared, editable body and donor head
(including hair if wanted) and atlas sources, their paths, SHA-256 hashes, permissions and
attribution. The human/coordinator chooses the target, measured references and applicable
single-subject checks; a rights note is a claim, not proof of rights. Synthetic examples in the
input file are not usable sources. Scope is head/face, neck, torso, abdomen/waist, arms, hands,
legs, feet, hair, skin texture, weights and neutral masks. No ship, sea, weather, props, clothing
or film work is in this contract.

Read [workflow](blender-agent-workflow.md), [route](blender-character-route.md),
[texture](skin-texture.md), [body parts](body-parts.md), [atlas](skin-atlas-authoring.md),
[head/hair](head-hair-authoring.md), [export parity](blender-export-parity.md),
[standards](skin-body-standards.md), [geometry](body-geometry-standards.md),
[rig/motion](rig-motion-standards.md) and [skin authoring](skin-authoring-from-reference.md).
The base standards and sorted stage fragments define check IDs, comparators, severity and
applicability. Missing required evidence is `unmeasured`, not a pass.

## Coordinator, ownership and dispatch

The coordinator decides scope, rights, frozen inputs, applicability and final acceptance. Spawn
configured implementer roles with explicit cwd, repository rules, read-only inputs with paths and
SHA-256, exact owned files, outputs, thresholds, prohibited edits and commands; use the generated
`brief` as the assignment. A scout can independently review source rights while separate workers
prepare isolated scripts/atlas components in distinct paths. **One main integration owner** alone
writes the master `.blend`; no concurrent writers to any one `.blend`. Independent workers write
only their own scripts, intermediate images or isolated component files, never the master. The
coordinator reviews and the integration owner incorporates components serially. No recursive
delegation and no worker self-approval. The verifier is independent and works after writers finish.

Dependencies: S1 precedes S2 and S9; S2 and S9 precede S2B; S2B precedes S3; S3 precedes
S4; S4 precedes S10 and S5; S9 and S10 also precede S5, whose weights are remeasured for
strain; S5 precedes S6, S6 precedes S7, and S10 precedes S11. S8 is last, after S6, S7 and S11.
Parallel research or isolated component preparation does not authorize integration before
dependencies are accepted. Every dependency artifact and hash is required, not merely the
previous task in the displayed order. A filtered plan retains external prerequisites in `dependsOn`.

Generate a plan (the example deliberately uses placeholders and synthetic hashes):

```sh
python3 tools/skin_body_plan.py --standards reference/skin-body-standards.json --character-plan examples/skin-body/plan.example.json --out /tmp/skin-body-plan.json
```

The author and measure commands in the plan call a Python containing bpy. Name it with
`--bpy-python /path/to/python`; without the option the plan uses
`$IMG2_HOME/runtime/character-bpy/bin/python` (`IMG2_HOME` defaults to `~/.img2`).

Input schema `skin-body-plan-input/1` requires `subjectId`, `sources` with `body`, `head` and
`atlas` entries each containing `path`, 64-hex `sha256`, and nonempty `rights`, `blendPath`,
`atlasNames` (nonempty list), `catalogueCharacterId`, `mirrorPairsFile`, `repairMaskFile`,
`outputDir`, and `regions`. The last field is limited to abdomen, waist-left/right,
cheek-left/right, face and hair. Additional sources also need hash and rights. Paths and hashes
are declarations, not checks of file existence, integrity, licence or artistic suitability. Replace
all sample paths, synthetic hashes and notes; supply the catalogue asset ID, actual image names,
mirror-pairs JSON and repair-mask JSON expected by the measurer. `--stages S2,S5` filters tasks;
the generator does not run any stage. `skin-body-agent-plan/1` includes role, owned files, inputs,
outputs, checks, commands, prohibitions, dependencies and paste-ready brief per task.

For selected S2B, S5, S9, S10 or S11, `declaredReferenceFile` is mandatory. The path names a
JSON file with a top-level `declared` object containing metric-keyed `references`, `baselines`
and `limits`, each entry carrying its source. The planner validates the path string, not the
file contents, permissions or scientific validity. Geometry additionally needs `referenceBlend`,
`landmarksFile`, `geometryRegionsFile`, `geometryMirrorFile`, `geometryBudgetFile`,
`atlasSize` and `joinBoundary`; S2B needs `skinRegionsFile`, `skinTargetsFile` and
`skinOptionsFile`; rig/hair need `armatureName`, `bodyObject`, `posesFile`, `chainsFile`,
`jointSectionsFile`, `faceGroup`, `restReferenceFile`, and S11 also `hairObject`.

## Declare-first rule

Before authoring, the **integration owner** records the target's reviewed landmark, tone,
UV-density and pose references and provenance, plus approved baselines and limits, in
`declared.references`, `declared.baselines` and `declared.limits`. Each reference gives value,
tolerance and source; baselines give value, factor/epsilon and source; limits give value and
source. Follow the exact comparator rules in [standards](skin-body-standards.md), including
one-sided direction, declared min/max and wildcard expansion: every matching region/pose needs
its own measurement and declaration. For reference-relative checks the gate compares the built
character to **that target's** predeclared values. No historical subject measurements or fixed
hair-chain layout are bundled. Generic required tolerances remain unchanged; caller-dependent
tone, material, rig and export checks need actual declarations/evidence and remain open if missing.
The plan requires `catalogueFile` and `catalogueCharacterId`, forwards both into task inputs and
every skin/body measurement command, and never substitutes the synthetic primitive catalogue
for a missing real-input selection. Record advisory warnings without promoting them to evidence.

## Stage-specific work

For every row, inputs include the pinned sources and their hashes and the accepted prior-stage
artifact and hash; outputs also include runnable job-specific source, SHA-256 receipt and
independent evidence and verdict. Scripts and checkpoint names in the generated plan are job
outputs, **not pre-existing plugin scripts**. Each author writes the script for the stage and runs
it only on its owned copy. The verifier independently measures the produced artifact and gates it.

| Stage | Role and output | Required standards check IDs (see [JSON](skin-body-standards.json)) |
|---|---|---|
| S1 source/rights | Source-rights role writes admission script/receipt and an isolated source checkpoint; coordinator reviews permissions, original hashes and source identity. Inputs: rights-cleared body/head/atlas and hashes. | `source-hash`, `original-unchanged` |
| S2 skin texture | Skin author writes atlas recipe and checkpoint from S1 and repair mask. | `body-pixels`, `opaque`, `bit-depth`, `atlas-space`, `atlas-layout`, `repair-boundary`, `island-tone`, `uv-error`, `normalized-uv` |
| S9 geometry | Geometry author writes a separate component/checkpoint from S1; review actual topology, UV, landmarks and symmetry. | [S9 fragment](skin-body-standards.s9-geometry.json): `geometry-landmarks`, `geometry-pose`, `geometry-mirror-coverage`, `geometry-nonmanifold`, `geometry-uv-overlap`, and other listed checks |
| S2B reference skin | Skin author writes the neutral atlas after S2 and S9, using target patches and explicit region mappings. | [S2B fragment](skin-body-standards.s2b-skin-authoring.json): `s2b-tone-rgb`, `s2b-tone-lstar`, `s2b-density`, `s2b-padding`, `s2b-support` and other listed checks |
| S3 head/neck | Integration owner joins after S2B, preserving donor correspondence; local join is not whole-body watertightness. | `join-open`, `join-nonmanifold`, `join-edges`, `join-triangles`, `face-position` |
| S4 skeleton/body parts | Rig author writes a separate rig component/checkpoint from S3 and the selected catalogue; integration owner incorporates it. | `bone-groups`, `bone-count`, `hair-chains` (conditional on declaration) |
| S10 rig/pose | Rig author writes a separate component and samples declared poses and joint sections; verifier gates reference-relative and baseline checks. | [S10 fragment](skin-body-standards.s10-rig.json): `rig-joint-section`, `rig-rest-mirror`, `rig-strain-p99`, `rig-strain-p01`, `rig-rebase`, `rig-loop-angle`, `rig-loop-root` and other listed checks |
| S5 skin weights | Weights author writes separate recipe/checkpoint from S4, S9 and S10; verifier checks mirrored pairs and repeats S10 rig/strain measurements on the actual S5 output. | `weight-sum`, `influences`, `small-weights`, `mirror-difference`, `mirror-unmatched`, `mirror-mapping`, plus S10 checks |
| S6 neutral masks | Integration owner writes mask recipe/checkpoint from S5 and explicit subject-derived eligibility and region ids. Do not reuse another subject's coordinates. | `neutral-regions`, `mask-min`, `mask-max`, `mask-sum` |
| S7 material | Integration owner writes material recipe/checkpoint from S6, atlas name and texture hashes. Distinguish native material from actually exported maps and scattering. | `material-space`, `roughness`, `metallic`, `export-maps` |
| S11 hair | Hair author writes a separate component/checkpoint after S10; verifier checks fit and pose samples against target baselines. | [S11 fragment](skin-body-standards.s11-hair.json): `hair-contact-baseline`, `hair-root-drift`, `hair-exposed-scalp` and advisory checks |
| S8 export parity | Integration owner exports an isolated working copy and GLB from accepted S7; independent verifier compares native and GLB with matching assets and views. Retain the master. | `export-position`, `export-uv`, `export-weight`, `export-pixels` |

## Commands and evidence

Run from the plugin root, using the exact commands generated per task after replacing sample inputs.
For example, the following uses job paths from the input (`OUTPUT` here is illustrative):

```sh
B="${IMG2_HOME:-$HOME/.img2}/runtime/character-bpy/bin/python"   # any Python containing bpy
"$B" OUTPUT/s5_author.py
"$B" tools/bpy_measure_skin_body.py --blend OUTPUT/s5_artifact.blend --baseline-blend OUTPUT/s4_artifact.blend --catalogue reference/body-parts.json --character ASSET_ID --atlas ATLAS_NAME --mirror-pairs INPUT/mirror-pairs.json --out OUTPUT/s5_evidence.json
python3 tools/gate_skin_body.py --evidence OUTPUT/s5_evidence.json --stage S5 --json > OUTPUT/s5_verdict.json
```

The extended stages use their own read-only measurers. These commands use illustrative names;
the generated task supplies the full concrete paths and a following command to merge the
predeclared `declaredReferenceFile` into the raw receipt without changing measured values:

```sh
"$B" tools/bpy_measure_geometry.py --blend OUTPUT/s9_artifact.blend --reference INPUT/reference.blend --landmarks INPUT/landmarks.json --regions INPUT/geometry-regions.json --mirror INPUT/geometry-mirror.json --join-boundary join-boundary --atlas-size 2048x1024 --budget INPUT/geometry-budget.json --out OUTPUT/s9_raw_evidence.json
"$B" tools/bpy_measure_skin_authoring.py --blend OUTPUT/s2b_artifact.blend --atlas ATLAS_NAME --regions INPUT/skin-regions.json --targets INPUT/skin-targets.json --options INPUT/skin-options.json --baseline-blend OUTPUT/s2_artifact.blend --subject SUBJECT_ID --out OUTPUT/s2b_raw_evidence.json
"$B" tools/bpy_measure_rig_motion.py --blend OUTPUT/s10_artifact.blend --armature Armature --body Body --poses INPUT/poses.json --chains INPUT/chains.json --joint-sections INPUT/joint-sections.json --face-ids face-reference --rest-reference INPUT/rest-reference.json --out OUTPUT/s10_raw_evidence.json
"$B" tools/bpy_measure_rig_motion.py --blend OUTPUT/s11_artifact.blend --armature Armature --body Body --poses INPUT/poses.json --chains INPUT/chains.json --joint-sections INPUT/joint-sections.json --face-ids face-reference --rest-reference INPUT/rest-reference.json --hair Hair --out OUTPUT/s11_raw_evidence.json
python3 tools/gate_skin_body.py --evidence OUTPUT/s9_evidence.json --stage S9 --json > OUTPUT/s9_verdict.json
```

With no `--standards`, the gate merges the default base and all sorted sibling
`skin-body-standards.s*.json` fragments. If explicit files are used, repeat `--standards` for
every base and fragment; a single explicit base alone excludes the fragments. The planner's
gate command supplies exactly the files it loaded. S5 also gates S10 against the post-weight
artifact, not merely the earlier rig. Paths for the prior references, region selections,
mirror mapping, sampled poses, chain definitions and joint-section contours are job inputs,
not supplied by the plugin. Their detailed schemas are in the linked measurer guides.

Geometry uses explicit polygon regions, same-pose landmarks, a mirror plane and project budgets;
its finite raster misses subpixel overlap and does not establish pose self-intersection or
continuous UV/filter behaviour. Skin uses selected neutral UV triangles, patches, targets,
transition/support and declared pairs; it cannot establish physical albedo, automatic seam
correspondence, pores or visual fidelity. Rig section measurements omit ambiguous/open contours;
rebase compares supplied world-delta samples, not independently extracted before/after clips.
Loops measure only endpoint bones and root, not velocity or vertex seams. Scalp rays are
caller-supplied samples, not a texture-to-surface rasterizer; open-body inside tests are
indeterminate, and continuous collision is unmeasured. Visual inspection remains mandatory.

Use `s1_author.py` through `s8_author.py` respectively for the other author stages, each with its
own `sN_artifact.blend` and `sN_evidence.json` / `sN_verdict.json`; S8 instead measures the actual
`character.glb` with `--glb OUTPUT/character.glb --baseline-blend OUTPUT/s7_artifact.blend`.
For S4, the verifier supplies `--hair-prefix PREFIX` when the selected hair chain is declared,
or `--hair-absent` when explicitly absent; without a declaration the conditional check remains open.
For S2 the generated command uses S1 as baseline and the repair-mask JSON; its image sizes and
pixel order must match. The measurer cannot establish every listed metric: missing observations
remain open even when an artifact was authored. Never fill gaps with invented measurements.
Use the generated task's commands to avoid inventing a measurer flag. The author script is written
by the assigned agent, not supplied by the plugin. The author may import pure helpers from job
scripts, for example `from tools import skin_texture, body_parts, atlas_surface, head_transplant,
hair_chain_rig`; these are APIs, not automatic authoring CLIs. Run a pure helper script with
`python3 JOB/helper.py` when it only imports those helpers; use the bpy Python above for scripts
that import `bpy`. The coordinator or verifier runs gate and integrated checks after writers finish;
a worker may run only explicitly authorized focused reproductions.

The measurer emits `skin-body-evidence/1`: `subject`, `measurements` mapping metric to
`{value, unit, method, source}`, and `declared`. Preserve the original JSON and gate JSON; do not
substitute hand-authored values for measured facts. A stage handoff additionally records source,
script, artifact and evidence paths plus SHA-256, upstream accepted hashes, exact commands,
selected check IDs, verdicts, applicability, limitations, and open failures/unmeasured items.
Record rights evidence separately: measurable source hash alone does not establish permission.
The gate exits 0 when selected applicable **required** checks pass, 1 for required failure,
2 for required unmeasured or unusable evidence. Advisory failure is `warn` and advisory
unmeasured is reported but neither changes the status. A successful script, visual impression,
or attempted measurement is not a pass.
The native-to-GLB gate is not browser appearance, skin scattering, likeness or collision evidence;
record those separately as open unless independently measured.

## Prohibitions, correction and completion

Never overwrite a pinned source; never re-freeze geometry or relax thresholds to make a check pass;
never recolour globally to hide a geometry defect; never create chest, hip or buttock regions; no
neural mesh generation unless the user explicitly opts in; never claim a check you did not run.
Do not silently replace missing sources, licences or measurements with guessed values. Do not infer
browser SSS or pores from a native material. Do not upload or spend credits without authorization.

Repair one causal group per round, then independently remeasure that group and invalidated downstream
checks. Default budget is three focused correction rounds per stage and six total, stopping earlier
on a repeated failure/plateau. Escalate the exact blocker and remaining evidence when the cap is
reached, rights are unavailable or a required tool/source is missing; do not change methods or
thresholds to hide the failure. Done means **all selected applicable required checks pass**,
independent verification and required stage handoffs exist. List every `unmeasured` check as
open: required unmeasured prevents completion; advisory unmeasured is not a pass but does not
change the gate status.
