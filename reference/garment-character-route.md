# Calibrated garment mechanics

Route ID: `garment-character`. This composes with the admitted-asset, native, CC5 and softbody routes; it does not replace their authoring or acceptance requirements.

## Shipped scope

`runtime/garment-character/synthetic-scene.mjs` independently constructs a Cartesian support grid, a connected rectangular cloth grid, one `BoardAnchor` bone and a `BoardSlide` translation clip. The surface is an authored cosine function, not a body scan. Texture pixels are a blue rectangle and white stripe painted by code. `synthetic-config.mjs` independently chooses board-scale dimensions and artistic settings. There are no imported meshes, old measured matrices, body landmarks or third-party textures in this example.

This is a geometric solver demo, **not human/garment fidelity, native acceptance, real-device performance, likeness or rights evidence**. Historical subject studies, tables and copied receipts are no longer distributed in HEAD. This does not erase history or establish permission for any previous or caller-supplied asset; see `../NOTICE`.

## Run locally

Use existing local dependencies (`three` 0.186.1), then serve the **plugin root**:

```sh
python3 runtime/garment-character/serve.py 18773
# open http://127.0.0.1:18773/runtime/garment-character/
```

No network, model download, native binary or third-party asset is required by the default page. Dependencies must already be installed by the caller. Interaction modes, orbit/zoom, region impulses, clip playback, surface comparison, cloth grabs, release/reset and color transition remain available. The page visibly identifies the synthetic example.

## Real inputs: explicit configuration, no case fallback

Open the viewer with `?config=/caller/config.json`. The JSON must set `synthetic:false`, `label`, `glb`, `sidecar`, exact `clip`, `initialView`, `views` (named position/target triples), `regionViews`, `outfitLabels`, camera clipping/FOV/distance limits, `background`, `lights` and `probes` (`panelY`, `pullDistance`). Mesh and clip names are exact selections, never guessed. The synthetic config documents the complete shape, not values to copy for a different mesh.

Required mechanics contracts are validated by `calibration.mjs` before attachment:

- `garment`: exact `bodyMesh`/`garmentMesh`, side-to-region map, two outfit IDs, reveal origin and normal-orientation origin; `strap`, `panel`, `strapField`, `cupLift`, `contactSteady`, `flap`, `contact`, `colorway`, `visual` objects.
- `strap`: attach/top heights, x/z eligibility, max pull, grab interval, spring frequencies/damping and tension. `panel`: max pull, normal lift, frequency and damping.
- `strapField`: geodesic reach multiplier, explicit minimum/fallback reach, pin fade length and lift fade interval. `cupLift`: gap, lead interval and extent.
- `flap`: hinge, bend and reach lengths, lift clearances, cut fraction, normal sampling radius and hanging direction. `contact`: height ROI, search radii and minimum/maximum rest clearance in garment bind space.
- `colorway`: saturation interval, four increasing hue-band boundaries, destination hue and saturation/value scales. `visual`: spark, noise, reveal and wave dimensions and glow color.
- `soft`: all five artistic profiles and contact-pad dimensions. Each profile declares frequency, damping ratio strictly between zero and one, displacement cap, compression and optional signed press depth.
- `round`: plateau/reach, wall depth/fade, midline/fade, region IDs and attribute suffix. Shared space is the first sidecar mesh's bind-local frame; support axes are +Z forward and X bilateral. Inputs using another convention must be prepared accordingly, not silently reinterpreted.

Missing, nonfinite, inconsistent or unresolved configuration refuses readiness and reports an error. Real inputs must supply their own geometry, skin attributes, normals, UVs, color map, region sidecar and actual clip. A default synthetic file never supplies missing real calibration.

## Algorithms retained

Graph welding/geodesic fields, nearest-surface contact walking, spring integration, transitions, topology attenuation, smoothing and outer-layer correction remain generic algorithms. Local centres, normals, rest gaps and sag are computed from the supplied mesh. The retained `TRANSITION`/`REDUCED_TRANSITION` are authored timeline mechanics; `PULL_PATCH` is a dimensionless kernel policy. `SKIN_GUARD` retains floor 0.0008 m, six passes, relaxation 1.6, sag factor 4, centre minimum 0.0004 m and vertex-pruning slack. Moved triangle centres are measured directly: rest sag cannot bound current sag after lateral motion across a new ridge. The unsound centre-pruning shortcut and its obsolete slack were removed. Soft topology limits, substeps and sleep tolerances are generic numerical policies, not source calibration.

## Debug and independent probes

The sole browser API is `window.garmentStudio`: `ready`, `error`, `config`, root/rig/garments/camera/renderer/meshes, view/motion/surface/outfit controls, `step`, `render`, `locate`, `diagnostics`, reset/release/dispose. There is no historical-name alias. Load `tools/skin_probes.js` into that page for exact nearest-surface `__inside({faces:true})` and `__combo*` helpers. Probes select the configured meshes and panel target; an unready or uncalibrated page is refused.

## Acceptance and generated files

See [garment-acceptance.md](garment-acceptance.md). Supply G4 calibration explicitly:

```sh
python3 tools/gate_garment.py --parameters /caller/calibration.json \
  --matrix /caller/desktop.json --matrix /caller/other.json --matrix /caller/connected-interaction.json --json
# calibration.json: {"calibration":{"strap":{"maxPull":...},"panel":{"maxPull":...}}}
```

Missing limits remain unmeasured. Synthetic parameters are not a default for real evidence. Gate fixtures are constructed contract inputs, not observations of trusted browser events.

Regenerate artifacts after changing source/config/tests:

```sh
node tools/extract_garment_parameters.mjs --out reference/garment-parameters.json
python3 tools/generate_synthetic_reference.py
```

The latter regenerates the primitive catalogue, four synthetic gate fixtures and the sha256/byte manifest of every runtime/test file. `garment-parameters.json` records only exported generic constants and the independently authored example config; there is no hand-read subject-literal inventory.
