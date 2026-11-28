# Garment acceptance contracts

No real-input acceptance result is bundled. The default viewer and deterministic tests exercise independently authored geometry only. Synthetic contract fixtures are not recorded native/browser evidence and do not establish fidelity, performance or rights.

## Required real-input evidence

Keep the existing gate policy unchanged:

- **G1:** every garment vertex and triangle centre must have an independent signed-distance probe. No `inside > 0`; no depth greater than 0.3 mm. Missing values are unmeasured. Include an under-surface negative control to prove the probe detects penetration.
- **G2:** trusted mouse pulls for ribbon/cup, both sides, all eight 45-degree angles; left-side full-angle coverage in two outfits; trusted touch coverage in both outfits/kinds at four angles; both tissue modes on both sides; at least ten combo cases. API calls do not establish trusted mouse/touch evidence.
- **G3:** at least three hold, three rebound and one settled samples per case. A declared schedule is explicitly labelled declared, not recorded, and requires nine total samples. Missing sampling is not a pass.
- **G4:** every garment pull reaches at least 0.7 times its **explicitly selected input limit**. Tissue-only interactions are exempt. Missing calibration or pull measurements are unmeasured. Absolute flags are explicit overrides, never implicit demo fallback.
- **G5:** recorded release has exactly zero render mismatch and `stillGrabbed:false`. Missing release evidence is unmeasured.

Only all-pass exits 0. Failure exits 1; unmeasured/input error exits 2. Full caller-owned recording matrices must accompany any real-input claim. No synthetic result waives G10, source admission, native control, material, renderer, rigging or export-parity rules.

## Runtime mechanics

Exercise actual connected triangles, capture exclusivity, nonempty bounded influence, resisted inward/far pulls, contact over curved surfaces, held and rebounding clearance, exact release/reset and solver-rest preservation. Transition order and reduced motion are tested separately; transition folding is not proof of general cloth collision or coverage of anatomy. Do not infer topology quality or render correctness from a signed-distance result alone.

`tools/skin_probes.js` reads the ready `window.garmentStudio` config, not fixed mesh names or old coordinate heights. Sample both vertices and face centres against posed support triangles. Record actual events and phases, not a synthetic `trusted:true` object.

## Focused verification (integration owner)

```sh
node --test tests/garment-character/*.test.mjs tests/skin-probes.test.mjs
python3 -m unittest discover -s tests -p test_garment_character_manifest.py
python3 -m unittest discover -s tests -p test_gate_garment.py
python3 -m unittest discover -s tests -p test_body_parts.py
python3 -m unittest discover -s tests -p test_skin_body_plan.py
```

Serve the plugin root as documented in `garment-character-route.md`. In an actual browser, inspect synthetic identification, readiness/error handling, both colorways, motion clip, orbit/zoom, region impulse and cloth press/drag/release/reset. Check invalid real config visibly refuses readiness. Record browser/device details and observed results; do not replace this step with a source-string assertion.
