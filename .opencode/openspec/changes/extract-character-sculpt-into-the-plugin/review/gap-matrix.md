# Gap matrix — round 1

Two independent adversarial reviewers, 2026-09-12, against the change as first written.
Reviewer A: architecture. Reviewer B: delivery. Neither was given the lead's conclusions.

**Every finding below was re-measured by the lead before being accepted.** None was taken on the
reviewer's word, and none needed rebutting — the disagreements that would have been worth debating
did not arise, because all sixteen reproduce.

## HIGH

| # | Finding | Evidence | Decision | Artifact updated |
|---|---|---|---|---|
| A1/B1 | Plugin baseline "235 collected" is `COLLECTED_FLOOR` transcribed from `test_suite_integrity.py:35` and mislabelled measured | `--collect-only` on a clean `v0.2.0` extract → **258** (226 passed, 32 skipped) | accept | design baseline; tasks measurement rules; 1.8 now *corrects* the floor rather than raising from it |
| A2/B2 | Base baseline "1387" is the **passed** count; task 3.9 seeded floor arithmetic from it, two lines under "assert collected, never the run count" | `--collect-only` on `main` → **1453**. `pytest -q` never prints collected | accept | tasks measurement rules; 3.9 |
| A2b | The floor moves **up**, not down — 1192 against 1453 is 261 of slack, so post-move ~1353 is ~161 above today's floor. "Lower it" preserves the slack | measured | accept | 3.9 verb changed to *set*; D6 slack corrected 169 → 261 |
| A3 | Slice ordering breaks **every non-generic profile**: installing a plugin declaring `character` while the base still declares it raises `declared twice` from `registered_domains()`, which takes the whole registry down — `domain_profile('cs2')` raises too | reproduced in a synthetic `IMG2_HOME`: registry error, cs2 error, `--profile` degraded to generic-only | accept | ordering invariant added; `img2 add` and every installed-state capture moved to the end of slice 3 |
| A4/B4 | **"No base or harness code change is required" is false.** `state.py:37-40` uses argparse `choices=`, so init refuses before `domain_profile()` can name the provider. Init and resume give different answers today | `state.py init --profile cs2` → `invalid choice`; resume path → the good message | accept | proposal item 4 split into the true and false halves; `state.py` and `domains/__init__.py` added to §Affected code; design **D8**; tasks 3.3a, 3.3b |
| B3 | The withdrawn-profile requirement has no implementing task, and the live remedy becomes false — *"Install the domain plugin that provides it"* when nobody will | `rg successor tasks.md` → 0 hits | accept | tasks 3.3b, with a test per scenario |
| B5 | The authoring oracle must fail after 3.2 per the spec delta, while 3.10 demands zero failures — and no task gives it a home | contradiction between `domain-plugin-boundary` and 3.10 | accept | D6: it lives in the **plugin's** suite from the moment it is frozen; 0.5 says so |
| B6 | `img2 doctor` **FAILs today**; the installed clone carries 12 untracked files from the withdrawn attempt, and `scalp_exposure.py` needs `--workspace`, not just a bootstrap stanza | `img2 doctor` → 1 failure; `git status` in the clone → 12 `??`; none in `v0.2.0` | accept | tasks 1.4 (workspace-resolving tools), 3.10a (clean the clone before any capture) |
| B7 | 0.2's sweep is a node-type allowlist that misses function-scoped `ImportFrom` — `test_stand_proud_emission.py:204,228` errors after 3.6 while still being collected, so the floor never moves | measured | accept | 0.2 rewritten: grep the module name, then classify |
| B8 | The doc sweep covers 3 of 10 files teaching `animated-character`, and 4.4's machine check is path-only so it cannot see `--profile animated-character` | `rg -c` across `6e60b5e` | accept | 4.3a dispositions the seven; 4.4 becomes a test with the identifier grep beside the path check |

## MEDIUM

