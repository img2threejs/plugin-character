# Body parts, skin texture and weights

`body-parts.json` is a selected, versioned case catalogue, not a universal skeleton. `tools/body_parts.py` is a pure NumPy supplement; it does not generate texture, install a rig, or establish likeness. Source references beginning `robin-bikini-transfer-01/` identify the local job. Numbers below are **single-subject** unless labelled **behaviour**.

## Identity, stages and parts

The body and feet derive from a third-party base body whose licence and attribution terms are recorded in the job's `ATTRIBUTION.txt`; franchise rights are not established. Robin's user-supplied donor head and hair have no established creator or licence, and no public redistribution permission is asserted. Robin's full rig has 80 bones; the preserved head component has 28 (four original controls and 24 hair bones). These are different stages, not interchangeable counts. [single-subject: `robin-bikini-transfer-01/ATTRIBUTION.txt:4-13,19-25`; `robin-bikini-transfer-01/README.md:101-115`; `robin-bikini-transfer-01/native/donor_hair_rig.py:3-4,61-62`]

The selected catalogue links head/face, neck, torso, abdomen and waist, arms and hands, legs and feet, and hair to mesh components and representative bones. Fingers and toes are represented in the anatomical skeleton by bilateral finger chains and toe bases/end markers; the catalogue does not pretend its representative bone list is exhaustive. The central chain includes Root, Pelvis, Spine, Spine1/Spine2, Neck and Head; bilateral groups include Shoulder, Arm, ForeArm, Hand, five three-segment finger chains, UpLeg, Leg, Foot, ToeBase, and Robin toe end markers. A control-only rig has no individual finger or limb articulation. [behaviour: `robin-bikini-transfer-01/native/pinoc/repair_actor_skinning.py:61-65`]

Native coordinates are metres, +Z up, front −Y and anatomical left +X; glTF coordinates are `(x,z,-y)`, Y up and front +Z. Null parents in a selected inventory do not prove a root relationship. Explicit absent and unknown are distinct. [behaviour: `robin-bikini-transfer-01/native/pinoc/anatomy-landmarks.json:2-4`]

## Measurements and limits

- Robin donor crown Z 1.756543 m, body cut 1.515 m, donor neck cut 1.555 m; bridge 96 triangles and 192 edges. The reported correspondence proof concerns the join, not whole-body watertightness. [single-subject: `robin-bikini-transfer-01/ATTRIBUTION.txt:25`; `robin-bikini-transfer-01/evidence/head-10-blue-fidelity.json:43-51`]
- Robin left knee `(0.0592548888, 0.0048793189, 0.61)`, ankle `(0.050327409, 0.0217984567, 0.14)`, toe base `(0.0527272541, -0.1445145681, 0.0393541567)` and toe end `(0.0548175201, -0.2312552109, 0.0568187721)` in native metres; right mirrors X. These are authored, section-informed targets, **not recovered source joints**. Knee half-transition is 0.35 of thigh length; ankle interval −0.06 to 0.04 m and toe interval −0.035 to 0.025 m along their axes. [single-subject: `robin-bikini-transfer-01/native/pinoc/anatomy-landmarks.json:3-18`; `robin-bikini-transfer-01/native/pinoc/repair_actor_skinning.py:61-88`]
- Hair has five rear four-bone chains and two face two-bone chains; Head binding pins at 1.63 m with a 0.05 m blend. Seam-coincident vertices share weights. [single-subject: `robin-bikini-transfer-01/native/donor_hair_rig.py:12-20,28-36`]
- The separate foot meshes and calf border were connected by 132 zipper triangles, with maximum bidirectional gap 6.59e−8 m; this is not a welded solid. [single-subject: `reference/robin-transfer-study.md:32-34`]

## Skin texture is required

Weights do not replace head identity or skin texture. Plan each target's actual UVs, identity, pixel provenance and rights. Painted features and shading are not measured skin reflectance; mirrored UVs constrain independent asymmetric detail. No normal map or browser scattering texture is established by an export unless it is verified in the exported file.

