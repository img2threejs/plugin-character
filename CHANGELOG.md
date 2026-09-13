# Changelog

All notable changes to **plugin-character** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-09-13

This plugin now serves the WHOLE character track, not the rig half of it. The base authors a generic
skeleton spec; the humanoid decomposition, its derived rig, its materials and its build passes are
authored here and pulled at `spec-authoring`.

OpenSpec change: `extract-character-sculpt-into-the-plugin` (two-adversary review, plus an
independent partition review that rebutted four of seven questions as malformed).

### Added

- **`tools/character_spec_template.py`** — the humanoid track, moved from the base's
  `stage2_spec/new_sculpt_spec.py`: component tree, derived rig, materials, build passes, feature
  review targets. It authors into an EMPTY dict, so the sections it produces are complete rather
  than patches. It carries `BASE_DEFAULT_MATERIAL`, a pinned copy of the base's generic material,
  because the `materials` section is replaced wholesale and a provider that wants the base's default
  must supply it.
- **`tools/emit_spec_augmentation.py`** — publishes that as a `spec-augmentation-v1` artifact. It
  takes **no `--spec`**: the base pulls, and a tool that read the base's output and handed it back
  would invert the relationship rather than avoid it. `tests/test_spec_augmentation_artifact.py`
  asserts that from argparse, not from `--help`, which reads this docstring too.
- **`tools/humanoid_proportions.py`** — figure-drawing canon for a reference-free figure, moved from
  the base. Canon is labelled as canon; a head count the tables do not cover is refused rather than
  interpolated.
- **`grimoire/character/`** — four pages (`reconstruction`, `likeness_maximization`,
  `structure_decomposition`, `head_construction`). The two hair pages stay in the base: hair is not
  extracted by this change.
- **`spec_search_profile.json`** declaring the `character` collection, and
  `specCollection: "character"` in `domain.json`. `specCollection` REPLACES the collection searched
  rather than adding one, so `docs/specs/vocabulary/` carries byte-identical copies of the base's
  `core_3d` records — without them a character run would search LESS than a generic one, silently.
  What the collection adds is `grimoire/character/`, which no collection ever indexed.
- **`image → character-sculpt-spec`** in `plugin.json`. **This edge is discovery-only.** Capability
  edges are resolved by `img2 capabilities` and listed in the generated `routes.json` and
  `index.md`; nothing in the base pipeline reads them at runtime — the runtime path is `domain.json`,
  for every plugin including cs2. Recorded here rather than left to be discovered, because a
  declaration with no runtime caller was the withdrawn attempt's central defect and this one is
  deliberate.
- Tests moved with their subjects — `test_character_rig_derivation` (13) and
  `test_humanoid_proportions` (9). Only assertions that genuinely span both repos need a base
  checkout, and they skip with a reason naming `IMG2THREEJS_BASE`.
- `validate_rig_admission` is now asserted to pass on this plugin's submission. `rig` is not in the
  base's `BASE_OWNED`, so a plugin writes it wholesale and the merge admits it opaquely; those five
  checks are the base's only look at it, and nothing had ever run them on plugin-authored content.

### Changed

- **`domain.json` declares `id: "character"`.** See Removed.
- `character-contract-read` names `{plugin_dir}/grimoire/character/...`. The withdrawn attempt
  shipped it base-relative, which dangles the moment the pages move — and dangles silently, because
  a checklist step is spliced as text for an agent to read, not executed.
- `setupSteps` gains `character-spec-augmentation`, listed after `character-landmarks` because it
  reads `anatomy.json`, which that step writes. Ordering inside the group; the anchor does not buy it.
- `SKILL.md` describes the whole track; frontmatter version moves with `plugin.json`.
- `COLLECTED_FLOOR` 235 → 326, **corrected rather than raised**: 0.2.0 declared 235 while collecting
  258, so 23 tests could have stopped being collected with nothing going red. The arithmetic is
  written down in `tests/test_suite_integrity.py`.

### Removed

- **The `animated-character` profile is withdrawn.** One id now. A second profile that omitted the
  Stage R gates entirely is how animation shipped broken in 1.5.1; a static build skips a rig step
  with a recorded reason, which the checklist already supports.

### Rollback

Base and plugin roll back TOGETHER or not at all. 0.2.0's `domain.json` declares
`animated-character` and reads `grimoire/character/reconstruction.md` base-relative — files this
change's base half deletes. Reverting only the plugin leaves a user with no `character` profile and
a broken `animated-character` one. `img2 remove character && img2 add img2threejs/plugin-character
--ref v0.2.0` is the plugin lever; `git revert` on the base commit is the other, and it is a
developer's lever — a user who installed the skill normally has no such checkout.

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
