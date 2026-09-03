# Capability: animated-character-domain

## ADDED Requirements

### Requirement: The declaration is doctor-clean

The plugin SHALL ship a `domain.json` with id `animated-character` that `img2 doctor` accepts with
zero findings on a harness ≥ 0.2.3, and the harness SHALL validate `rigSteps` rows with the same
placeholder and angle-bracket checks as other rows, anchor-exempt.

#### Scenario: doctor accepts the installed plugin

- WHEN the plugin is installed via `img2 add` on a harness that knows `rigSteps`
- THEN `img2 doctor` SHALL exit 0 with no finding naming `character`.

#### Scenario: an anchor is not demanded for rigSteps

- WHEN `domain.json` declares non-empty `rigSteps` and no `rigAnchorBefore`
- THEN doctor SHALL NOT report a missing-anchor finding for it.

### Requirement: Structural checklist parity is byte-equal

`new_state` with profile `animated-character` SHALL produce a checklist whose `(scope, id)` sequence
is identical to the sequence produced by the in-repo module at the pre-deletion base commit, with
`final/plugin-gates` preceding the nine `rig` rows.

#### Scenario: the parity capture matches

- WHEN the `(scope, id)` list is captured before (in-repo module) and after (plugin installed,
  module deleted)
- THEN the two lists SHALL be identical.

### Requirement: Command deviations are exactly the enumerated allow-list

Every checklist `command` string that differs from the in-repo module's SHALL appear verbatim in
design D4's deviation table, and a differing row absent from that table SHALL fail the parity check.

#### Scenario: an unlisted deviation fails

- WHEN the command diff contains a row not in the D4 table
- THEN acceptance A2 SHALL fail naming that row.

### Requirement: The rigging gate is not due before the rig track

`run_gates.py` SHALL treat a plugin whose domain declares `rigSteps` as not due until at least one
declared rig step is `done`; the gate sweep at `plugin-gates` SHALL neither stop the run nor record
a `rigging` verdict while the rig scope is untouched.

#### Scenario: plugin-gates passes pre-rig

- WHEN `run_gates.py` runs on a workspace at the `plugin-gates` step with the plugin installed and
  every rig step pending
- THEN the run SHALL NOT report `stopped: true` and no `rigging` verdict SHALL be emitted.

#### Scenario: a post-rig invocation evaluates the gate once

- WHEN `run_gates.py` runs after a rig step is done and
  `rig-gate-payload.json` exists at the declared path
- THEN the `rigging` gate SHALL be evaluated exactly once, producing a `pass` or `fail` verdict,
  never `error: payload not found`.

### Requirement: The rigging gate is declared non-blocking until it can pass

`gates.json` SHALL declare `rigging` with `blocking: false`, and the re-block trigger (the four
producer-less checks gain producers and the gate can return `pass` on a healthy rig) SHALL be
recorded in the plugin CHANGELOG and SKILL.md.

#### Scenario: an honest non-pass does not halt the aggregate

- WHEN the gate reports `fail` or `error` in an `img2.gate-run` sweep
- THEN the aggregate SHALL NOT set `stopped: true` on its account.

### Requirement: Absence fails loud and recovery is lossless

Without the plugin installed, `state.py init --profile animated-character` SHALL fail naming the
available profiles; an existing animated-character workspace SHALL be refused while the provider is
absent and SHALL resume at the same step with `passHistory` unchanged after reinstall.

#### Scenario: removal round-trip

- WHEN `img2 remove character` is followed by a `next.py` call and then `img2 add` restores it
- THEN the intermediate call SHALL fail naming the missing provider and the post-reinstall call
  SHALL resume at the same step with `passHistory` byte-identical.

### Requirement: The plugin owns the rig order with a two-file pin

The plugin's `domain.json` SHALL be the canonical rig-step order, pinned by plugin tests asserting
its ids against a separately declared expected list, preserving: contract-read first, repair before
freeze, freeze before payload-validate and bind, bind before parity-verify, gates last.

#### Scenario: a reorder trips the pin

- WHEN any two rig rows in `domain.json` are swapped
- THEN at least one plugin order test SHALL fail.

### Requirement: The base pins its side of the shared surface

The base SHALL keep dispatcher-mechanism tests against a fixture domain, add a skip-with-reason test
reading the installed plugin's `domain.json` order when present, and add an agreement test asserting
the two base-relative setupStep paths (`grimoire/character/*`, `extract_landmarks.py`) exist.

#### Scenario: a moved base asset trips the agreement test

- WHEN `forge/stage1_intake/extract_landmarks.py` is renamed
- THEN the base agreement test SHALL fail naming the missing path.

### Requirement: Reference-doc copies are drift-pinned

The plugin's `reference/` copies of the animation contract and pipeline doc SHALL be pinned against
recorded content hashes, so divergence from the recorded content fails a plugin test rather than
passing silently.

#### Scenario: an edited copy trips the pin

- WHEN `reference/animation-contract.md` changes without the pin being re-recorded
- THEN the drift test SHALL fail.