| # | Finding | Decision | Artifact updated |
|---|---|---|---|
| M1 | The slice-0 gate is the predecessor's ignored sentence with bolder formatting; nothing can enforce it | accept — **the single highest-leverage change in the review** | 0.3a: a base test asserting the review artifact exists, which 3.10 and 5.4 already force to run |
| M2 | design described `test_character_oracle_replay.py` as existing; it exists only on the abandoned branch | accept | D6 rewritten: there is no character oracle on `main`; this change freezes two |
| M3 | Rollback rehearses the case that cannot occur, names three links when there are four, and all four point at `img2threejs-beta` | accept | 6.1 rewritten with the post-release command; 6.1a: base and plugin roll back together |
| M4 | 3.7 is an instruction to itself — "name each one" with none named | accept | 3.7 populated; the list is slice-0 work |
| M5 | The capability edge has nothing behind it; cs2 ships a `steps.json`, this plugin ships none | accept | 2.4 must state what backs the edge before adding it |
| M6 | 3.8 reverses a documented decision in one line with no rationale | accept | design **D9**; 3.8 names the replacement test rather than deleting the assertion |
| M7 | "Zero findings" is contradicted by a WARN this change makes permanent | accept | A3, 3.11, 5.3: the bar is zero **FAIL**s |
| M8 | "Publish" is unreachable — no `package.json` at `v0.2.0`, and no `@img2threejs` package exists on npm | accept | 5.3: publish means the git tag; npm is a separate change |

## LOW

| # | Finding | Decision | Artifact updated |
|---|---|---|---|
| L1 | Doc line references were not re-measured while code references were (`:170`→`:168`, `:296`→`:293`) | accept | 4.1 |
| L2 | D2's "one docstring line" is four sites, and the one named is a runtime message | accept | folded into 0.2's rewrite — all four are path strings the identifier sweep cannot see |
| L3 | A11 names no artifact, and two of its steps invoke `runtime/scripts/export_mesh_buffers.mjs`, which is not in the repo | accept | A11 names the emitted TypeScript and its markers; 5.11a blocks A11 until the script is located |
| B-c5 | The harness working tree sits on an abandoned branch leaving `PLUGIN_CONTRACT.md:458-467` garbled | accept | 7.2 extended to close out all three abandoned branches |

## Requirements that could not fail, now made falsifiable

`spec-augmentation`'s "Authority over each admitted section is stated" and its companion described a
**document**, not observable behaviour — no test could assert them. Rewritten: the ruling lives in
the module implementing the merge, and a provider's own suite fails when its artifact carries a
`specSections` key the ruling does not name. Tasks 1.7 and 1.7a implement both halves.

Reviewer B's one unqualified endorsement is recorded as well: `domain-plugin-boundary`'s
"Determinism is established before the output is frozen" is already mechanical, and task 0.6 is
called the strongest verification task in the plan.

## Round 1b — reviewer A part 2

| # | Finding | Evidence | Decision | Artifact updated |
|---|---|---|---|---|
| A-H5.1 | `materials` is a merge producing **nine** materials led by the base's own `base`, thirteen with accessories (four accessory entries, not three). `specSections` assigns wholesale, so a contributed array drops `base` | measured: `['base','hidden','skin','hair','shirt','pants','shoes','eye','lips']` | accept | D3 extended; task 1.2 |
| A-H5.2 | `objectClass.primaryDomain` is written by the template and hard-required by `validate_sculpt_spec.py:904`; only the canon anatomy was named as travelling through `assessmentPatch` | measured | accept | D3; task 1.3 |
| A-H5.3 | `--accessories` loses its switch with no plugin-side replacement | task 3.3 deletes it | accept | new task 1.3a |
| A-H6 | **The floor has a blind spot.** `test_stand_proud_emission` imports `scalp_field` inside two test bodies; with the module gone `--collect-only` still reports 31 while the run reports 2 failed | reproduced on the lab branch | accept | D6: the RUN is the primary gate, the floor a second check for a different loss; task 3.10 |
| A-H6b | That pin reopens the partition: the base keeps the emitted `ringStackDistance` and is pinned against the Python `ScalpField` | `generate_threejs_factory.py:1429` is signed distance to an ellipse-ring stack, driven by the base schema field `standProud`; nothing humanoid | accept | **D10**: `scalp_field.py` **stays**; `scalp_exposure.py` still leaves. Tasks 1.4, 3.7 |
| A-H7 | `img2 doctor` "zero findings" is unreachable — the WARN is mandated by §12 — and the live FAIL is on `scalp_exposure.py:40`, which task 1.4 would not have removed | measured | accept | bar is zero FAILs; 1.4 says delete the line |