Use the existing `tools/atlas_surface.py`, `tools/head_transplant.py` and `reference/skin-atlas-authoring.md`: preserve original body pixels, place donor face and neck and reserve a bridge strip. For an opaque original W×W/2 atlas the composite is W×9W/8; body UV `(u,4v/9)`, face `(u/2,4/9+4v/9)`, neck `(u/2+1/2,4/9+4v/9)`. Decode sRGB to linear light for bridge interpolation, then encode and verify actual atlas pixels and export UVs independently. The cases use 2048×2304 and 4096×4608 composites. Donor licence remains unknown; no image is included in this catalogue. [behaviour: `reference/skin-atlas-authoring.md:3-7`; single-subject: `robin-bikini-transfer-01/README.md:112-113`]

## Weight authoring and neutral masks

Retain compatible inherited weights, protect donor correspondence and coincident boundaries; relax authored shoulder fields for 80 graph iterations and neck fields for 6, with protected boundaries. The lower-chain redistribution is continuous and preserves each side's incoming mass instead of separately relaxing asymmetrically triangulated feet. Transfer unmatched lower-leg points by nearest-surface barycentric interpolation with side-aware BVHs; propagate unmatched neck/head weights from matched boundaries and blend toward Head. Keep the strongest four weights, dropping values **below** 1e−4 and renormalizing. Position correspondence does not imply UV correspondence. [behaviour: `robin-bikini-transfer-01/native/pinoc/repair_actor_skinning.py:124-145,156-226`]

On 681 matched foot pairs the maximum mirrored weight discrepancy fell 0.535104 → 1.99676e−6, and posed mirrored distance 0.0507933 → 1.10521e−6 m. This is a foot-pair receipt, not a full-body guarantee. Sampled parity ambiguity (rest-position/UV matches that cannot be paired uniquely) is not a pass. [single-subject: `robin-bikini-transfer-01/evidence/anatomy-skinning-aligned-comparison-02.json:15343-15350,30691-30698`]

Neutral masks use glTF-frame ellipsoids (centre and radii in metres, calibrated to the bounding box of the mesh they were authored for): abdomen and waist regions bind Spine; cheeks bind Head and exclude nose and forehead. Centres and radii are source-bbox-calibrated, not general anatomy, and are not bundled; plan them from the target's own landmarks. Robin cheek masks derive from her own donor landmarks and eligible skin. [behaviour: `robin-bikini-transfer-01/native/transplant_head.py:644-675`]

For `q=Σ((p−c)/r)²`, `u=max(0,1−q)`, evaluate `w=u³(10−15u+6u²)` after converting axes; divide all active weights by `max(1,Σw)`. The optional predicate operates on the converted point. Runtime profiles `(frequency Hz, damping ratio, cap m, compression, pressDepth m)` are abdomen `(2.8,0.30,0.014,0.06,0.008)`, waist `(5,0.6,0.006,0.10,absent)`, cheek `(4.5,0.80,0.0025,0,-0.0012)`. **Absent is not zero**; these are artistic parameters, not biological constants. [behaviour: `tools/body_parts.py` `ellipsoid_mask_weight`, `normalize_masks`; single-subject: `robin-bikini-transfer-01/softbody.mjs:13-16`]

## Failure evidence

- The donor neck was 2.6–2.7 cm rearward and had a lower flare; rigid placement and clipping fixed geometry rather than recolouring the face. [single-subject: `robin-bikini-transfer-01/README.md:110-113`]
- The original knee at 0.47475 m lay in the calf, whereas section constriction was 0.60–0.62 m. The replacement is an authored target, not recovered anatomy. [single-subject: `robin-bikini-transfer-01/native/pinoc/anatomy-landmarks.json:12-17`]
- A sampled triangle stretched 17.1182×; continuous lower-chain redistribution reduced the same triangle to 1.009584×. Remaining deformation limitations still require inspection. [single-subject: `robin-bikini-transfer-01/evidence/anatomy-skinning-commands.json:40-49`]
- A separate overlapping foot shell was rejected; the later local zipper is not a whole-mesh weld. [single-subject: `reference/robin-transfer-study.md:32-34`]
