# Garment acceptance

Acceptance checklist for route `garment-character` (`garment-character-route.md`). Every item is
measurable: a number the delivered build achieved, the command that measures it, and the
counter-example that **must fail** (a check that cannot fail proves nothing).

Source of every number: the delivered job `~/.img2/jobs/nami-sketchfab-8e496e5a` (JOB), files named per
item. `PLUGIN` = `~/.img2/plugins/character`. A number that could not be traced says `unverified`.
The numbers are results on **one asset** (a licensed Sketchfab model adapted in Blender, see route
section 0), in headless Chromium on one recorded host, with touch as emulation. They are the bar for a
replay on that asset and a reference for another one, not a promise of the same result from images.

Item ids `A1`–`A13` are the ones the route document cites. "Gate" = `tools/gate_garment.py`; it judges
recorded files and never measures (an unrecorded value is `unmeasured`, never `pass`).

## A1. One connected surface

- Delivered: BikiniTop **3351** vertices, **1** connected component; cup 999 each, ribbon 262 each, neck
  loop 299, under band 530 (`evidence/connected-interaction.json` `connectedChain.structure`; the same
  counts in `reference-analysis.json` `connectedGarment.verification.structure`).
- Measure: the weld graph of `garment-field.mjs buildGraph` over the garment mesh; count components and
  per-part vertices (`garment.mjs` builds this graph from the seam-welded vertex ids).
- Must fail: a garment whose loop or band is a separate mesh. The pre-field build is the recorded case: a
  ribbon pull moved the neck loop **0 mm** (`connectedChain.before.ribbonPull.neckLoopMovedMm`).

## A2. Pull reach, computed from the garment

- Delivered: ribbon pull reach **393.5 mm** = `STRAP_FIELD.reachFactor` 1.55 × the surface distance to the
  mirror point on the other ribbon (about 254 mm); **2598 of 3351** vertices carry weight; neck loop mean
  influence 0.74; under band 0. Cup pull: the nearest 50 % (`PULL_PATCH.share`), reach **216.1 mm**,
  `reachCount` **1675** of 3351; neck loop 0 (`connected-interaction.json` `connectedChain.reach`).
- Measure: `namiStudio.garments.getState().straps[i].reach` (m) and `.panels[i].reachCount`;
  `namiStudio.garments.influence('strap'|'panel', side)` for per-vertex weights. Tests: `garment.test.mjs`
  "how far a ribbon pull reaches is computed from the garment" and "a cup pull carries the nearest half of
  ALL garment vertices, and nothing beyond it moves".
- Note: `reach.cupPull.verticesInfluenced` is **1338** in the same evidence while `reachCount` is 1675. The
  1338 is the count of non-zero weights from `influence()`, which includes the pin fade toward the band;
  that reading is an `[INFERENCE]`.
- Must fail: reach typed in as a constant, or measured through the air instead of along the surface (the
  test fixtures compare against the along-surface distance). Conflict: `delivery-manifest.json`
  `pullPatch.reachMm` says **178.2** for the cup while the evidence file and `reference-analysis.json` say
  216.1; JOB's evidence is used here, 178.2 is **unverified / stale**.

## A3. Continuity of displacement along the garment (25.7 mm ribbon pull, left ribbon, desktop, trusted mouse)

- Delivered mean displacement (mm): neck loop **12.3** (max 14.3), pulled ribbon **17.6** (21.6), other ribbon
  **5.4** (10.4), pulled cup **10.8** (18.0), other cup **1.5** (5.8), under band **0**
  (`connected-interaction.json` `matrix.desktop[0].displacement`; `ATTRIBUTION.txt`). Cup pull (its pull
  size is not stated): cup 9.2 mm mean (12.4 max), ribbon above it 4.1 (7.9), loop 0, other cup 0.1
  (`ATTRIBUTION.txt`).
  Touch (emulated): loop 19.0, ribbon 25.6, cup 15.9 at a 30.7 mm pull.
- Measure: displacement of each part's vertices against rest after `grabStrap`/`dragStrap` through trusted
  input; part membership from the strap and cup attributes.
- Must fail: a part that does not move with its neighbour. Ordering `pulled ribbon > loop > other ribbon > 0`
  is asserted by the "pulling one ribbon carries the whole chain" test; the before-build recorded the loop
  at 0 and the other cup at 0.

## A4. Nothing tears at a junction

- Delivered: worst edge stretch across a junction between parts **1.31x desktop / 1.27x touch** (ribbon pull;
  cup pull 1.09 / 1.11); edges past 2.5x: **1** desktop and up to **7** touch of **9540** edges
  (`pullsDesktop`, `pullsTouch`, `matrix.*[].edgesOver2_5x`).
