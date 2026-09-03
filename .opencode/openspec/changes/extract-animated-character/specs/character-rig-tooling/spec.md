# Capability: character-rig-tooling

## ADDED Requirements

### Requirement: gate_rigging accepts an explicit payload path

`gate_rigging.py` SHALL accept `--payload <path>`, read the payload from that path without calling
`resolve_workspace`, and keep its existing `--workspace` fixed-path mode unchanged for the
terminal `gates.json` invocation.

#### Scenario: payload mode works from a checkout cwd

- WHEN the tool runs with `--payload rig-gate-payload.json` from a directory containing SKILL.md
- THEN it SHALL evaluate the payload and emit one `img2.gate-verdict`, never a
  checkout-refusal error.

#### Scenario: missing payload is named

- WHEN `--payload` points at a non-existent file
- THEN the tool SHALL emit an `error` envelope naming that path and exit 2.

### Requirement: Step tools bypass workspace resolution via --out

Every rig step invocation in `domain.json` SHALL pass an explicit `--out <name>` (or `--payload`),
so no step tool reaches `resolve_workspace` — whose checkout refusal the base pipeline's
checkout-as-workspace layout cannot satisfy.

#### Scenario: a step tool never hits the checkout refusal

- WHEN each declared rig command runs from the base checkout root
- THEN no tool SHALL exit with the "looks like a skill or plugin checkout" error.

### Requirement: clip-measure writes a named artifact

`anim_clip_features.py`, invoked per the declared step with `--out clip-features.json`, SHALL write
the measurement artifact to that workspace-relative path; the deviation from the base's stdout-only
behavior SHALL be recorded in the D4 table and release notes.

#### Scenario: the artifact lands at the declared name

- WHEN the clip-measure step runs on a valid sampled-clips payload
- THEN `clip-features.json` SHALL exist at the workspace root and carry the loop decision.

### Requirement: Installed-copy evidence is captured

Release acceptance SHALL include, from inside `~/.img2/plugins/character`: the plugin test suite
green, `img2 doctor` clean, and a run of the rig_spec drift-pin tests with `IMG2THREEJS_BASE` set so
they execute rather than skip.

#### Scenario: the drift pin actually runs

- WHEN the plugin suite runs with `IMG2THREEJS_BASE` pointing at the base checkout
- THEN the nine rig_spec drift-pin tests SHALL execute (zero of them skipped) and pass.
