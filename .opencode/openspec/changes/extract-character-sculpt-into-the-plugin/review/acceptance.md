# Acceptance capture — extract-character-sculpt-into-the-plugin

Run 2026-09-13 against `img2threejs` @ `a355e60` and `plugin-character` @ `f35b074`, installed
with `img2 add --link ./plugin-character` (0.3.0, local).

## The rule the whole change is measured by

> The character build emits the same Three.js output for the same input across the move.

Not sampled — **proved by md5 over the full emitted TypeScript**, through the real installed
plugin and the real base, with nothing stubbed:

```
$ python3 ~/.img2/plugins/character/tools/emit_spec_augmentation.py \
    --anatomy anatomy.json --out spec-augmentation.json
{"kind": "spec-augmentation-v1", "out": "spec-augmentation.json",
 "components": 61, "bones": 49, "materials": 9}

$ python3 forge/stage2_spec/new_sculpt_spec.py "Oracle Figure" \
    --augmentation spec-augmentation.json --domain character --out oracle.json

$ generate(oracle.json, "blockout")
produced md5: 98ac2045dcc9d802cc369e8b4d4d20a4
frozen   md5: 98ac2045dcc9d802cc369e8b4d4d20a4     <- fixtures/oracle-character/blockout.ts
BYTE-IDENTICAL
```

The first attempt used the target name "Hero" and differed by 83 bytes over 20 lines — every one
of them the target's own name (`createHeroModel` vs `createOracleFigureModel`). Zero geometry, rig
or material lines differed. Recorded because "20 lines differ" and "nothing differs" look the same
from a summary, and the reason they were identical is worth stating: the target name is an INPUT.

Anti-tamper markers in the emitted TypeScript: `THREE.SkinnedMesh` ×50, `THREE.Skeleton` ×1,
`new THREE.Bone` ×49, `skinIndex` ×1.

## A1 — base suite, empty `IMG2_HOME`

```
$ IMG2_HOME=$(mktemp -d) python3 -m pytest forge/tests -q
1387 passed, 66 skipped in 82.39s
```
Zero failures, zero errors. `COLLECTED_FLOOR` 1453 == 1387 + 66 collected.

## A2 — plugin suite standalone

```
$ IMG2_HOME=$HOME/.img2 python3 -m pytest tests/ -q
311 passed, 23 skipped
$ IMG2THREEJS_BASE=/nonexistent python3 -m pytest tests/ -q
296 passed, 38 skipped
```
With no base checkout reachable, 15 more tests SKIP and none fail. `COLLECTED_FLOOR` 334 == 334.

## A3 — `img2 doctor`

```
WARN  character  multi-capability provider: declares 3 capabilities; each edge resolves
                 independently via `img2 capabilities`
doctor: ok (4 plugin(s), 1 warning(s))
```
Zero FAILs. The WARN is expected and part of the baseline: three declared edges, each resolvable.

**3.10a was real.** Before this capture the installed clone was v0.2.0 carrying **12 untracked
files** hand-copied from the withdrawn attempt (`tools/character_template.py`,
`tools/derive_character_rig.py`, `tools/scalp_field.py`, …). `img2 doctor` reads the directory, not
the SHA, and FAILED on them. Every capture above would otherwise have photographed that attempt
rather than this release. The files are preserved outside the repo; the clone was removed and
re-added.

## A4 — capability resolution

```
$ img2 capabilities --from-kind image --to-kind character-sculpt-spec
{"status":"answered","providers":[{"plugin":"character","version":"0.3.0", ...}],"problems":[]}
```
Exactly one provider. The edge is **discovery-only** — see the plugin CHANGELOG.

## A5 — the checklist, with the plugin installed

`--profile character`, 35 steps. Contributed steps at the declared anchor, in declaration order:

```
 3 [setup ] character-contract-read
 4 [setup ] character-landmarks            <- writes anatomy.json
 5 [setup ] character-spec-augmentation    <- reads it
 6 [setup ] local-spec-search              <- setupAnchorBefore
10 [setup ] spec-authoring                 <- --augmentation spec-augmentation.json
26..34 [rig] rig-contract-read … rig-gates (9, after the FINAL steps)
```

## A6 — fail loud without the provider

```
$ IMG2_HOME=$(mktemp -d) python3 forge/state.py init --profile character ...
state error: no installed provider serves profile 'character'; available: generic.
              Install the domain plugin that provides it, or start the run as generic.

$ ... --profile animated-character
state error: profile 'animated-character' has been withdrawn; it was replaced by 'character'.
              one id now carries the rig steps; a static build skips a rig step with a recorded
              reason. Re-init with --profile character, or edit "profile" in an in-flight state
              file. Available: generic.
```

