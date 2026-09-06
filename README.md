# plugin-character

Character rigging and animation for [img2threejs](https://github.com/img2threejs/img2threejs), as an
[img2](https://github.com/img2threejs/img2) plugin.

```bash
img2 add img2threejs/plugin-character
```

## What it is for

An img2threejs reconstruction produces a static mesh. This plugin takes it from there: a skeleton read
out of a GLB, skin conditioning across overlapping parts, clips measured rather than guessed at, and a
twelve-check gate where **an unmeasured check is never a pass**.

The base skill stays the entry point. Without this plugin a character reference still reconstructs —
with no rig, no skinning and no bind. Less exact is the intended trade; useless is not.

## The rule it is built around

> Nothing about a rig is believed until it has been evaluated at a sampled time and compared against
> the value the track says it should have. **A clip that exists is not a clip that plays.**

Two bugs in the pre-plugin build each produced a plausible scene with zero motion: eleven clips held
actions, the mixer held state, buttons dispatched, nothing moved. Neither was visible in code review;
both were found only by measuring. Every gate here traces to a failure that was measured, not imagined.

## Contents

| | |
|---|---|
| `tools/rig_*.py` | skeleton, skinning, bind space, mesh parity |
| `tools/anim_*.py` | clip measurement, action design, runtime emission |
| `tools/gate_rigging.py` | one gate row, twelve checks, every verdict reported |
| `reference/` | the derivation, the measured thresholds, and the failure log |

Every threshold is a fraction of **figure height H**, never an absolute unit. Numbers marked
`single-subject` came from one rig and are starting values, not constants.

## Two design decisions worth knowing before reading the code

**One gate row, not twelve.** `img2_core.gate_runner` is sequential and stop-the-line: the first
non-passing blocking row halts the run and the rest are recorded as skipped. Twelve rows would surface
one failure and eleven skips. The aggregate preserves the point of the suite, which is seeing every
violation at once.

**`unevaluated` maps to `error`, and never appears in `status`.** A check whose input is absent is not
a pass. The verdict parser accepts only `pass|fail|error`, and an unrecognised status makes it discard
every reason supplied — so the distinction lives in `reasons` and `evidence` instead. Four of the
twelve checks have no input producer yet, so `error` is the honest verdict on a real run today.

## Tests

```bash
python3 -m unittest discover -s tests
```

`tests/test_oracle_replay.py` is the correctness oracle for the extraction: a byte comparison against
a frozen run on a real 113-node GLB. It is deliberately a byte comparison — a semantic assertion has
to enumerate what matters, and the point of an oracle is to catch the change nobody predicted.

## Publishing to npm

CI and publishing run through the org's shared [`img2threejs/ci-workflows`](https://github.com/img2threejs/ci-workflows) reusable workflows; this repo owns only its triggers and its test command.

1. Bump the version in **both** `plugin.json` and `package.json` — the `ci` workflow's version-sync check fails the build if they disagree.
2. Update `CHANGELOG.md`.
3. Commit the bump.
4. Tag the commit `vX.Y.Z` (matching the new version) and push the tag. A prerelease tag (`v1.2.3-beta.1`) publishes under the matching npm dist-tag (`beta`); a stable tag publishes under `latest`.
5. The shared `npm-publish.yml` workflow re-validates the tag against `package.json` and `plugin.json`, runs this repo's tests in a job with no access to the publish credential, and runs `npm publish --provenance` using the org's `NPM_TOKEN` secret (a granular npm automation token with publish rights on the `@img2threejs` scope, configured once at the org or repo level — no per-repo trusted-publisher setup needed). Re-pushing a tag whose version is already on the registry is a no-op, not a failure.
6. Workflow references in `.github/workflows/` are pinned to a specific `ci-workflows` commit SHA, per that repo's pinning policy.

## Licence

Apache-2.0.
