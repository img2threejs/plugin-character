# Blender source assets: rights, catalogues and manifests

Use with `blender-character-route.md` and `blender-geometry-workflow.md`. This file decides where a legal asset comes from, what
it may be used for, and what must be recorded. It authors nothing.

## Scope and non-negotiables

- This route is for explicit Blender/bpy authoring. Never call Tripo, CharacterGen or another neural/image-to-mesh service, and
  never substitute a previously generated mesh for the requested identity. Adapted source anatomy is described as such
  (`blender-geometry-workflow.md`).
- Prefer CC0 or an equivalent public-domain dedication; anything else needs a recorded, job-specific grant before it enters the
  build. Prefer curated core sources over the whole community catalogue: a named shortlist with hashes is auditable, a scraped
  library is not. Never quietly swap the identity, source, licence or resolution of an admitted asset.
- Record **two separate rights** per asset: (a) may this workflow handle it at all — local authoring, preview, and any
  AI/ML-assisted handling the licence permits — and (b) may the derivative be **redistributed inside a downloadable GLB**. Rights
  for (a) do not imply rights for (b), and vice versa.
- No purchases, paid tiers, uploads or publishing without a recorded grant. Generation intent or local preview is never permission
  to publish. Never run or auto-execute scripts embedded in a downloaded `.blend`, `.sbsar` or archive.

## Curated CC0 catalogue