The second is what 3.3b bought. The generic message would have said only "no installed provider
serves profile 'animated-character'", from which "your plugin is missing" and "this profile no
longer exists" are indistinguishable — and its advice, *install the plugin that provides it*,
cannot succeed: nobody provides it, so obeying it installs 0.3.0 and reproduces the message.

## A7 — generic run, no plugin installed

```
$ IMG2_HOME=$(mktemp -d) python3 forge/stage2_spec/new_sculpt_spec.py "Plain Box" --out spec.json
/private/tmp/a7/spec.json
components: 1 | rig: False | materials: 1
```
Authors the skeleton and validates with warnings only — unchanged from before the move.

## A8 — removal round-trip

```
$ img2 remove character   -> doctor: ok (3 plugin(s), 0 warning(s))
  --profile character     -> state error: no installed provider serves profile 'character'
$ img2 add --link ./plugin-character  -> added character 0.3.0
  --profile character     -> resolves, 35 steps ending in rig-gates
```

## A9 — both floors at measured values

| | floor | collected |
|---|---|---|
| base | 1453 | 1453 |
| plugin | 334 | 334 |

Both **set** to the measurement, not lowered and not merely raised. The base floor stood at 1192
against 1458 — 266 of slack, enough to absorb a quarter of the suite going dark, which is how the
withdrawn attempt lost 100 tests without the floor moving.

Both numbers moved once more after a cleanup review: 1449 → 1453 and 331 → 334. The plugin's three
are the ones that matter — the five base values this plugin carries were pinned only by KEY
PRESENCE, with the value comparison in a class that skips without a base checkout, so a stale
`blockedReason` string could have shipped on every run with nothing red. The new pin compares
values against the frozen fixture this plugin carries, so it cannot skip.

## A10 — every skip states a reason

Seven distinct reasons over 38 skips, each naming an environment variable that would enable it
(`IMG2THREEJS_BASE`, `IMG2THREEJS_SHOWCASE_ROOT`) or a missing local asset. **No skip's reason is a
missing plugin.** `IMG2THREEJS_REQUIRE_BASE=1` turns every base-dependent skip into a failure.

## A11 — end to end

**The sculpt half is done and is the byte-identical capture at the top of this file.** The rig half
is **BLOCKED**, and the blocker is pre-existing rather than introduced here:

> `runtime/scripts/export_mesh_buffers.mjs` does not exist in this repo. Two of the nine rig steps
> — `mesh-freeze` and `mesh-parity-verify` — invoke it, and the path appears only in `.md` files.
> This shipped in plugin-character v0.2.0.

Recorded as task 5.11a rather than worked around. The honest statement: **this change does not make
the rig track runnable end to end, and it did not break it either — it was already not runnable.**
A capture claiming otherwise would be the withdrawn attempt's mistake repeated, where a state file
full of `done` marks stood in for evidence.

## Gates from `openspec-apply-audit`

```
$ g5_surviving_readers.py forge/ --dest character --dest accessories
--- G5: 0 finding(s) ---

$ g3_moved_not_copied.py --src forge --dst ../plugin-character/tools  (19 symbols)
--- G3: 0 finding(s): all 19 MOVED, none COPIED, NOT MOVED or VANISHED ---
```

G5 is the withdrawn attempt's signature defect: it deleted `--character` and left `args.character`,
which raised `AttributeError` on **every** profile, generic included. A string-literal AST sweep
cannot see it — `args.character` contains no string constant.

## The review that came after this capture

A correctness review run over the finished diff found **one Critical and three Important**, all
confirmed by measurement and all fixed. Recorded here because a capture that only lists what passed
is the shape the withdrawn attempt had.

**Critical — the anatomy gate existed in NEITHER repo.** The base deleted `validate_character_track`
under a disposition asserting the check had moved to the producer. It had not:
`emit_spec_augmentation.py --out a.json` with no anatomy exited 0 and authored a full default
humanoid. The gate fired under `--strict-quality`, and `strict-validation` is a mandatory checklist
step — so a character run with no landmark evidence used to be BLOCKED and had silently become a
clean pass with invented proportions. The byte-identity capture above could not see it: the fixture
always supplies anatomy.

**And the fix exposed what looked like a second hole underneath it** -- the paragraph below was
itself wrong, and is corrected at the end of this document. It is left standing because the
correction is the point.

**What I wrote at the time:** Adding the gate immediately rejected the real
fixture, because `_anatomy_from` only ever looked for an `"anatomy"` key — so the BARE block
`extract_landmarks.py` writes, the one `domain.json` passes, returned `None` and every run had been
authoring the DEFAULT humanoid rather than the measured one. Invisible for an unlucky reason: the
fixture's measurements equal the template's defaults, so the spec was byte-identical either way.
**The byte-identity that proves this extraction correct was, for this one function, also what hid a
bug in it.**

