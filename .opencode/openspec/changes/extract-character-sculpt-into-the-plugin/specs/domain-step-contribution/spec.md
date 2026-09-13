# domain-step-contribution

How a resolved domain's steps enter the base checklist, and what a profile identifier means once the
set of them is open.

## MODIFIED Requirements

### Requirement: The profile set SHALL be open, and existing state SHALL survive opening it

The base SHALL accept a profile identifier supplied by a resolved domain provider rather than
validating against a closed literal set. Opening the set SHALL NOT invalidate state files written
before the change.

A profile identifier that a release withdraws SHALL fail loud and name what replaces it. Withdrawing
a profile is a breaking change to the identifier a user typed and a state file recorded, so the
refusal SHALL be as informative as the install-time refusal for a missing provider: it SHALL name the
withdrawn identifier, name its successor, and state the remedy. It SHALL NOT silently resolve to the
successor, because a profile carries a different step set and a run that silently changed step sets
would produce evidence under a name that never ran.

#### Scenario: A pre-existing run remains loadable

- **WHEN** a state file written before this change carries a domain profile that is no longer a base
  literal
- **THEN** loading it SHALL succeed
- **AND** the run SHALL remain resumable

#### Scenario: A state schema migration accompanies the change

- **WHEN** the profile set is opened
- **THEN** a state schema version bump and a profile rewrite SHALL ship in the same change

#### Scenario: An unresolvable profile fails loud

- **WHEN** a state file names a domain profile whose provider is not installed
- **THEN** loading SHALL fail with an error naming the missing provider
- **AND** it SHALL NOT silently downgrade the run to the generic profile

#### Scenario: A withdrawn profile names its successor

- **WHEN** a run or a state file names a profile identifier a release has withdrawn
- **THEN** the refusal SHALL name the withdrawn identifier and the profile that replaces it
- **AND** it SHALL state the remedy
- **AND** it SHALL NOT resolve the run to the successor on its own

#### Scenario: The refusal comes from the resolver, not from argument parsing

- **WHEN** a withdrawn or unresolvable profile is supplied on the command line
- **THEN** the refusal SHALL be produced by domain resolution
- **AND** it SHALL NOT be produced by argument parsing, which cannot name a provider, a successor or
  a remedy
- **AND** the command line and the resume path SHALL produce the same refusal for the same profile

#### Scenario: A withdrawal is announced where the identifier is published

- **WHEN** a profile identifier is withdrawn
- **THEN** the release notes SHALL record it as a breaking change
- **AND** every document that taught the withdrawn identifier SHALL be updated in the same release
