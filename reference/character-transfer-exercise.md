# Prove construction knowledge on a second character

Use after `character-construction-prior.md`, before native authoring a new identity.
A successful extractor is not a successful character. Use the existing native route and job plan.

## Record the transfer before editing

In `character-plan.json`, write source hashes, adopted construction principles, target references,
observed landmarks, inferred depth, pose/camera, material style and per-feature acceptance criteria.
If adapting an admitted base, say so before building. Preserve its licence and original bytes.
Do not call a recolour an independently reconstructed character. Separate deliberate body similarity
from identity-specific head, eyes, nose, mouth, hair, accessories and outfit choices.

## Accept a construction reference before authoring

For a standing character, first show and inspect a full-body neutral A-pose or near-A-pose.
Prefer front, side and rear views at a consistent scale. Verify that clothing and hair do not
hide the anatomy or garment boundaries being evaluated. A seated swimsuit image and an angled
portrait can establish identity/palette, but cannot validate standing silhouette or proportions.
Do not start shape authoring on that basis and plan to solve the reference mismatch later.
If only clothed A-pose views exist, disclose the hidden regions and get the user's decision on
an adapted bikini design versus waiting for an adequate bikini reference. A reference model's
render is visual evidence only, not permission to download/adapt its geometry or textures.

If a suitable pose image cannot be found, an explicitly labelled AI-authored design sheet can
become the target rather than inventing geometry from an incompatible seated photograph.
Use an authorized image-generation tool; disclose its current cost and visibility before creating.
Request the adult character, exact outfit, full-body front/profile/back, neutral A-pose, aligned
head/ground levels, plain lighting and unobstructed garment boundaries. Save the request and
operation ID; recover that operation instead of issuing an automatic paid retry.
Inspect the completed image itself for view-scale, anatomy, outfit and occlusion inconsistencies,
show it to the user, and resolve design acceptance before resuming geometry. Record uncertain or
hidden connections and merged fingers. Aligned views do not prove one exact orthographic volume.

## Make geometry controllable

Write job-local bpy recipes with explicit parameters separate from mesh operations. Parameterize
head width/length, jaw/chin, orbit/eye proportions, nose profile and mouth placement. Record the
vertices/regions each control affects; modify connected surfaces, not detached facial lumps.
Preserve protected regions and smooth transitions. Keep anatomical and display dimensions distinct.
Changes to geometry invalidate dependent UV, weights, masks and clearance; regenerate them together.
Removing source clothes or footwear changes what must be continuous and painted. Inspect newly
exposed skin in clay/albedo before freezing it; declare localized topology exceptions instead of
claiming global source preservation. See the measured ankle/atlas case in `robin-transfer-study.md`.
Choose SIMPLE only to increase sampling density after shape acceptance, never to repair anatomy.

Imported skin can be visually continuous but split at UV/material seams. Before restricting a
fitted garment to one raw connected component, measure where that component actually ends.
If it ends at a seam, weld only a construction copy at a measured coincidence tolerance; keep the
admitted Body unchanged. Rebuild the construction fields against the copy's actual indices.
Replay the contour and measure its residual before blaming interpolation or snapping.

## Close the visual correction loop

1. Lock camera, viewport, lighting and pose. Save front/quarter/profile/rear and face views.
2. Compare reference-visible landmarks and silhouette. Record measured image coordinates, uncertain
   points and residuals. Do not compare raw image pixels across different poses as a likeness score.
3. Classify a defect as camera/pose, macro shape, local shape, UV/paint, material or runtime.
4. Change one causal parameter group. Rebuild from the saved source; retain before/after evidence.
5. Compare the same views. Keep a change only when the target criterion improves without breaking
   others. Follow the native route's bounded correction policy; a plateau is not a pass.

## Paint for this character

Build/repaint target-specific eyes, brows, lips and skin features into matching UVs. A compatible
base texture may be adapted with attribution, but its original identity marks must not leak through.
Record whether the style intentionally includes painted shading; do not label it de-lit PBR.
Inspect albedo-only, clay, normal-off and beauty controls to separate geometry from paint and lighting.
New hair needs scalp/root coverage, silhouette and back volume, not only a colour change.

For scanned fabric, verify source rights, physical tile units and colour/data roles before baking.
Measure texel density and UV Jacobian distortion; increasing atlas size does not repair a squeezed
UV chart. In native unwrap/average/pack scripts, explicitly select UV loops as well as mesh elements
and check operator completion. Preserve intended panel cuts; do not turn every new UV seam into
painted trim. Record per-panel physical scale, filtering and unresolved warp/weft direction.
Keep dye separate from source luminance, normals and roughness; a stretch-labelled scan supplies
no elastic modulus. Verify actual GLB image-channel parity, then inspect a close-up normal-off/beauty
pair on the same geometry. Runtime folding must be repaired and measured on the rendered mesh,
not concealed by grain, lighting or a smaller effective grip.

## Verify what transfers

Run the construction extractor on both admitted source and new GLB with explicit body selection.
Compare normalized proportions, density, UV allocation and clearance using the same definitions.
Distinguish purposeful similarity (e.g. requested body ratios) from unchanged source identity.
Inspect the actual browser artifact with posed picking, real mouse/touch, hold/release, rebound and
reset. Isolate each case's event history; API combinations are not trusted pointer evidence.
Run independent probes with conservative posed-world bounds and test their geometric counter-examples.
Wait for natural spring sleep before exact-rest comparison; do not reset away remaining motion.
Nearest-normal signs are not volume membership around concave/open surfaces; retain raw flags and
confirm ambiguous cases geometrically. Sampled clearance never proves arbitrary-motion collision.
For different garment topology, re-derive anchors/classification and verify all claimed cases;
do not call a source-specific garment gate universal. Test articulated limbs/faces only if authored.

## Evidence and promotion

Save `.blend`, recipes, parameters, references/rights, GLB/sidecar hashes, measurement reports,
fixed-view captures and actual pass/fail/unmeasured outcomes in the job. Declare browser/device.
Record repair rounds and which construction lessons held or failed on the second identity.
Promote only observed successful recipes into the skill; retain failures as bounded counter-examples.
Do not claim generalization from one transfer case, or claim new likeness from unit-test totals.

Measured transfer, failures, corrected probe regressions and bounded results: [Robin case study](robin-transfer-study.md).
