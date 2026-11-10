# Skin and body parts — distilled from the Robin case

Scope: **skin (da) texture, skin weights/masks and the body parts of Robin**. Nothing about the ship, sea, weather,
props, clothing/cloth solving or film tooling is taken from the showcase; those stay in the job. The plugin is for characters.

Every rule carries the case that produced it. Numbers are tagged **single-subject** (measured on one rig/atlas, a starting
value) or **behaviour** (a mechanism that holds across subjects). Citations are job paths (`J` =
`~/.img2/jobs/robin-bikini-transfer-01`). This file records what was read and exercised there; it does not re-verify it.
Rights are the sources': the base body is a third-party asset whose licence and attribution terms are in the job's `ATTRIBUTION.txt`; the donor head's creator and
licence are **not established**; franchise rights remain with their owners. The plugin ships formulas and code, never
images, and asserts no redistribution permission.

## Where each piece lives

| piece | module | doc |
|---|---|---|
| **skin texture pipeline** (classify, measure tone, fill, details, composite, pack, material) | `tools/skin_texture.py`, `tools/atlas_surface.py` | `skin-texture.md`, `skin-atlas-authoring.md` |
| body parts catalogue, neutral masks, mirrored-weight symmetry | `tools/body_parts.py`, `reference/body-parts.json` | `body-parts.md` |
| head/neck join, cheek masks, hair chains and motion | `tools/head_transplant.py`, `tools/hair_chain_rig.py`, `tools/bake_hair_motion.py` | `head-hair-authoring.md` |
| skinning weights from the solid | `tools/rig_geodesic_skinning.py`, `tools/rig_skin_conditioning.py` (existing) | `blender-rig-interaction.md` |
| soft-region preparation and runtime (existing route) | `tools/prepare_softbody.py`, `runtime/softbody.mjs` | `softbody-character-route.md` |
| standards (S1–S8), bpy measurer, gate, agent contract and plan generator | `reference/skin-body-standards.json`, `tools/bpy_measure_skin_body.py`, `tools/gate_skin_body.py`, `tools/skin_body_plan.py` | `skin-body-standards.md`, `skin-body-agent-contract.md` |

## The pipeline, in the order a builder meets it
1. **Admit the source with its rights** (body atlas, donor head). Record hashes; never modify the original.
2. **Author/transplant the body parts** (head, neck, hair, feet) preserving protected correspondence.
3. **Skin texture** — classify UV regions, measure tones, correct, add details, composite, pack, verify (`skin-texture.md`).
4. **Skin weights** — inherit, repair along the welded mesh, mirror-check; masks for neutral regions only (`body-parts.md`).
5. **Skin material** — Principled values, and an honest list of what the export does not carry.
6. **Verify in the exported file**, not in the authoring session: pixel parity, UV parity, weight parity, join manifold report.

## Rules and their cases

### Skin texture
1. **Measure the tone you match; do not eyeball it.** Case: the source painted the leg/hip islands darker with pale streaks; exposed,
   they read as blocky patches. Per-channel **encoded-sRGB median** of torso samples was used as the fill: leg median
   `[.94118,.74902,.63137]` → `[.98824,.85098,.75686]`, 19,383 pixels filled, 1,704 original pixels had deviated > .08 from the median
   (`J/evidence/head-report.json:315-330`; history `robin-transfer-9-before-donor-head/native/build_head.py:339-384`) — single-subject.
2. **Say which colour space a statistic lives in.** The historical edits work on stored (encoded) sRGB with encoded-channel
   luminance `.2126R+.7152G+.0722B`; the neck bridge blends in **linear light**. Mixing them silently shifts tones; the tools name
   the space in the call (`measure_tone(..., color_space=...)`) and a test proves the two answers differ — behaviour.
3. **A repair may change nothing outside its mask, and the file proves it.** Case: nape shadow was source pigment, not live shading.
   Projection onto the colour line shadow `[231,173,141]` → skin `[246,203,177]` changed 26,687 pixels with 0 outside and untouched
   error 0.0 (`J/evidence/nape-08-blue-native.json:9-41`) — single-subject numbers, behaviour mechanism.
4. **Neck shading is lifted, not erased.** `gain = referenceMedian / max(neckMedian,.001)` on dark samples only, dilate 2, blur 6,
   darkness gate smoothstep .75–.88 at strength .7: neck median `[.90588,.68235,.55686]` + gain `[1.09091,1.24713,1.36620]`
   → `[.96353,.80039,.69961]` (`J/evidence/head-report.json:332-355`) — single-subject.
5. **Old paint is selected from the ORIGINAL pixels and intersected with where paint can be.** Case: the root-paint repair uses the pinned
   original image (orange ordering R>G>B + saturation smoothsteps) ∩ rasterised eligible triangles, extended 8 px, 400 harmonic-fill
   iterations; it never darkens natural skin. The legacy fill used `np.roll`, which **wraps across image edges** — the tool has a
   bounded mode (`hairline_atlas.py:23-112`).
