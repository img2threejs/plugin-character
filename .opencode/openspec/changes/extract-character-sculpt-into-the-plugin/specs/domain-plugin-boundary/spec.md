# domain-plugin-boundary

What separates the base skill from a domain plugin, and what must be true of a domain that has been
extracted out of the base.

## MODIFIED Requirements

### Requirement: Extracted domain behaviour SHALL be unchanged

The extracted plugin SHALL produce the same output as the pre-extraction base for the same input.
Equality SHALL be asserted by an executable test rather than by inspection. Where no completed
reference run exists to serve as the oracle, a frozen input and its frozen expected output SHALL be
captured from the pre-extraction base and SHALL serve as the oracle, and the path SHALL be verified
deterministic before the frozen output is trusted.

An oracle SHALL cover the stage that is moving. An oracle whose input is downstream of the extracted
work is blind to it by construction: freezing an already-authored artifact and replaying it through
machinery that never left proves only that the machinery still runs, and stays green when everything
upstream of the frozen artifact has been removed. Where an extraction moves the authoring of an
artifact, the oracle SHALL start from the inputs the authoring consumes, not from the artifact it
produces.

#### Scenario: The oracle replays byte-identically

- **WHEN** the extracted plugin is run against the oracle's frozen input
- **THEN** its output SHALL be byte-identical to the frozen expected output

#### Scenario: Determinism is established before the output is frozen

- **WHEN** an output is captured as an oracle fixture
- **THEN** repeated runs on the same input SHALL have been shown to produce identical output
- **AND** the path SHALL contain no unseeded non-deterministic source

#### Scenario: The oracle runs before and after extraction

- **WHEN** the oracle is established
- **THEN** it SHALL pass against the pre-extraction base
- **AND** it SHALL pass again once the plugin is installed

#### Scenario: The oracle's input is upstream of the moving stage

- **WHEN** an extraction moves the code that authors an artifact
- **THEN** an oracle SHALL exist whose input is what that authoring consumes
- **AND** deleting the moved authoring SHALL make that oracle fail

### Requirement: The collected count SHALL be the asserted floor, not the run count

The number of tests **collected** SHALL be asserted against a recorded floor, because a suite can
report success while tests silently fail to run. The run-versus-skipped split SHALL NOT be used as a
floor: it depends on which optional toolchains are present, so the same tree yields different splits
on different machines and a run-count floor would fail for an environment reason rather than a defect.

The floor SHALL be the measured collected count, not a number below it. Slack between the floor and
the real count is the size of the loss the check cannot see: a floor 261 below its tree absorbed 100
deleted tests without failing. Every movement of the floor SHALL record its arithmetic — the count
before, what moved out, what was added, the count after — with both counts measured in the same
sitting, by the same runner.

#### Scenario: A dropped test module fails the check

- **WHEN** a test module stops being collected
- **THEN** the integrity check SHALL fail
- **AND** the failure SHALL name the shortfall against the recorded floor

#### Scenario: A class-level setup failure is not read as a pass

- **WHEN** a test class raises during class-level setup
- **THEN** the check SHALL account for every test method that did not run

#### Scenario: A differing run/skip split is not a failure

- **WHEN** the same tree is run on an environment lacking an optional toolchain
- **THEN** the collected count SHALL match the recorded floor
- **AND** the differing run and skipped counts SHALL NOT fail the check

#### Scenario: Every skip carries a reason

- **WHEN** a test is skipped
- **THEN** the skip SHALL state a reason
- **AND** a skip whose reason is a missing plugin SHALL fail the check

#### Scenario: The floor is set to the measured count

- **WHEN** a floor is recorded or moved
- **THEN** it SHALL equal the count measured in that sitting
- **AND** the accounting for the movement SHALL be recorded with it

#### Scenario: Tests relocated by an extraction arrive somewhere

- **WHEN** an extraction removes test modules from one tree
- **THEN** the same tests SHALL be collected in the tree that received them
- **AND** both floors SHALL be re-measured and recorded in the same sitting

#### Scenario: A retained module referencing a removed one fails the check

- **WHEN** a module the extraction removes is referenced from anywhere in the retained tree
- **THEN** the check SHALL fail, naming the reference
- **AND** the check SHALL cover references inside function and method bodies, and the test tree, not
  only module-scope references in production code
- **AND** a collected-count assertion SHALL NOT be relied on to detect this, because a reference that
  fails at run time leaves the count unchanged

#### Scenario: Skip reasons are asserted by a test, not by a reader

- **WHEN** the suite's integrity check runs
- **THEN** it SHALL inspect the reason attached to every skip
- **AND** a skip carrying no reason, or a reason naming a missing plugin, SHALL fail it
- **AND** this SHALL NOT be discharged by a human reading the run output

#### Scenario: Two providers claiming one domain id is refused

- **WHEN** an in-repo domain and an installed plugin both declare the same domain id
- **THEN** resolution SHALL refuse, naming the duplicated id
- **AND** the refusal SHALL NOT be scoped to the colliding profile alone, since the registry cannot
  be read at all in that state
