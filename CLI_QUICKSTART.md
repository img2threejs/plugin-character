# @img2threejs/character quick start

The public npm installer lives in [`cli/`](cli/README.md). Plugin implementation (skeleton
extraction, skin conditioning, clip measurement, action design and the rig gate) stays at
the repository root and is **not** included in the npm tarball.

## Install the plugin

Requires Node.js >=18, Git, Python >=3.10, and Claude Code, Codex or OpenCode. The plugin
source is public, so no GitHub credential helper is required. Hermes is not supported by
the img2 plugin harness at this time.

```bash
npx --yes @img2threejs/character install --dry-run
npx --yes @img2threejs/character install --yes
npx --yes @img2threejs/character doctor
```

Installation creates the canonical img2 harness if missing, fetches
`img2threejs/plugin-character`, and links this plugin into detected hosts. It does not
run a model, a reconstruction, or a rig build. The plugin source commit pinned in
`cli/package.json` is `796dd9caf3f299958cf75b2294f54b37dc23ada9` (plugin source tag
`v0.2.0`). The CLI executable version (`0.2.0`) is released on a separate track.

## Develop this installer

```bash
npm --prefix cli install
npm --prefix cli test
node cli/bin/cli.mjs install --dry-run
```

To run a globally installed CLI:

```bash
npm install -g @img2threejs/character
img2-character install --yes
```

## Publish the first npm version

Use Node >=22.14 and npm >=11.15 for release setup. The npm account needs package write
access and account-level 2FA. Review the package contents; never publish from the plugin
repository root.

```bash
cd cli
npm test
npm pack --dry-run
npm publish --access public --ignore-scripts --provenance=false
cd ..
```

Then authorize the GitHub **caller** workflow filename, not the shared workflow filename:

```bash
npm exec --yes --package=npm@11 -- npm trust github @img2threejs/character \
  --repo img2threejs/plugin-character --file cli-publish.yml --allow-publish --yes
```

The package must exist before this command can configure it. The npm website's trusted
publisher settings are equivalent. No npm write token is stored in Actions. The plugin
source repository is public, so npm provenance is enabled in `cli/package.json` and in
the trusted CI workflow; the one-time manual bootstrap publish above cannot mint
provenance outside trusted CI, so it ships with `--provenance=false`. All subsequent CLI
releases flow through trusted publishing and ship with provenance enabled.

## Publish subsequent releases automatically

Bump `cli/package.json` and the CLI release notes inside `cli/README.md`, review and
commit only intended changes, then push a matching annotated `cli-vX.Y.Z` tag. For
example, after bumping to `0.2.1`:

```bash
git tag -a cli-v0.2.1 -m 'img2-character CLI 0.2.1'
git push origin cli-v0.2.1
```

`.github/workflows/cli-publish.yml` tests, packs and publishes the exact tested tarball.
Stable CLI versions use npm's `latest` channel. Plugin source tags `vX.Y.Z` remain
separate from CLI release tags `cli-vX.Y.Z`.

The repository's workflow also accepts a `workflow_dispatch` input with a `cli-vX.Y.Z`
tag value, so maintainers can validate and publish the exact tarball whose
`cli/package.json` version already matches that tag. Immutable npm versions cannot be
overwritten — for a new release, bump `cli/package.json`, push a fresh annotated
`cli-vX.Y.Z` tag, then push it.

See [`cli/README.md`](cli/README.md) for CLI command details and
[npm trusted publishers](https://docs.npmjs.com/trusted-publishers/) for authentication.