- Measure: per edge, live length over rest length, reported as the maximum across a junction between two
  parts, the number of edges past 2x and 2.5x, and the edge count. The recorded fields are `edges`,
  `edgesOver2x`, `edgesOver2_5x`, `worstJunctionStretch`, `worstJunction`; JOB's recorder script is not in
  the job, so the grouping rule is `[INFERENCE]` from those field names.
- Must fail: the earlier build, which recorded **14.4x** at ribbon|cup (21 of 21 edges over 2x) and **7.4x**
  at cup|band (`connectedChain.before.ribbonPull.worstJunctions`), and 4.5x for a cup pull.
- Unverified: `ATTRIBUTION.txt` says the one desktop edge past 2.5x is in the neck loop; the evidence file
  records only the worst junction name (`neck loop | ribbon (pulled)`), not the location of that edge.

## A5. Flipped triangles are counted, not hidden

- Delivered: ribbon pull **15** (desktop) / **41** (touch) flipped triangles; cup pull **2 / 11**
  (`pullsDesktop[].flippedTriangles`, `pullsTouch[]`). JOB sets **no pass/fail limit** on this number, so none
  is invented here: report the count, do not claim zero.
- Denominator, **unverified**: `reference-analysis.json` and `ATTRIBUTION.txt` write "of 3730"; the matrix
  records say `triangles: 6192`, and the exported BikiniTop primitive has 6192 triangles (read from
  `native/export/character.glb`). Quote the count and the recorded `triangles` field, not the 3730.
- Measure: read `flippedTriangles` and `triangles` from the matrix records. How JOB's recorder decides that a
  triangle is flipped is **not recorded** (unverified), so a replay must state its own definition.
- Must fail: a report that omits the count or its definition.

## A6. Exact release

- Delivered: after release every vertex returns to rest, **render mismatch 0** in all **16** matrix runs
  (8 desktop + 8 touch, both outfits; `matrix.*[].afterRelease.renderMismatch`, `stillGrabbed: false`);
  `exactRestMismatchesAfterRelease: 0` in `delivery-manifest.json`.
- Measure: after release plus settling, compare the rendered garment positions with a fresh rest pose.
- Gate: **G5**. Must fail: any `renderMismatch != 0` or a case still grabbed (`test_release_mismatch_or_still_grabbed_fails_g5`);
  with no release records at all G5 is `unmeasured`, not pass (pass `connected-interaction.json` as a
  `--matrix`).

## A7. Real input, whole matrix, hard pulls

- Delivered: pulls driven by **trusted** pointer/touch events (CDP `Input.dispatchMouseEvent` /
  `dispatchTouchEvent`), not API calls: 48 desktop mouse cases, 16 touch, 16 tissue grab/squeeze, plus 13
  API-driven combos (7 of them two-handed). Pull distance: ribbon 25.92–34.05 mm and cup 23.5–23.83 mm on
  desktop; up to 35 mm (touch/combos). Both outfits for the left ribbon and left cup.
- Gate required cells (**G2**), all must be present and trusted: each kind (ribbon, cup) × each side × the 8
  angles 0/45/…/315 by mouse; the **left** ribbon and the **left** cup at all 8 angles in **2** outfits;
  per outfit and kind at least **4** touch angles; tissue **grab** and **squeeze** on both cups by mouse;
  at least **10** combos. A missing cell fails G2 by name.
- Gate **G4** (relative): every garment pull reaches at least 0.7 × its limit, limits read from
  `reference/garment-parameters.json` (`STRAP.maxPull` 0.035 m, `PANEL.maxPull` 0.024 m): ribbon ≥ 24.50 mm,
  cup ≥ 16.80 mm. Observed: 84 garment pulls pass. The 225°/315° directions stop short of the nominal limit
  because the pull stretches with resistance (`limitPull` tanh), hence a fraction, not the limit.
- Must fail: 12 mm pulls (`test_twelve_mm_ribbon_pulls_fail`), one missing angle
  (`test_one_missing_angle_fails_g2_and_names_it`), a left ribbon in one outfit only, API-only events.
- Also check, in the **default** view, not only the torso view: the ribbon is about 5 mm wide, so the
  viewer searches a small ring (`viewer.mjs strapNear`: mouse 4, 8 px; touch 5, 10, 15 px).

## A8. Outer-layer guarantee: the skin is never in front of the cloth

