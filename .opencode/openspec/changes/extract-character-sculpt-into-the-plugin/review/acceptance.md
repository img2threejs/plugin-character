# Acceptance capture — extract-character-sculpt-into-the-plugin

Run 2026-09-13 against `img2threejs` @ `061ac35` and `plugin-character` @ `f860f4e`, installed
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
1383 passed, 66 skipped in 93.68s
```
Zero failures, zero errors. `COLLECTED_FLOOR` 1449 == 1383 + 66 collected.

## A2 — plugin suite standalone

```
$ IMG2_HOME=$HOME/.img2 python3 -m pytest tests/ -q
308 passed, 23 skipped
$ IMG2THREEJS_BASE=/nonexistent python3 -m pytest tests/ -q
293 passed, 38 skipped
```
With no base checkout reachable, 15 more tests SKIP and none fail. `COLLECTED_FLOOR` 331 == 331.

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
| base | 1449 | 1449 |
| plugin | 331 | 331 |

Both **set** to the measurement, not lowered and not merely raised. The base floor stood at 1192
against 1458 — 266 of slack, enough to absorb a quarter of the suite going dark, which is how the
withdrawn attempt lost 100 tests without the floor moving.

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
