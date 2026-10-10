# @img2threejs/character

Public installer for the img2 plugin **`character`**, sourced from
[`img2threejs/plugin-character`](https://github.com/img2threejs/plugin-character).
This npm package contains the installer only. The plugin implementation (skeleton extraction,
skin conditioning, clip measurement, action design and the twelve-check rig gate) is fetched
separately from the Git source and is not shipped in this tarball.

The npm package is scoped to `@img2threejs/character`; the executable installed into `PATH`
stays unscoped as `img2-character`. This is a thin launcher; the shared runtime is
[`@img2threejs/img2`](https://www.npmjs.com/package/@img2threejs/img2), pinned to an exact
version (`0.4.0`). The plugin source commit is also pinned in the package metadata; the CLI
version (`0.2.0`) and the plugin source version (`v0.2.0`) are released on separate tracks.

## Quick start

Requires Node.js >=18, Git, Python >=3.10, and a Claude Code, Codex or OpenCode host.
Hermes is not supported by the img2 plugin harness at this time. The plugin source is public,
so no GitHub credential helper is required.

```bash
# Preview only: no downloads, no subprocesses, no filesystem writes.
npx --yes @img2threejs/character install --dry-run

# Install the img2 harness if missing, then fetch and link this plugin.
# --yes explicitly approves the harness setup prompt.
npx --yes @img2threejs/character install --yes
npx --yes @img2threejs/character doctor
```

Or install the CLI globally:

```bash
npm install -g @img2threejs/character
img2-character install --yes
img2-character doctor
```

For a project-local CLI:

```bash
npm install @img2threejs/character
npx img2-character install --yes
```

Installing an npm CLI alone **does not** install an agent skill or start a rig build. The
`install` command initializes the canonical img2 harness under `$IMG2_HOME` (default
`~/.img2`), registers this plugin, and links it into detected hosts. The shared runtime
comes from `@img2threejs/img2`; its executable remains `img2`.

## Source pin, update behaviour, and what this installer does not claim

- **Source pin.** This CLI's metadata pins plugin commit
  `796dd9caf3f299958cf75b2294f54b37dc23ada9` (plugin source tag `v0.2.0`). An explicit
  `--ref vX.Y.Z` or `--ref <40-char SHA>` on `install` overrides that pin for that run;
  omit `--ref` to accept the metadata pin. The CLI executable version (`0.2.0`) is
  independent of the plugin source version (`0.2.0`).
- **Update behaviour.** `update` follows the registered source's release policy through
  the harness. Plugin source updates require a semantic `vX.Y.Z` tag on `img2threejs/plugin-character`;
  CLI updates require a separate `cli-vX.Y.Z` tag on this repository. The two tracks never
  share a tag. An existing `--link` registration or another source is not silently replaced.
- **Reconstruction / rig quality.** This package is an installer. It does not reconstruct,
  measure, score, or rig anything on its own. The rig gate, character scaffolding, rig
  validation and rig measurement live in the plugin source and run only after the user
  invokes the installed `/img2-character` skill with a real reference image and GLB rig.
  Installation is **not** a claim that a rig build, rig measurement, or rig gate has
  passed. Provider dependencies, model access remain explicit prerequisites.

## Commands

```text
img2-character install [--ref <vX.Y.Z|40-char SHA>] [--home <absolute path>] [--yes] [--force] [--dry-run]
img2-character update [--home <absolute path>] [--yes] [--check]
img2-character remove [--home <absolute path>] [--yes]
img2-character doctor [--home <absolute path>] [--json]
img2-character version [--json]
img2-character help
```

`--dry-run` performs no downloads, subprocesses or writes. `--force` changes only this
plugin's registered ref; local links and registrations from another source are protected.
`doctor` audits the installed harness and any plugins registered there; it does not run a
model, renderer or rig measurement. Exit codes: `0` success, `1` failure, `2` refused,
`3` confirmation requires a terminal.

## Manage the installation

```bash
npx --yes @img2threejs/character --version
npx --yes @img2threejs/character update --check
npx --yes @img2threejs/character update --yes
npx --yes @img2threejs/character remove --yes
```

## Develop this installer

From the repository root:

```bash
npm --prefix cli install
npm --prefix cli test
npm --prefix cli pack --dry-run
```

To run a globally installed CLI:

```bash
npm install -g @img2threejs/character
img2-character install --yes
```

## Release this CLI

The package root is `cli/`, isolated from plugin content. Tags `cli-vX.Y.Z` must match
`cli/package.json`; plugin source tags `vX.Y.Z` on `img2threejs/plugin-character` are
independent. `.github/workflows/cli-publish.yml` publishes the installer through npm
trusted publishing. Configure the npm package's GitHub trusted publisher for organization
`img2threejs`, repository `plugin-character`, workflow filename `cli-publish.yml`, and
allow **direct `npm publish`**.

The plugin source is public, so npm provenance is enabled (`provenance: true` in
`cli/package.json`) and stays on for every subsequent trusted CI release. No npm write
token is stored in Actions. The first publish of a new package is a one-time manual bootstrap
from a maintainer with package write access and account-level 2FA; that bootstrap publish
cannot use `--provenance` because npm provenance is only minted by trusted CI, so it is
released without provenance. Subsequent CLI releases run through the SHA-pinned,
tested-artifact GitHub workflow with `provenance=true`.

The first publish of a new package is manual and skips provenance:

```bash
cd cli
npm test
npm publish --access public --ignore-scripts --provenance=false
cd ..
```

Then authorize trusted publishing for this package:

```bash
npm exec --yes --package=npm@11 -- npm trust github @img2threejs/character \
  --repo img2threejs/plugin-character --file cli-publish.yml --allow-publish --yes
```

The package must already exist on npm. Initial publication is manual and without
provenance; subsequent CLI tags run through trusted publishing with `provenance=true`.

```bash
# Bump cli/package.json and update CLI release notes first, then commit reviewed CLI files.
git tag -a cli-v0.2.0 -m 'img2-character CLI 0.2.0'
git push origin cli-v0.2.0
```

`workflow_dispatch` is also exposed on this repository's workflow; pass a matching
`cli-vX.Y.Z` tag value so the workflow validates and publishes the exact tarball whose
`cli/package.json` version already matches that tag. Immutable npm versions cannot be
overwritten — the workflow does not re-publish an existing `cli-vX.Y.Z` once it is on npm;
for a new release, bump `cli/package.json`, push a fresh annotated tag, then push it.

Never publish from the plugin repository root: npm would automatically include the root
README, plugin tools, gates and source assets. Keep plugin content untouched until a
separate explicit source release.

## CLI release notes

- **0.2.0**: initial public installer-only npm package for the `character` plugin.
  Shared runtime pinned to `@img2threejs/img2@0.4.0`; plugin source pin is immutable
  at commit `796dd9c` (plugin source tag `v0.2.0`). npm provenance is enabled because
  the plugin source repository is public.