**D10 is the round's deepest correction.** The withdrawn attempt's `partition.md` classified
`scalp_field.py` as content by reading its docstring, which recounts a hair defect as *motivation*.
The docstring says why the file was written; the code says what it knows. That is exactly the test
the partition itself prescribes — *what does the symbol KNOW?* — and it was applied to the wrong
text. The maths stays; the gate goes.

## Rounds 1c–1e — reviewer A parts 3–9

Nine parts in all, and twelve across both reviewers — reviewer B delivered its report in three
(H1–H6; H7–H8 and M1–M8; L1–L3 with the contradictions, the unfalsifiable criteria and its bottom
line). B's findings are folded into the round-1 table above under dual ids (`A1/B1`, `A2/B2`), which
is why they are not separately enumerated here; the count is recorded now so "twelve report parts"
is checkable from this file rather than resting on process context that was never written down. Beyond what is tabled above: the capability edge is legal under §13 and
manifest-level is a deliberate choice (D5); `test_rigid_hair_binding` moves a test whose subject
stays (H8); the review-existence gate is withdrawn for a rule about what may live in the base suite
at all (D6); the gate row ships a tool that cannot produce a verdict envelope (M1); D4's anchor
reason was invented (M3); the anatomy source and `hybrid` are now decisions rather than side effects
(D4, task 3.5); the harness anchor was stale and points at a branch of the abandoned change (M5);
the doc sweep missed `README.md` and Python docstrings (M6); `3.4`'s no-op claim samples fixtures
while the behaviour-changing class is a spec with `rig.bones` and `primaryDomain: "object"` (L3);
five missing scenarios added across the three deltas; eight assumptions written down as **D12**.

**The D2 attack is the round's sharpest finding and it changed no conclusion.** D2 said hair stays
because a doll, a wig stand or a furred creature carries hair and is not a character — then sent
`scalp_exposure.py`, the hard channel of that very gate, to a *character* plugin, leaving exactly
those subjects without it and pointing their runs at a deleted path. The partition cut the hair
subsystem along the line its own rationale rejects. D2's reasoning is rewritten, not dropped.

## The pattern, which is worth more than any single fix

Four instances of **deriving from what something is called rather than what it references**:
`scalp_field.py` from its docstring, `test_rigid_hair_binding` and `test_stand_proud_emission` from
their filenames, and `grimoire/character/` from its directory name. Every one was a `grep` away.
The Direction 1–3 sweep converts that class from judgement into derivation.

And its sibling, across D2 and D4: **a correct conclusion reached through reasoning that does not
survive contact with the source.** That is the most expensive error in a document meant to be
inherited, because the conclusion gets kept and the reasoning gets reused. Both rationales were
rewritten rather than quietly corrected.

## Verdict, recorded as given

> **The plan does not yet prevent a repeat, and it is close.** It fixes the two *process* omissions
> — the partition review is scheduled first, the suite is a numbered gate per slice, and both are
> real improvements over what was withdrawn. But its own anti-repeat mechanism was mis-specified in
> both directions (H1, H2); the loss class that actually cost 92 tests is invisible to that
> mechanism and was inherited unchanged (H6, H8); the slice order reproduced a hard break the base's
> own tests already pin (H3); and the claim the plan's shape rests on is false three ways (H4). So
> "its plan is built so neither omission is possible without the change visibly failing" did not
> hold as written. It holds once H1–H8 are corrected, and on the evidence of this round they are
> being corrected.

## Outstanding

- **The cross-reviewer rebuttal exchange did not run as a separate step.** The workflow calls for
  each reviewer to accept / rebut / amend the other's findings. It happened once in substance and
  materially: on the slice-0 gate, where reviewer A was asked for a view on reviewer B's proposal and
  **rejected half of it** — the lead had already applied B's version, and backed it out. Elsewhere
  the two reviewers' findings did not contradict each other, and every one reproduced under the
  lead's own re-measurement, so the exchange would have been a check on the lead's acceptances rather
  than a dispute. It was not run as a formal round, and this matrix should not be read as though it
  had been.
- **D11 is open and is the owner's.** Hair stays whole or leaves whole; the plan currently sits
  between. Recommendation on the record: partition 1, for the reason in D2's rewritten rationale —
  not because hair is generic, but because it cannot leave whole until a plugin can contribute a
  role, and half-left is worse than either end.
