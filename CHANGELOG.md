# Changelog

All notable changes to **plugin-character** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-09-03

### Added

- **The `animated-character` domain declaration** (`domain.json`): the two character setup steps
  (verbatim base-relative — the static `character` domain stays in-repo and owns those assets) and
  the nine Stage R rig steps, appended after the base's FINAL steps via the registry's `rigSteps`
  vocabulary (harness ≥ 0.2.3). This plugin is now the canonical owner of the rig-step ORDER; the
  two-file pin in `tests/test_domain_declaration.py` guards it, and the freeze-before-bind rationale
  lives in that file's docstring. OpenSpec change: `extract-animated-character` (two-adversary
  review; command deviations from the old in-repo strings are enumerated in its design D4).
- **`gate_rigging.py --payload <path>`** — the checklist-step mode: an explicit payload path with no
  workspace resolution, because the base pipeline's workspace is its checkout, which
  `resolve_workspace` refuses. `--workspace` remains the terminal `gates.json` mode.
- Reference-doc drift pins (content hashes) for the two contract documents `rig-contract-read`
  reads from `{plugin_dir}/reference/`.

### Changed

- **The `rigging` gate is declared `blocking: false`.** Four of its twelve checks have no producer
  yet, an unevaluated check is honestly an `error`, so the gate cannot return `pass` on a healthy
  rig — a blocking declaration would halt any sweep on an honest verdict. **Re-block trigger:** the
  four producers exist and the gate passes the oracle rig. A fail is still recorded in the
  `img2.gate-run` aggregate; it just does not stop it.
- `clip-measure` writes `clip-features.json` (the base step was stdout-only): `--out` is required
  because bare cwd resolution would hit the checkout refusal.
- `plugin.json`: version 0.2.0, `requires.harness: ">=0.2.3"` (the release that admits `rigSteps`).

### Rollback

Reverting to 0.1.0 removes the domain declaration: `--profile animated-character` fails loud naming
the available profiles, and an in-flight workspace is refused until a provider returns — it resumes
unchanged when one does. The base-side module deletion rolls back by `git revert`, not `img2 remove`.

[0.2.0]: https://github.com/img2threejs/plugin-character/compare/5b12a14...v0.2.0
