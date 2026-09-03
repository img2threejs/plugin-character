# Tasks: extract-animated-character

Release order is load-bearing: §1 (harness) → §2 (plugin) → §3 (base) → §4 (acceptance).

## 1. img2-harness (prerequisite — ships first as 0.2.3)

- [ ] 1.1 Add `rigSteps` to `DOMAIN_JSON_ALLOWED_KEYS` (bin/img2.mjs:879) and fix the "mirrors
      `_ALLOWED` exactly" comment's claim by making it true again.
- [ ] 1.2 Wire anchor-exempt row validation for `rigSteps` (placeholder + angle-bracket + metachar
      checks per row; NO missing-anchor finding — rig rows have no anchor by design).
- [ ] 1.3 Tests: a domain.json with rigSteps passes doctor; a rigSteps row with `<x>` or `&&` in a
      command row fails; no anchor demanded.
- [ ] 1.4 `docs/PLUGIN_CONTRACT.md` §10: document `rigSteps` (appended after FINAL, no anchor).
- [ ] 1.5 CHANGELOG + version 0.2.3; push + tag; update installed harness.

## 2. plugin-character (v0.2.0)

- [ ] 2.1 `tools/gate_rigging.py`: add `--payload <path>` (no `resolve_workspace` on that branch);
      keep `--workspace` mode for gates.json; tests for both modes incl. checkout-cwd and
      missing-payload scenarios.
- [ ] 2.2 `domain.json`: id `animated-character`; the two setupSteps verbatim base-relative with
      `setupAnchorBefore: local-spec-search`; the nine rigSteps exactly as design D4's table.
- [ ] 2.3 `gates.json`: `rigging` → `blocking: false`; re-block trigger recorded in CHANGELOG and
      SKILL.md.
- [ ] 2.4 Order tests: port the six StageROrderIsLoadBearing assertions against `domain.json` ids
      with a separately declared expected list (two-file pin); move the freeze-before-bind
      rationale into their docstrings and SKILL.md.
- [ ] 2.5 Drift pins: `reference/animation-contract.md` and
      `reference/character-rigging-animation-1.5.2.md` pinned by content hash.
- [ ] 2.6 Declaration guard tests: domain.json parses; rig rows carry `--out`/`--payload`; setup
      rows are the two expected base-relative strings.
- [ ] 2.7 Docs: create `CHANGELOG.md` (cs2 release discipline); SKILL.md — payload location
      (`rig-gate-payload.json` at the workspace root for the step; the fixed
      `.img2/artifacts/character/` path for the terminal mode), cwd contract, re-block trigger;
      SKILL.md frontmatter version moves with plugin.json.
- [ ] 2.8 `plugin.json`: version 0.2.0, `requires.harness: ">=0.2.3"`.
- [ ] 2.9 Raise `tests/test_suite_integrity.py` floor (227 → new count: ____).
- [ ] 2.10 Release: tag v0.2.0, push, `img2 add img2threejs/plugin-character`; `img2 doctor` clean.

## 3. img2threejs (base branch; record the exact base commit here: ____)

- [ ] 3.1 `run_gates.py`: rig-aware participation — a domain declaring `rigSteps` is due only when
      ≥1 rig step is `done`; test: sweep at plugin-gates with rig pending neither stops nor records
      a rigging verdict; post-rig sweep evaluates it once.
- [ ] 3.2 `forge/state.py:32`: guard argparse-time `registered_domains()` (DomainRegistryError →
      generic-only choices); test: a colliding fixture home still allows `state.py status` on a
      generic workspace.
- [ ] 3.3 Delete `forge/_shared/domains/animated_character.py`.
- [ ] 3.4 `test_rig_workflow_steps.py` rework per the 21-method disposition (design D5): dispatcher
      class → fixture home with a fixture rigSteps domain; six order tests removed with a comment
      naming the plugin as order authority; new skip-with-reason installed-plugin order test; the
      six AnimatedCharacterProfile tests → fixture; prose-pin test survives via D4's preserved
      string.
- [ ] 3.5 New base agreement test: the two setupStep-referenced paths exist
      (`grimoire/character/reconstruction.md` + `likeness_maximization.md`,
      `forge/stage1_intake/extract_landmarks.py`).
- [ ] 3.6 `test_domain_registry.py`: expectations back to `["character"]` (+ fixture variants).
- [ ] 3.7 Doc sweep (design D7 table): README:94,140,270-272; SKILL.md:65,77,81-83,300-303;
      GLB_ANIMATED_CHARACTER_PROMPT.md; STAGE_R_TEST_PLAN.md; STAGE_R_BACKLOG.md:96,251;
      standard-prompts/build.md:21; ARCHITECTURE.md:145-152 — every runnable example states the
      plugin prerequisite; stage5_rig demoted to library status.
- [ ] 3.8 CHANGELOG entry (breaking: plugin prerequisite; frozen-checklist note with remedy);
      raise `forge/tests/test_suite_integrity.py` floor (1192 → ____).
- [ ] 3.9 Full base suite green.

## 4. Acceptance captures (design D8; all ten, machine-checkable)

- [ ] 4.1 A1 structural parity byte-equal (before/after `(scope,id)` capture).
- [ ] 4.2 A2 command diff == D4 allow-list exactly.
- [ ] 4.3 A3 `img2 doctor` clean output captured post-install.
- [ ] 4.4 A4 `run_gates.py` at plugin-gates, rig untouched: no stop, no rigging verdict.
- [ ] 4.5 A5 post-rig gate evaluated once with a real payload (pass/fail, not error).
- [ ] 4.6 A6 dispatcher drain through the nine rig steps on the installed plugin.
- [ ] 4.7 A7 fail-loud capture without the plugin.
- [ ] 4.8 A8 removal round-trip: refusal names the provider; resume unchanged after reinstall.
- [ ] 4.9 A9 both suites green with the rig_spec drift pins EXECUTED (`IMG2THREEJS_BASE` set) and
      the plugin suite run from inside `~/.img2/plugins/character`.
- [ ] 4.10 A10 doc-sweep grep: every `animated-character` hit states the prerequisite or is
      historical.

## 5. Tracked follow-ups (filed, not implemented here)

- [ ] 5.1 Base-owned post-rig gate sweep row (reviewers' option (b)) — trigger for re-evaluating
      the sweep placement and re-blocking.
- [ ] 5.2 Re-block `rigging` when the four producer-less checks gain producers.
- [ ] 5.3 cs2 `steps.json` = `[]` debt (revisit when a rig/cs2 edge becomes an emission target).
- [ ] 5.4 Harness workspace-confinement vs checkout-as-workspace incompatibility.
- [ ] 5.5 stage5_rig dedup when the factory's rig imports move behind a core API.