**Important — the routing conflict's remedy could not succeed.** The message named `--domain
character` plus an augmentation artifact; supplying both reproduced the message, because the routing
check ran before the block that reads those flags. The first fix was worse than none — it let the
run through with the record still `request-input`, which exited 0 and then failed strict validation.

**Important — `unittest.main()` sat mid-file** in `test_spec_augmentation_artifact.py`, so running
that module directly defined 11 of 20 tests, silently including the non-skippable value pin added
specifically so a stale value could not drift. pytest collected all 20, so CI never saw it.

**Important — `SKILL.md:81` was left truncated** by an earlier edit: an orphan clause, and the claim
"on `character` the Stage R gates are absent", which contradicted the clause three lines above it.
`test_documentation_agreement` could not catch it — no dead path, and the withdrawn identifier had
been edited out.

Also: `test_rig_spec_agreement.py` defaulted to `~/Documents/personal/img2threejs`, so **nine
cross-repo drift pins had been skipping silently** with the base sitting next door. They pass.

Re-measured after every fix:

```
base    1391 passed, 66 skipped, 0 failed     floor 1457 == 1457 collected
plugin   330 passed, 14 skipped               floor  344 ==  344 collected
plugin, no base checkout   306 passed, 38 skipped, 0 failed
end to end                 md5 98ac2045dcc9d802cc369e8b4d4d20a4, BYTE-IDENTICAL
```

**The lesson this round earned**, which is the same one the partition review earned in a different
costume: a disposition is a claim about code somewhere else, and writing it down is not the same as
checking it. Three of the five findings were sentences I wrote asserting behaviour I had not run.

## And the re-review of those fixes found the Critical was mine

A focused re-review over the fix delta found **one Critical and one Important**, both in the fixes
themselves. Recorded because it is the sharpest instance of this change's own recurring lesson.

**Critical — the anatomy gate broke the domain's own checklist on the happy path.** `domain.json`
runs `character-landmarks` then `character-spec-augmentation` back to back. The gate copied the
base's `anatomy.get("applies") is not True` test, and `extract_landmarks.py` **never writes an
`applies` key** — so it refused `anatomy.json` even after an agent filled every null exactly as that
tool's own `authoringInstruction` demands, with a message telling them to run the step that had just
produced the file. Advice that cannot succeed: the third instance of that class in this change, one
file over from the fix that removed the second.

**And the story I wrote about it was wrong.** The docstring, the CHANGELOG and this document all
said `extract_landmarks.py` writes a BARE anatomy block that `_anatomy_from` used to miss. It writes
the **wrapped** shape, which the original two-line version handled correctly. The bare form exists
only in this plugin's own hand-made fixtures — so "every run had been authoring the default humanoid
rather than the measured one" was never true of the real pipeline. **Every test written alongside
that gate used a hand-made dict or that fixture. Not one fed it what the producer emits.**

Fixed: a missing `applies` is "not stated" and the fields decide; only an explicit `False` refuses on
its own terms. `tests/fixtures/oracle-character/landmarks-skeleton.json` freezes the producer's real
output — so this suite cannot be green while the checklist is red — plus a base-checkout test that
the frozen shape is still what `make_anatomy_skeleton` emits.

**Important — the provider branch opened a hole in the fail-closed guarantee.**
`resolve_pipeline_routing` checked four conditions before letting a provider resolve a record;
`validate_pipeline_routing` checked the record's SHAPE and none of them. Measured: a hand-edited
record claiming `source: "provider"` walked a **0.40-confidence hybrid** through as `resolved` with
zero errors — the "needs a human" case the module exists to stop. Before the provider branch that
edit was impossible, because `track` had to be in `VALID_TRACKS`. Both sides now call one predicate,
`provider_may_resolve`, and a test asserts they cannot disagree.

Also fixed from the same pass: `--style-heads nan` emitted literal `NaN` (invalid JSON for the Node
harness) and `inf` raised an uncaught `ZeroDivisionError`; `_anatomy_from`'s bare fallback could
return a whole assessment payload; and a provider-resolved run persisted two contradictory routing
records, the nested copy still saying `request-input`.

Final:

```
base    1394 passed, 66 skipped, 0 failed     floor 1460 == 1460 collected
plugin   335 passed, 14 skipped               floor  349 ==  349 collected
end to end                 md5 98ac2045dcc9d802cc369e8b4d4d20a4, BYTE-IDENTICAL
real checklist path        unfilled anatomy -> refused NAMING the fields
                           filled anatomy   -> 61 components, 49 bones
```

**The lesson, now measured three times in one change:** a claim about code is worth nothing until it
is run. The partition review caught it in classification ("what does it know" vs "who calls it"), the
first correctness review caught it in a disposition, and this one caught it in a fix written to close
that disposition — where the test that should have caught it was fed a fixture I had made rather than
the artifact the pipeline produces.