- Delivered: **0 inside-skin samples over 93 runs** (48 desktop mouse + 16 touch + 16 tissue + 13
  two-handed) at the pull limit, deepest **0 mm**; probe threshold 0.3 mm
  (`evidence/skin-guard-desktop.json` `summary`, `skin-guard-other.json` `summary`:
  `withAnyInside: 0`, `worstDeepestMm: 0`, `guardUnconverged: []`); 8 spot checks after the final tuning
  also 0, and 0 after release (`connected-interaction.json` `skinGuard.verification.spotChecks`).
- Measure: `tools/skin_probes.js` loaded into the viewer page: `await window.__inside({faces: true})`
  returns `{samples, insideSkin, deepestMm, byPart, examples}`. It takes every garment vertex and triangle
  centre, finds the nearest triangle of the **CPU-skinned** Body mesh and signs the distance by the outward
  normal; a sample is inside when it is more than **0.3 mm** under the skin. It is independent of
  `getState().skinGuard`. (It expects `namiStudio.modelMeshes` with meshes named `Body` and `BikiniTop` and
  resolves `three` through `__omp_import__` when that exists, else `import('three')`; other harnesses are
  `unverified`.)
- Probe protocol (`skin-guard-other.json` `probe.sampling`, one case = **9 samples**): pull and **hold 36
  frames, sampled every 12 (3)**; **release**; **rebound 60 frames, every 12 (5)**; **settle 300 frames then 1
  sample (1)**; steps via `namiStudio.step(1/60)` with the page paused. The recorded files differ in how they
  record this: the 32 touch/tissue cases carry per-phase counts, the other 61 carry a total `samples`.
  For those, G3 needs the declaration: `--sampling-declared "hold 36 frames/12, release, rebound 60/12,
  settle 300 + 1 sample = 9 per case"`, and fails when a case has fewer than 9 samples.
- Gate: **G1** (no case with inside > 0 or deepest > 0.3 mm; a case with no recorded measurement is
  `unmeasured`) and **G3** (hold ≥ 3, rebound ≥ 3, settled ≥ 1).
- Must fail: before the guard a ribbon pull put **6.1 mm** of the neck loop (78 samples), up to 3.6 mm of the
  cups and 3 mm of the ribbon inside the skin (worst direction down-left 225°); a cup pull 2.8 mm. The unit
  tests run the same pulls with `passes: 0` in a scratch copy and fail with cloth **5.32 mm** (strap) and
  **0.46 mm** (cup) under the skin (`skinGuard.verification.unitTests.nonVacuous`). Gate tests:
  `test_skin_in_front_of_the_cloth_fails_g1`, `test_deeper_than_threshold_fails_g1_even_with_zero_inside`.
- Not covered: the outfit-change fall (A10). The guard's own `violations` list can end non-zero in a rare
  frame (`[289, 17, 2, 1, 1, 1]`) while the probe still finds nothing inside; report it, do not hide it.

## A9. Cost of the per-frame garment update

- Delivered (`garments.apply()` under a held pull, headless Chromium, software GL; no hardware host is
  recorded beside these numbers; frame rates do not transfer to other devices): ribbon pull median **7.9–10.2 ms** /
  p95 **13.3–15.3 ms** (4 runs; before the guard 6.3 / 8.5); cup pull **4.4–4.9 / 6.9–8.9** (3.3 / 4.8);
  outfit fold **4.3 / 8.9** measured at a heavily loaded moment (load average about 90; before 1.9 / 3.0)
  (`skinGuard.cost`). A separate run: ribbon pull apply median 4 / p95 5.6 / max 13.5 ms, softbody update
  median 8.6 ms (`connected-interaction.json` `cost`); another recorded 6 / 10.3 / 13.2 ms (`connectedChain.cost`).
- Measure: wrap `garments.apply()` with `performance.now()` for 30+ frames under a held pull and report
  median, p95 and max with the host and load.
- Must fail: JOB records **no pass/fail budget** (unverified); the comparison is against the unguarded cost,
  which the guard raised (6.3 / 8.5 → 7.9–10.2 / 13.3–15.3 for a ribbon pull). State the cost, do not assert
  a frame rate for other hardware.

## A10. Outfit change sequence

- Delivered: 3.8 s (0.4 s cross-fade with reduced motion): release 0–0.4, fall 0.4–1.6, recolor 1.6–2.7,
  lift 2.8–3.5, reseat 3.5–3.8 s; order checked at **13** sampled times with **0 non-finite** vertices;
  flap = **12.2 %** of cup vertices, max **24.3 mm**; flap and ribbon 0 at start and end
  (`connected-interaction.json` `sequence.rows`). Tests: `garment.test.mjs` "neck release comes first, ribbon
  and flap fall, recolor happens while fallen, then lift and reseat exactly" and "the fall accelerates to
  touchdown, bounces a little and settles on the cup".
