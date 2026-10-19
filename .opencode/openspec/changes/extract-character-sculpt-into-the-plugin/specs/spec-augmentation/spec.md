# spec-augmentation

The declared artifact a domain plugin publishes so the base can raise its own quality floors, and the
merge rule that keeps a plugin from weakening a base gate.

## MODIFIED Requirements

### Requirement: The base SHALL pull; a plugin SHALL NOT push

A plugin SHALL publish a declared-kind artifact. The base SHALL read it at a defined point in spec
authoring. A plugin SHALL NOT write into base pipeline state or into the base's own spec output.

The artifact SHALL be authored independently of the base's spec output: the tool that emits it SHALL
NOT take the authored spec as an input. A domain that reads the base's spec in order to write its own
sections has made the base's output an input to the artifact the base then merges back, which is the
push relationship inverted rather than avoided, and it forces a second authoring pass whose only
purpose is to consume what the first produced. A section the domain contributes SHALL therefore be
authored complete, from the domain's own knowledge and the evidence its own steps produced.

#### Scenario: The base reads the artifact at the defined point

- **WHEN** a resolved domain provider has published a spec-augmentation artifact
- **THEN** the base SHALL read it after authoring the spec and before serialising it

#### Scenario: A plugin writing base state is refused

- **WHEN** a plugin attempts to write into the base pipeline's state file
- **THEN** the write SHALL be refused
- **AND** the run SHALL report the refusal rather than continuing silently

#### Scenario: The emitting tool does not read the authored spec

- **WHEN** the tool that emits the artifact is inspected
- **THEN** it SHALL NOT accept the base's authored spec as an input
- **AND** one authoring pass SHALL be sufficient for the base to merge the artifact

#### Scenario: A contributed section is authored complete

- **WHEN** a domain contributes a section the base also populates
- **THEN** the contributed value SHALL carry every field the base's own value would have carried
- **AND** the merge SHALL NOT be relied on to preserve fields the contributed value omitted

#### Scenario: A contributed list carries the base's own elements

- **WHEN** a contributed section is a list the base also populates
- **THEN** it SHALL carry every element the base's own value would have carried
- **AND** an element the base authored SHALL NOT be dropped by the contribution replacing the list

### Requirement: The artifact SHALL carry only base-owned schema paths

The artifact SHALL be limited to paths the base schema already defines and to values in base
vocabulary. Domain taxonomy values and the domain marker SHALL NOT be carried in it. A section that is
merely absent from the base-owned exclusion set SHALL NOT thereby be treated as safe to admit
opaquely: the authority over each such section SHALL be stated rather than left to follow from the
exclusion set's silence. (Validating a base-consumed section's values against the set the base
implements shipped in `40f73b5` — `test_pass_identifier_authority.py` pins it; the scenarios are not
duplicated here.)

The statement of authority SHALL live **in the module that implements the merge**, so that it is a
named artifact at a known path rather than prose in a design document, and SHALL name each admitted
section rather than describing the class of them. A section admitted with no stated authority SHALL
be treated as an unresolved question, not as a permission. The correspondence between the ruling and
what providers actually send SHALL be asserted executably: a provider's own suite SHALL check that
every section its artifact carries is named in the ruling, so that adding a section without ruling on
it fails a test rather than passing unnoticed.

#### Scenario: An unknown key is refused, not ignored

- **WHEN** the artifact contains a key outside the permitted set
- **THEN** the merge SHALL fail with an error naming the key
- **AND** the unknown key SHALL NOT be silently dropped

#### Scenario: The domain marker is not accepted from the artifact

- **WHEN** the artifact attempts to set the resolved-domain field
- **THEN** the merge SHALL refuse
- **AND** the field SHALL be set only by domain resolution

#### Scenario: Authority over each admitted section is stated

- **WHEN** a section is admitted through the artifact
- **THEN** whether a plugin may write it SHALL be explicit in the ruling that ships with the merge
- **AND** admission SHALL NOT be inferred from the section's absence from the exclusion set

#### Scenario: A section absent from the ruling fails a provider's own suite

- **WHEN** a provider emits an artifact carrying a `specSections` key the ruling does not name
- **THEN** that provider's suite SHALL fail, naming the unruled section
- **AND** the failure SHALL occur before the provider is released, not when the section is merged

#### Scenario: The ruling and the merge cannot drift apart

- **WHEN** the ruling is read
- **THEN** it SHALL be located in the module implementing the merge
- **AND** a section may be added to the exclusion set or to the ruling only together with the other