**MakeHuman community packs** — core assets are CC0, "free to do as you see fit with the asset or derivates of the assets"; the
code licence (MakeHuman AGPL, MPFB GPL) does not restrict asset use (https://static.makehumancommunity.org/about/license.html).
Pack index: https://static.makehumancommunity.org/assets/assetpacks/index.html
- **[skins01](https://static.makehumancommunity.org/assets/assetpacks/skins01.html)** — 24 natural female skin textures.
  `skins01_cc0.zip`, `files2.makehumancommunity.org/asset_packs/skins01/` (mirror2
  `files.makehumancommunity.org/asset_packs/skins01/`), 99 MB.
- **[skins02](https://static.makehumancommunity.org/assets/assetpacks/skins02.html)** — 13 natural male skin textures.
  `skins02_cc0.zip`, `files2.makehumancommunity.org/asset_packs/skins02/` (mirror2
  `files.makehumancommunity.org/asset_packs/skins02/`), 72 MB.
- **[makehuman_system_assets](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html)** — eyes,
  teeth, hair, brows, lashes, clothes, shoes, proxy meshes: the CC0 core set. `makehuman_system_assets_cc0.zip`,
  `files2.makehumancommunity.org/asset_packs/makehuman_system_assets/`, 267 MB.
- Each pack page lists a per-asset creator and licence row (MargaretToigo, OnlyTheGhosts, CutOff3D, Mindfront, …): record that
  creator, not just the pack name. Other packs are **CC-BY** (`Hair 02`, `Shirts 02`, `Suits 03`, `System eye materials 03`,
  `Animal 02–04`) and need attribution.

**ambientCG materials and substances** — every asset is CC0 1.0: you may "copy, modify, distribute and perform the assets, even
for commercial purposes… include the raw files in your project" (https://docs.ambientcg.com/license/; types
https://docs.ambientcg.com/asset-types/). Channels and packages below are what the asset page and API actually list for that id —
verify against the live listing, never assume a channel or resolution is present.
- **[Fabric016](https://ambientcg.com/view?id=Fabric016)** — PBR material, woven wool, released 2019-01-09, parent asset
  `FabricSubstance005`. Listed maps: color, displacement, normal, roughness, opacity. Listed downloads: `Fabric016_1K-JPG.zip`,
  `_2K-JPG.zip`, `_4K-JPG.zip`, `_8K-JPG.zip`, `_1K-PNG.zip`, `_2K-PNG.zip`, `_4K-PNG.zip`, `_8K-PNG.zip` (JPG/PNG only, no
  EXR package).
- **[Fabric002](https://ambientcg.com/view?id=Fabric002)** — PBR material, cloth/pattern, released 2018-01-28. Listed maps: color,
  displacement, normal, roughness. Listed downloads: `Fabric002_1K-JPG.zip`, `_2K-JPG.zip`, `_4K-JPG.zip` (JPG only, 1K–4K, no
  PNG package).
- **[FabricSubstance005](https://ambientcg.com/view?id=FabricSubstance005)** — Substance graph, knitted wool, 2019-01-09. Listed
  download: `FabricSubstance005_COMPILED.sbsar` (317 KB) only.
- Enumerate, never scrape or synthesise URLs: `https://ambientcg.com/api/v2/full_json?id=<AssetId>&include=downloadData` gives the
  map list and download folders; `https://ambientcg.com/api/v2/downloads_csv?type=Material&id=<AssetId>` (type `Substance` for
  `.sbsar` assets) gives one row per real file with size and URL. v2 is frozen — new work uses
  https://docs.ambientcg.com/api/v3/index.html (`/api/v3/assets`), whose bearer token is only needed for Patreon-tier benefits.
  Fabric: `https://ambientcg.com/list?category=Fabric`.

**Poly Haven textures** — assets are CC0 and explicitly redistributable "including in a product you sell"
(https://polyhaven.com/license). That page's Terms of Service protect the site's own non-asset content (logos, avatar images,
example renders, text): copy assets, not page images. Enumerate per-file metadata (exact URL, byte size, MD5) from
`https://api.polyhaven.com/files/<asset_id>`; asset list `https://api.polyhaven.com/assets?t=textures`.
- **[fabric_pattern_05](https://polyhaven.com/a/fabric_pattern_05)** (Rob Tuytel) — 8K cotton windowpane plaid, 500 mm tile.
  Roles: `col_01/02/03`, `nor_gl`, `nor_dx`, `Rough`, `AO`, `arm`, 1K–8K PNG/JPG/EXR, plus `blend`/`gltf`/`mtlx` packages.
- **[fabric_pattern_07](https://polyhaven.com/a/fabric_pattern_07)** (Rob Tuytel) — 8K red-and-cream woven cotton towel weave, 400
  mm tile. Roles: `col_1`, `col_2`, `col_03` (different colour-role naming), `nor_gl`, `nor_dx`, `Rough`, `AO`, `arm`,
  1K–8K PNG/JPG/EXR.
- **[fabric_leather_01](https://polyhaven.com/a/fabric_leather_01)** / **[02](https://polyhaven.com/a/fabric_leather_02)** (Poly
  Haven staff) — leather grain. Roles: `Diffuse`, `Displacement`, `Rough`, `AO`, `rough_ao`, `arm`, `nor_gl`, `nor_dx`,
  1K–8K.

## Formats: raw maps, compiled .sbsar, editable sources

- **Raw maps** (`.png`, `.jpg`, `.exr`) are the working channels: base colour, roughness, metallic, AO, normal (OpenGL or
  DirectX), opacity, displacement. **EXR is a master source, not a stock core-glTF embedded image format**: keep the linear EXR
  master, and convert or re-bake it to a supported delivery image (PNG/JPEG, or a separately verified compressed-texture
  extension) before it ships inside the GLB.
- A **`.sbsar`** is a *compiled* Substance graph — a playable archive, not editable graph source. A compatible Substance engine
  can expose the parameters the author published, so published exposed controls may work; arbitrary edits to the internal graph
  require editable source. **Editable sources** are `.sbs` (graph), `.blend` and `.psd`; only these allow restructuring the
  graph, adding nodes or repainting layers.
- **Do not claim all editable files are free.** Verified example: `FabricSubstance005` publishes the compiled `.sbsar` (317 KB)
  anonymously, while its Substance **project** `.sbs` is labelled "Substance Project files (.sbs) are available for Patreon
  supporters" — the page's "PROJECT .zip 125 KB" row is a Patreon reward, and the API lists only the `COMPILED` `.sbsar`. If a
  job needs a different weave scale, colourway or re-baked normal, prefer a source that ships raw maps and rebuild it in Blender.

## Sources that need written authorization

Do not admit either source by default for LLM-assisted standalone character/GLB delivery. Verify handling, viewer and derivative-distribution rights for the intended use.
Require an express written exception where ordinary terms prohibit that use; record the exact grant, scope and date, or exclude the source.
A blocked licence is a named prerequisite, never permission to substitute a similar asset silently or publish without user authorization.
- **texturing.xyz** — current Terms of Service (last updated 29 August 2026, https://texturing.xyz/pages/terms-of-service)
  prohibit, without express prior written authorization: distributing Materials where the product is itself primarily a
  material/texture/scan/collection, or as part of a texture or material pack; using Materials or derivative data with AI/ML/neural
  networks or dataset/model training; producing an **online or offline 3D viewer**, anatomy viewer or photography viewer; creating
  and selling customer assets stand-alone; and using external suppliers to handle the Materials. A Business Commercial Project
  Licence grants integration into one production, not redistribution of the raw material. Because the AI/ML restriction is about
  *handling*, not just shipping, exclude the asset from LLM-assisted handling unless the exact written permission covers it.
- **3D Scan Store** — https://www.3dscanstore.com/terms-and-conditions-licensing: "NOT in any cases permitted to: Sell or
  distribute any of these 3D Models or Scans in an unmodified form, or where the derived product you are selling or distributing
  is a 3D model or Scan or a collection of 3D models or scans, alpha or texture packs"; it also bars integrating scan data into a
  character-maker programme whose results export as 3D models, and bars redistributing AI training datasets derived from its
  assets. A **game** licence is not blanket redistribution permission: the Business Commercial Single Project Licence covers one
  for-sale project, and the Business R&D licence excludes a final for-sale project. Ask for the exact grant.
- A derivative built from a prohibited source does not become distributable by omitting the original bytes: if the licence forbids
  the derived use, the derived model stays out of the shipped GLB.

## User-supplied licensed base meshes

The user may supply their own authored or licensed base mesh; that is often correct.
- Require before import: local path and SHA-256, creator/rights holder, licence name plus its URL or the signed grant, whether
  LLM-assisted handling is permitted, whether redistribution inside a downloadable GLB is permitted, and whether likeness/consent
  covers the intended use.
- Accept it as **adapted source anatomy**, not reconstruction produced here; keep the original unmodified and work on a copy.
- Without LLM-handling permission, exclude it from LLM-assisted authoring even locally. Local-only use needs its own authorization.
- Without derivative-GLB rights, exclude the prohibited source and derivatives from delivery; never silently substitute a generic avatar.

## Asset manifest fields

One row per admitted asset (e.g. `source-assets.json` in the job). A row is incomplete until every field below is filled from the
actual file, not from its name.
- `id`, `role` — stable id; `skin` / `garment-fabric` / `hair` / `eye` / `base-mesh`.
- `asset_page`, `download_urls` — the page it came from; the exact file URL(s) used. `creator` — creator/rights holder name as
  published.
- `license`, `license_url`, `license_version_or_terms` — licence name, URL of its text, and the terms/version as published on
  the access date. Re-read the licence before shipping.
- `access_date` — ISO date the file was fetched. `local_path`, `sha256` — where it landed and the SHA-256 of the archive.
- `maps[]` — per map: `role` (base_color / normal / roughness / metallic / ao / displacement / opacity), `file`, `resolution`,
  `source_color_space` (as the vendor published it — an EXR may be scene-linear, a PNG colour map usually sRGB),
  `delivered_color_space` (what ships), `convention` (OpenGL/DirectX for normals), `sha256` of that map file, `used_as` (what the
  job used it for).
- `permissions` — `llm_assisted_handling`, `redistribute_in_downloadable_glb`, `commercial_use`, `attribution_required`,
  `basis` (the clause each rests on). `notes` — edits made, missing channels, "no editable .sbs published anonymously", pack-level
  restrictions. Also record the colour space and normal convention you actually use, and whether you edited the file (then it is a
  derived asset with its own hash).

## Acquisition, hashing and distribution

- Download only from the recorded URLs, one manifest row per file. Pick the highest resolution the device budget allows, then keep
  it; a different resolution mid-job needs new URLs and hashes.
- Hash every archive and every extracted map (SHA-256), then re-hash after extraction so a truncated transfer cannot pass as a
  valid map. Record the Blender version and assigned colour space.
- Keep sources, extracted maps, the editable `.blend` and the exported GLB in separate directories. The GLB embeds baked maps; the
  source maps stay as editable master material.
- Before shipping, confirm `permissions.redistribute_in_downloadable_glb` is true for **every** map embedded in that GLB,
  including AO, normal and roughness channels from third-party packs. A CC0 colour map does not make a restricted normal map free.
  Shipping an asset whose licence forbids stand-alone distribution is prohibited even inside a character GLB: the derived product
  is the asset.
- Keep the manifest with the job: a reviewer must re-derive every shipped byte to a URL, a licence and a hash without trusting
  this prose. Next: `blender-pbr-workflow.md`.