6. **Composite atlas = W × 9W/8:** original body bottom 4/9 (bytes exact), donor face + neck middle 4/9, bridge strip top 1/9; body UV
   `(u,4v/9)`, face `(u/2,4/9+4v/9)`, neck `(u/2+.5,4/9+4v/9)`. Strip padding `4W/2048` so normalised UVs are identical at 2048 and
   4096 (blue/violet 2048×2304, Halloween 4096×4608) — behaviour.
7. **Preserve the donor's tone.** Case: the donor face is tan against the pale body; the answer was a bridge, not a global recolour.
   The step at the neck was a **geometry** defect (donor neck 2.6–2.7 cm rearward with a hidden flare), fixed by rigid alignment and
   clipping — never by colour (`J/README.md:110-113`).
8. **Pack the saved bytes, then reload and compare.** Case: packing alone retained stale pixels, so the transplant writes the PNG,
   packs the file bytes, reloads and compares; a changed original region raises (`transplant_head.py:411-430,447-469,795-803`).
9. **Iris variants are pigment-selected.** Halloween amber: `sat>.2, max>.08, B>1.1R, G>1.02R` → `[max, min+(max−min)·h/60, min]`, h = 42°;
   8,491 pigment pixels changed, 7,893 protected (`J/evidence/head-10-halloween-native.json:475-500`). Blue/violet keep the donor iris. A
   UV-covered count (5,997 texels) is a different domain from the full-map count — never quote one for the other.
10. **Skin material values are artist-painted shading, not measured skin.** metallic 0, roughness .5, IOR 1.4, subsurface .08,
    radius (1,.45,.2), scale .002 m; face-detail roughness .35 (`build_head.py:430-461`) —
    single-subject. The exported asset had **no skin normal/roughness map and no browser SSS**; native scattering is not exported.
    No pores or scan-derived micro-detail were ever authored; the pipeline reports that as `unmeasured`, not as present.

### Body parts and weights
11. **Parts are catalogued per asset and per stage.** Robin's full rig has 80 bones; the preserved head component has 28 (24 hair
    bones). A control-only rig and a full anatomical rig are not interchangeable counts.
12. **Hair is a head part with its own chain rule:** 5 rear chains × 4 bones + 2 face chains × 2 = 24; roots pinned at Z 1.63 m, blend
    .05 m; 1,367 Head-only vertices, 3,371 length-chain bound; seam vertices share weights. No collision solver: 236 approved
    rest hair-inside-body samples remain (`J/evidence/rig-11-acceptance.json:72-87`).
13. **Inherit weights where positions match; transfer side-aware where they do not.** Keep the strongest 4 and renormalise.
    Matching positions do **not** imply matching UVs: compare UV loops separately.
14. **Mirror-check, with the pairing stated.** On 681 foot pairs the max mirrored weight difference fell 0.535104 → 1.99676e-6 and the
    posed mirror distance 0.0507933 → 1.10521e-6 m — a foot-pair result, not a body guarantee.
15. **Landmarks must be set from sections, not copied.** Case: the first lower rig put the knee at .47475 m (in the calf) against a
    section constriction of .60–.62 m; ankles differed 37.42 mm. Copying local quaternion curves after a rest-frame change gave
    0.596454 rad world error; the corrected mapping 2.27e-7 rad.
16. **Redistribute lower-chain weight continuously per side.** The first aligned skinning left a triangle stretched 17.1182× in a sampled
    jump; continuous per-side redistribution gave 1.009584×. Asymmetric graph smoothing of differently triangulated feet was rejected.
17. **Protect the join.** Donor neck cut 1.555 m, body cut 1.515 m, bridge 96 triangles / 192 edges / 0 open or non-manifold join edges
    at 1 µm. That is a local proof, not whole-character watertightness. Bare feet stayed separate objects with 132 zipper triangles
    (max gap 6.59e-8 m); an earlier separate foot shell was rejected for an exposed junction.
18. **Neutral regions only.** Soft-region masks and demonstrations use abdomen, waist, cheek/face, hair. Mask: `q=Σ((p−c)/r)²`,
    `u=max(0,1−q)`, `w=u³(10−15u+6u²)`, divided by `max(1,Σw)`, coordinates (x,y,z)→(x,z,−y). Cheek centres are **derived per head**
    (`cx=1.30·eye_x`, …, ≥ 8 active vertices) — never transplanted from another character. Runtime profiles are artistic modes
    (abdomen 2.8 Hz/.30/.014/.06/.008, waist 5/.6/.006/.10/absent, cheek 4.5/.80/.0025/0/−.0012), and **absent ≠ 0**.
    `tools/body_parts.py` refuses region ids outside the neutral allowlist.
19. **Quaternion sign continuity is part of the export.** Antipodal consecutive quaternion pairs are removed by hemisphere
    alignment without touching geometry or weights; do not infer animation correctness from that alone.

## Not established (do not claim)
Skin reflectance, pores, browser subsurface, de-lit albedo, hair or foot collision, likeness, phone performance, and any redistribution
right for the donor head or franchise characters.