- Measure: `namiStudio.setOutfit(id)` then `namiStudio.step()` to each time; read
  `garments.getState().transition.phase` (`fold`, `cut`, `morph`) and the flap/ribbon displacement.
- Must fail: recolor while the ribbon is still up (the rule is recolor only while `fold >= 0.8`), a fall
  before the release completes, or a vertex that is not finite.
- **Outside the outer-layer guarantee:** the independent probe flags ribbon samples inside the skin in the
  fall (up to 13 mm at 1.0 s over the cup edge, a few up to about 33 mm at the hanging end) although the
  guard's own measure reads 0. Say so; do not extend A8 to the fall (`connected-interaction.json`
  `skinGuard.knownLimit`).

## A11. Round chest

- Delivered: 8 directions at 38 mm from the apex plus the apex, 25 mm drag: tissue moves **7.3–8.0 mm**
  (inner side 5.8–6.0), topology-guard scale **0.96** (was 0.51), squeeze dents **8.5–10.1 mm** (was 2.0–5.3);
  trusted-mouse drags from four sides move the breast **8.0 mm** along the drag
  (`roundChest.finalLeftBreast`, `realMouseDrags` 16 rows, `baselineLeftBreast`).
- Measure: the protocols in `connected-interaction.json` `protocol.chestProbe` (rays from the torso camera
  at the apex and 8 directions at 38 mm; squeeze then a 25 mm grab-drag in +x, -x, +y, -y) and `mouseChest`.
- Must fail: the authored masks without `ROUND_CHEST` (baseline: 7.9 mm at the top but 2.4 mm at the bottom;
  guard scale 0.51). Tests: `chest-field.test.mjs` (4).

## A12. Unit tests of the byte-identical runtime

- Delivered: **47** node tests (chest-field 4, garment-field 3, garment 15, softbody 25); `npm test` in JOB
  passed 47, 0 failed (`skinGuard.verification.unitTests`); the plugin copy was run again while writing this
  file: `# tests 47 # pass 47 # fail 0`.
- Command: `cd PLUGIN && node --test tests/garment-character/*.test.mjs` (Node ≥ 20; `three` 0.186.1).
- Must fail: the skin-guard tests with `passes: 0` (A8), a runtime file edited away from `provenance.json`
  (`tests/test_garment_character_provenance.py`).

## A13. The build under review is the build that is running

- Delivered: `serve.py` sends `Cache-Control: no-store, max-age=0`; `window.namiStudio.build` is `guard-1`
  and the footer `#build-stamp` shows it; the matrices carry `chain-1 (identical code to guard-1; only the
  footer stamp was renamed afterwards)` (`skin-guard-*.json` `build`).
- Measure: read the stamp in the page before reading any result; compare with the evidence `build`.
- Must fail: a stamp that differs from the evidence, or `python3 -m http.server`. Case: the user was shown
  a stale build once (reported in the delivery session; not in a JOB file).

## Whole-run command

```bash
cd ~/.img2/plugins/character
node --test tests/garment-character/*.test.mjs
python3 tools/gate_garment.py \
  --matrix "$J/evidence/skin-guard-desktop.json" --matrix "$J/evidence/skin-guard-other.json" \
  --matrix "$J/evidence/connected-interaction.json" \
  --sampling-declared "hold 36 frames/12, release, rebound 60/12, settle 300 + 1 sample = 9 per case"
```

On JOB's own recorded evidence this was run for this document: G1 pass (93 cases, deepest 0 mm), G2 pass,
G3 pass (32 cases record per-phase counts, 61 record only `samples >= 9` and rely on the declaration),
G4 pass (84 pulls, ribbon ≥ 24.50 mm, cup ≥ 16.80 mm), G5 pass (16 release cases), exit **0**. Without
`--sampling-declared` G3 is `unmeasured` and the exit is **2**, by design. A clean subset is not a pass:
fewer matrix cells than A7 lists fail G2 even with zero inside samples.

## Untraced / conflicting

- Cup reach 178.2 mm in `delivery-manifest.json` against 216.1 mm in the evidence (A2).
- "of 3730" triangles against `triangles: 6192` recorded (A5).
- Location (neck loop) of the single desktop edge past 2.5x (A4).
- Any cost budget or flip limit: none recorded (A5, A9).
- Whether `influence()` count 1338 means the pin fade (A2); the probe outside the recorded harness (A8).
- The stale-build and un-grabbable-ribbon cases are from the delivery session, not from a JOB file (A7, A13).
