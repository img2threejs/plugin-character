# Tasks — extract character sculpt into the plugin

Branch from `img2threejs` `main` @ `6e60b5e` and `plugin-character` `v0.2.0` @ `796dd9c`. The
branches from the withdrawn attempt are not reused.

**Slice order is the design.** Slice 0 establishes what "unchanged" means and closes the review gate
the withdrawn attempt left open; slices 1–2 are plugin-only; slice 3 is the first that removes
anything from the base. Each slice ends with a measured suite run whose numbers go in the commit
message.

**THE ORDERING INVARIANT: the plugin is never INSTALLED while the base still declares `character`.**
The registry refuses two providers for one id, and the refusal is not scoped to the colliding
profile — it takes down the whole registry. Measured, with the base at `main` and a plugin declaring
`id: "character"` present in `IMG2_HOME`:

```
registered_domains()        → DomainRegistryError: domain id 'character' is declared twice
domain_profile('character') → same error
domain_profile('cs2')       → SAME ERROR — an unrelated domain's user is broken too
state.py init --profile character → invalid choice: 'character' (choose from 'generic')
```

`forge/state.py:37-40` catches the error and degrades `--profile` to generic-only; `validate_state`
raises for any saved state naming `character` **or `cs2`**. So an `img2 add` performed before the
base lets go breaks every non-generic profile on the machine, CS2 included.

An earlier revision of this file put `img2 add` and the installed-state captures in slice 2, ahead
of the base deletion in 3.1, and claimed slices 1–2 "change nothing". They would have changed
everything, for anyone who ran 2.6. The install and every capture that needs it now sit in slice 3,
**after** the base has let go. The reverse window — base deleted, plugin not yet installed — is
safe: it fails loud with no provider, which is the designed behaviour, not a broken registry.

## Measurement rules — these are the rules the withdrawn attempt broke

- **Assert collected, never the run count** — and measure it with `--collect-only`, because the
  `-q` summary line reports passed and skipped, not collected. Baseline, measured 2026-09-12:
  base `IMG2_HOME=$(mktemp -d) pytest forge/tests --collect-only -q` → **1453 collected**
  (1387 passed, 66 skipped, 0 failed); plugin
  `IMG2_HOME=$HOME/.img2 pytest tests --collect-only -q` → **258 collected** (226 passed, 32
  skipped). An earlier revision of this file wrote 1387 and 235 here: the base's passed count, and
  the plugin's *declared floor* transcribed from `test_suite_integrity.py:35`. Following either
  would have set a floor 66 and 23 below its tree — the slack this change exists to remove,
  reproduced in its own baseline.
- **Every floor move writes its arithmetic**: `before − moved + added = after`, both sides measured
  in the same sitting. A floor below the measured count is not a floor.
- **A commit message with no measurement means the slice is not done.** The suite is the gate, not a
  checkbox in this file.
- **Post-deletion runs need `--continue-on-collection-errors`**, or pytest aborts and reports nothing.
- **Never read a test's own stdout as a verdict** — `test_label_glb_nodes` prints `FAILED: not a GLB
  container` while passing. Anchor on the summary line or the exit code.
- **No comment, docstring or CHANGELOG line describes work that is not in the same commit.** The
  withdrawn attempt wrote "the base no longer carries the character content" into the file that
  still carried it.

---

## 0. The gate and the oracles — nothing moves before this closes

- [x] 0.1 **Done 2026-09-12** — `partition.md` at the change root: measured census (24/104/12/15
      module-level symbols), 13 flagged in `new_sculpt_spec.py` all confirmed content, and three
      UNFLAGGED symbols that name-matching missed (`_eye_socket_sdf`, `_limb_attachment`, the
      `anatomy` seed in `make_pre_spec_assessment`) plus one flagged symbol that is mechanism
      (`_cnode` — its docstring names a domain, its code knows only the schema). Seven open
      questions recorded for 0.3.
      Originally: Write `partition.md` at the change root: one row per module-level symbol reachable from
      the character path in the modules that STAY — `new_sculpt_spec.py`, `validate_sculpt_spec.py`,
      `generate_threejs_factory.py`, `pipeline_routing.py`, `new_pre_spec_assessment.py` — with
      columns: symbol, `file:line`, lines, what it *knows* in one sentence, mechanism-or-content,
      justification. Include the name-blind symbols a keyword sweep misses: `CHARACTER_BASE_MATERIALS`,
      `CHARACTER_ACCESSORY_MATERIALS`, `_RIG_STRUCTURAL_LEAVES`, `SYMMETRY_PARITY_TOLERANCE`,
      `POOL_FLOOR_MIN_BONES`, `PROPORTION_LIMIT_FRACTION`, `_mirror_partner`
- [x] 0.2 **Done 2026-09-12** — whole-tree sweep, three passes, `forge/tests/` included. `import`
      hits: 0. Symbol refs: 33. Path strings: 8. It found **three test modules no earlier
      disposition list named**: `test_joint_admission_gate` (`_mirror_partner` ×4),
      `test_rig_hierarchy_emission:102` (a method-body import, invisible to a module-scope scan and
      to the collected count), and `test_run_gates:187` (a path string with no AST reference at
      all). Plus `extract_landmarks.py:6` — a module that STAYS — naming a leaving grimoire page.
      Originally: **Sweep for consumers, and do not scope the sweep by node type.** The withdrawn attempt
      scoped slice 2 from an AST sweep for domain-name *string literals*; `args.character` is an
      attribute access carrying no literal, so it survived the flag it read and crashed every run.
      An allowlist of `Attribute` / `Name` / argparse `dest` fixes that one case and reproduces the
      shape of the error — it still misses **function-scoped** `ImportFrom`
      (`test_stand_proud_emission.py:204` and `:228` import `scalp_field` inside test bodies; the
      module's top-level imports name nothing character-related, and after 3.6 those two error while
      pytest still collects all 31, so the floor does not move) and it misses **path strings**
      (`scalp_exposure.py` is named in four literals: `hair_gate.py:108` docstring, `:123` a runtime
      message, `:194` argparse help, and `orchestrate_passes.py:169` user-facing output).
      The honest method is: grep the bare module name across the whole tree, then classify every
      hit. Record the result as a table, hit by hit.
      **Sweep `forge/tests/` too, in BOTH directions** — staying tests that import into the leaving
      set, and leaving tests whose subject stays — because the disposition list is otherwise a guess
      dressed as a decision. It already went wrong both ways from filenames alone: see 1.6
- [x] 0.3 **Done 2026-09-12 — gate closed.** `review/partition-review.md`: an independent
      architecture adversary ruled on all seven questions across ten report parts.
      **Accept 1 · Amend 3 · Rebut 3**, and all three rebuttals dissolved their question rather than
      answering it. Outcomes that changed the partition: `_cnode` leaves (18 call sites, all inside
      the leaving function); `validate_rig_admission` **stays whole** — `rig` is plugin-contributable
      and admitted opaquely, so moving three of five checks would make the plugin validate its own
      submission; `_eye_socket_sdf` and `_limb_attachment` leave with their caller; the `anatomy` key
      is dropped, not scaffolded; `POOL_FLOOR`'s 4 is the `skinIndex` vec4 width, not anatomy;
      `hybrid` stays, with the sweep scoped to the `{"character","hybrid"}` literal pair.
      **Four of seven questions were malformed** — the review's own finding, recorded there.
      Originally: Get `partition.md` and the 0.2 sweep reviewed. Deliverable: `review/partition-review.md`
      recording accept / rebut / amend per row
- [ ] 0.3a **Make the partition's CONCLUSIONS executable — not its review.** An earlier revision of
      this task added a base test asserting `review/partition-review.md` exists with a verdict per
      row. That is withdrawn on review: it points `forge/tests/` at
      `openspec/changes/<name>/review/`, a directory that moves at archive, so it breaks or is
      deleted exactly when nobody is watching — *a gate that expires silently is worse than a
      checkbox, because it looks like a gate* — and it is satisfiable by writing the file, which is
      the withdrawn attempt's signature failure in a new costume.
      Instead assert properties of the shipped repo. The partition lives in
      **`forge/tests/fixtures/partition.json`**, not under `openspec/`, so nothing moves at archive.
      Three directions:
      1. **Nothing staying references anything leaving.** `ast.walk` every `forge/**/*.py` collecting
         `Import` / `ImportFrom` module names, `Attribute` attrs and `Name` ids; none may match the
         leaving set. Two properties are load-bearing and both were missed last time: walk the
         **whole tree, not `tree.body`** (the two broken imports were `ImportFrom` nodes inside
         method bodies, which a module-scope sweep and the unittest loader both saw as nothing), and
         **include `forge/tests/`** (a sweep scoped to production code skips exactly the file that
         broke). Pair it with a plain-text sweep for the leaving basenames, to catch the
         `sys.path.insert` + string-literal form that carries no AST reference at all.
      2. **Nothing leaving references anything staying.** For each moving test module, its imports
         must resolve entirely within the leaving set. That is H8 as a two-line assertion.
      3. **The stays column still resolves.** Import each staying module and `getattr` each symbol
         the partition asserts — catches a stays entry deleted by accident, which a deny-list sweep
         cannot see.
      All three survive archive, need no allowlist upkeep, and hold for the next extraction too
- [x] 0.4 **Done 2026-09-12.** `forge/tests/fixtures/oracle-character/{spec.json,blockout.ts,anatomy.json}` +
      `test_character_oracle_replay.py`. spec `bb1051fd35003aa8eb125fa8f77b5410`, blockout
      `98ac2045dcc9d802cc369e8b4d4d20a4`, all four anti-tamper markers present. **Finding:** the
      emitter embeds a spec's dict KEY ORDER in its output, so the first freeze (sort_keys=True)
      replayed to 850 diff lines of pure reordering. Fixture is now serialised without sort_keys
      and round-trips exactly — and the plugin must author its sections in the base's key order or
      byte-identity fails on unchanged content.
      Originally: Freeze the **emission** oracle: `forge/tests/fixtures/oracle-character/{spec.json,
      blockout.ts}` and `test_character_oracle_replay.py` asserting byte equality, plus an
      anti-tamper assertion that the frozen output still contains `THREE.SkinnedMesh`,
      `THREE.Skeleton`, `new THREE.Bone` and `skinIndex`
- [x] 0.5 **Done 2026-09-12.** `plugin-character/tests/test_character_authoring_oracle.py` + its own fixtures.
      Reads the template from the plugin's `tools/` when present, else the base via
      `IMG2THREEJS_BASE`, so it follows the template when slice 1 moves it.
      Originally: Freeze the **authoring** oracle — the one that can see this extraction regress:
      assessment → `new_sculpt_spec.py` → spec, md5 recorded. It is authored in
      **`plugin-character/tests/` from the start** (design D6), frozen from `main` before anything
      moves, run against the base checkout through `IMG2THREEJS_BASE` during slice 0 and against the
      plugin thereafter. It must NOT live in `forge/tests/`: the `domain-plugin-boundary` delta
      requires that deleting the moved authoring makes it fail, while 3.10 requires the base suite to
      have zero failures after exactly that deletion — one home satisfies both, the other is a
      contradiction that reads as licence to neutralise the only test that can see the regression
- [x] 0.6 **Done 2026-09-12.** Zero unseeded sources on either path (no `random`/`uuid`/`time.time()`/
      `datetime.now()`/`os.urandom`), and two full runs produced one md5 for both the spec and the
      emitted TypeScript.
      Originally: Record the determinism evidence beside the fixtures: no `random` / `uuid` / `time.time()`
      / `datetime.now()` / `os.urandom` in `new_sculpt_spec.py`, `generate_threejs_factory.py` or
      `forge/stage5_rig/*.py`, and repeated runs producing one md5
- [x] 0.7 **Done 2026-09-12.** Both green on `main`: emission 5 passed, authoring 4 passed. **And the pair is
      proven falsifiable** — against a scratch tree with `apply_character_template` stubbed to a
      no-op (componentTree 61 → 1, rig gone): emission **5 passed** (blind by construction),
      authoring **1 failed**, naming buildPasses, componentTree, featureReviewTargets, materials,
      preSpecAssessment, rig, sculptPipeline. That is the demonstration the
      `domain-plugin-boundary` delta requires, and the reason the previous attempt's oracle stayed
      green while the authoring was deleted.
      Originally: Both oracles green on `main`, before any file moves. Record both md5s here

## 1. The plugin takes the content — base untouched, nothing user-visible changes

- [ ] 1.1 `tools/character_spec_template.py`: the humanoid component tree, `derive_character_rig`,
      `apply_character_pose`, build passes, feature targets, `validate_character_track`, and the
      material constants — authored into an **empty scratch dict**, mirroring
      `cs2_spec_template.py`. One definition per symbol; the withdrawn attempt shipped this file
      with its own content pasted twice
- [ ] 1.2 Make the character materials **self-contained** (design D3): each carries its own
      `shaderModel`, `textureResolution`, `textureProjection`, `albedo`, `colorVariation`,
      `roughness` — as `_cs2_finish_material` does — instead of seeding from the base's `base`
      material. **The list is NINE, not eight**, and it is led by the base's own `base`:
      `['base','hidden','skin','hair','shirt','pants','shoes','eye','lips']` — measured. Since
      `specSections` assigns wholesale, a contributed array drops `base` unless the plugin
      re-authors a base-equivalent default, so that default is part of this task. With accessories
      it is **thirteen**: `CHARACTER_ACCESSORY_MATERIALS` has **four** entries, not three. Test:
      byte-identical to what the base produces today, same order, both accessory modes
- [ ] 1.3 `tools/emit_spec_augmentation.py`, mirroring cs2's: `specSections` filtered by the
      `BASE_OWNED` deny-list, `assessmentPatch` with the domain marker popped, `qualityFloors`
      carrying the floors, `provenance` read from `plugin.json` so it cannot drift from the release.
      **No `--spec` argument** — it authors, it does not read the base's output.
      `assessmentPatch.objectClass` must carry **`primaryDomain: "character"`**: the base template
      writes it at `new_sculpt_spec.py:1139` and `validate_sculpt_spec.py:904` hard-errors without
      it. The merge refuses only `objectClass.domain`, so the route is open — but an earlier revision
      named only the canon anatomy as travelling this way, and the run would have failed validation
- [ ] 1.3a **Replace the `--accessories` switch.** Slice 3 deletes the base flag; the plugin needs
      its own way to select the four accessory materials and their feature targets, or the
      capability disappears with the flag and nobody notices
- [ ] 1.4 `git mv` into `tools/`: **`humanoid_proportions.py` only.** Under D11 partition 1 neither
      `scalp_field.py` nor `scalp_exposure.py` moves — the first because the base's emitted
      `ringStackDistance` is pinned against it (D10), the second because it is **hair's** content and
      hair stays whole. The moved tool gains the §8 bootstrap stanza. It needs nothing further:
      `humanoid_proportions.py` contains **no** `Path(__file__).parents[N]` and no `sys.path`
      insertion — measured. (An earlier revision of this task demanded `--workspace` and
      `img2_core.paths` here; that requirement was written for `scalp_exposure.py`, which no longer
      moves. It is not lost — `img2 doctor` FAILs on a hand-copied `tools/scalp_exposure.py` in the
      installed clone today for exactly that pattern, so the requirement travels to **7.1** with
      hair.) What it does need is the `--in-place` question: it writes the base's spec, and a plugin
      may not — see 1.3a.
      `humanoid_proportions`' canon anatomy travels as an `assessmentPatch`, never `--in-place` into
      the base's spec
- [ ] 1.5 `git mv` the grimoire pages into the plugin's `grimoire/` — **by content, not by folder**.
      The directory holds five pages and a JSON file; two are hair (`stylized_hair_threejs.md`,
      `threejs_hair_parameter_contract.json`, cross-referenced from `SKILL.md:163-164`) and under
      D11 partition 1 they **stay**. The moving set is **four**:
      `reconstruction.md`, `likeness_maximization.md`, `structure_decomposition.md`,
      `head_construction.md`. and add
      `spec_search_profile.json` declaring the `character` collection — the plugin contributes no
      evidence corpus today and the mandatory local-spec-search step runs on every profile
- [ ] 1.6 Move the tests with their subjects — **derived from imports, not from filenames**, per
      0.2's sweep over `forge/tests/`. Two corrections an earlier revision got wrong in opposite
      directions, both from reading names: `test_rigid_hair_binding` (21) **does not move** — its
      bootstrap is `sys.path.insert(... "stage5_rig")` then
      `from geodesic_skinning import RIGID_ROLES, bind, partition_for_binding`, so its subject is
      `forge/stage5_rig/geodesic_skinning.py`, the **first row of D5's stays table**. Moving it would
      leave base library code with its only pin inside an optional plugin, and in the plugin it would
      either import `forge.*` (a §8 doctor FAIL) or silently resolve against the plugin's own
      `rig_geodesic_skinning.py` — a different module — and keep passing while no longer testing what
      it was written to test. And `test_stand_proud_emission` stays for the same reason under D10.
      Under D11 partition 1 the moving set is **22 tests**, measured:
      `test_character_rig_derivation` (13) and `test_humanoid_proportions` (9). The three the plan
      once moved — `test_scalp_field` (36), `test_scalp_exposure` (21), `test_rigid_hair_binding`
      (21), **78 collected** — all stay. Base-checkout and showcase dependencies skip with a reason through
      `IMG2THREEJS_BASE` / `IMG2THREEJS_SHOWCASE_ROOT`, never silently
- [ ] 1.7 New tests: the artifact's shape against the base's real `merge_spec_augmentation`; that
      no `specSections` key collides with `BASE_OWNED`; that the tool writes only its artifact and
      never the spec it was pointed at; and that **every `specSections` key the artifact carries is
      named in the base's authority ruling** (read through `IMG2THREEJS_BASE`, skipped with a reason
      when unset). Without that last one, `spec-augmentation`'s "authority is stated" scenarios
      describe a document no test can check, and a section added without a ruling ships unnoticed
- [ ] 1.7a Write the ruling itself, **in `forge/_shared/spec_augmentation.py` beside the deny-list**
      it governs — not in a design document: name `componentTree`, `rig`, `materials`, `buildPasses`,
      `featureReviewTargets` and `sculptPipeline`, each with whether a plugin may write it and why.
      This is base work and belongs in slice 3's commit; it is listed here because 1.7's test asserts
      against it
- [ ] 1.8 Plugin floor **corrected, not merely raised**: v0.2.0 declares 235 against 258 collected,
      so it is already 23 short. Set it to the measured count with the arithmetic recorded
      (`258 + arrived + added = measured`). Plugin suite green standalone, without the base test
      tree — numbers in the commit message

## 2. The plugin declares itself — still additive, still nothing removed

- [ ] 2.1 `domain.json`: `id: "character"` (D1); `setupSteps` = `character-contract-read`,
      `character-landmarks`, `character-spec-augmentation` at `setupAnchorBefore: local-spec-search`;
      `passSteps` = `character-scalp-exposure` at `passAnchorBefore: ai-review-recorded`;
      `rigSteps` = the nine Stage R steps unchanged; `specCollection: "character"`
- [ ] 2.2 `character-contract-read` names `{plugin_dir}/grimoire/character/...`, not the base paths —
      those files are gone after slice 3, and the withdrawn attempt shipped a step pointing at them
- [x] 2.3 **Dissolved by D11 partition 1.** The scalp-exposure gate row and its verdict-envelope
      wrapper are not needed: `scalp_exposure.py` stays in the base, where it is already the hard
      channel the base's own hair gate consumes. This is M1 ceasing to exist rather than being
      solved — the cheapest possible resolution, and a direct consequence of the partition choice.
      Recorded for the reader who wonders where the gate went:
      ~~add the scalp-exposure row — and write the envelope wrapper it needs.
      `scalp_exposure.py:252-255` prints the raw report dict and returns `0 if verdict == "pass"
      else 1`. §9 requires one `{"kind": "img2.gate-verdict", "version": 1, "gate": …, "plugin": …,
      "status": …}` envelope on stdout, and `run_gates.py:27` classifies a malformed envelope as
      **`error`, never a pass** — so the row as an earlier revision described it ships a gate that
      errors on every run: the same "check with no runtime caller" defect this task exists to
      prevent, one layer down. `gate_rigging.py` shows the shape to copy. The word "envelope"
      appeared nowhere in this change before review.
      It is a HARD gate in the base today (`SKILL.md:293`, `:362`).~~
- [ ] 2.3a `gates.json`: keep the existing `rigging` row and its `blocking: false` re-block trigger
      unchanged. Nothing is added to this file by this change
- [ ] 2.4 `plugin.json`: version `0.3.0`, and the `image → character-sculpt-spec` capability edge —
      resolution matches on the typed edge alone, never on the plugin's name. **State what backs the
      edge before adding it**: cs2 ships a `steps.json` and resolves with `"steps": []`; this plugin
      ships none and no task adds one. Either add the row, or record the edge as discovery-only and
      name what consumes it. `domain-step-contribution` forbids a declaration with no runtime caller,
      and a declaration with no caller was the withdrawn attempt's central defect — settle it here,
      not at the doctor capture
- [ ] 2.5 Declaration guard tests: the domain parses; every step's placeholders are inside
      domain.json's own closed set (`{plugin_dir}`, `{reference}`, `{spec}`, `{pass_id}`); no
      command row carries a shell metacharacter; every tool a row names exists
- [ ] 2.6 Everything above is committed to the plugin repo and NOT installed. Verify the invariant
      holds: `img2 doctor` still reports the registry healthy, because nothing new is registered yet.
      Installing here would collide with the base's `character` module and break CS2 too — the
      install is task 3.2

## 3. The base lets go — the first slice that removes anything

- [ ] 3.1 Delete `forge/_shared/domains/character.py`. The id cannot be served by two
      providers, so the base releases it here and the plugin claims it at 3.11. Between the two the
      profile is simply unserved, which fails loud — the reverse order breaks the whole registry
- [ ] 3.2 Delete the character content from `new_sculpt_spec.py` per the 0.1 partition, and
      `validate_character_track` from `validate_sculpt_spec.py`
- [ ] 3.3 Remove the `--character` / `--accessories` flags **and every reader of them**, per the 0.2
      sweep. This is the exact defect the withdrawn attempt shipped: the flag went, the
      `args.character` read stayed, and step 2 of the pipeline raised `AttributeError` on every
      profile including generic
- [ ] 3.3a **`forge/state.py`: drop the argparse `choices=` on `--profile`** (`:37-40`) and let
      `new_state()` refuse, so the registry's own message — which names the missing provider and the
      remedy — reaches the user. Today `init` answers `invalid choice: 'x' (choose from ...)` and
      names nothing, while **resume** goes through `validate_state → domain_profile` and does print
      the good message: one bad profile, two different answers. The comment already at `state.py:31`
      describes the behaviour this restores. Test both paths
- [ ] 3.3b **A withdrawal table beside the registry**: `animated-character → character`, with the
      remedy. `domain-step-contribution`'s new scenarios require the refusal to name the withdrawn
      identifier, name its successor and state the remedy; today's message names an availability list
      from which a user cannot tell "your plugin is missing" from "this profile no longer exists",
      and it says *"Install the domain plugin that provides it"* — after this change nobody does, so
      obeying it installs v0.3.0 and reproduces the message. Two base tests, one per new scenario.
      Without this task those two scenarios cannot fail
- [ ] 3.4 Delete `BONE_TRACK_DOMAINS` from `generate_threejs_factory.py:1915` and the
      `primaryDomain` test at `:1926`; `rig_is_bone_track` then routes on `rig.bones` alone.
      **"All three emission md5s unchanged" is not enough** — it samples fixtures, while the class
      that actually changes behaviour is a spec carrying `rig.bones` with `primaryDomain: "object"`,
      which goes from emitting nothing to emitting a full skeleton, against the function's own
      docstring guarantee that object output stays byte-identical. Add the negative test for that
      spec rather than weakening the claim to "no fixture regresses": a weaker claim leaves the
      behaviour change unowned
- [ ] 3.5 `pipeline_routing.py`: drop the character track. `TRACK_BY_KIND` keeps `weapon`, and the
      resolver's `kind` handling is resolved for both domains at once, not only for the one leaving.
      **`hybrid` is a decision, not a side effect.** On `main`,
      `VALID_KINDS = {"weapon", "character", "hybrid", "unknown"}`; the abandoned branch silently
      narrowed it to `{"weapon", "unknown"}`, removing both. But `hybrid` is a *classification
      outcome* — "part object, part character" — not a domain name, and `domain-recognition` requires
      an unknown-or-hybrid classification to **request input** rather than route. Decide explicitly
      whether it stays in the vocabulary; an earlier revision of this task was silent and would have
      inherited the deletion
- [ ] 3.6 `git rm` **`humanoid_proportions.py` and the four moved grimoire pages only** — under D11
      partition 1 `scalp_field.py`, `scalp_exposure.py` and the two hair pages stay; repoint the docstring at
      `hair_gate.py:123` that names `forge/stage4_review/scalp_exposure.py`
- [ ] 3.7 Rework the base tests that break — by disposition, never by deletion to make the suite
      green. Each either moved with its subject in 1.6 or is re-expressed against the mechanism the
      base keeps. **The list is filled in during slice 0, not discovered here** — leaving it blank at
      review time is how 100 tests went missing last time, and it is a grep. Two are already known:
      `test_stand_proud_emission.py` (31 tests; function-scoped `from scalp_field import ScalpField`
      at `:204` and `:228`. **Under D10 it no longer breaks** — `scalp_field.py` stays — but it is
      the measured proof that the floor is blind to this loss class: with the module gone,
      `--collect-only` still reports 31 while the run reports 2 failed. Keep it as the pin it is) and `test_hair_gate.py:222-236`, which asserts
      `assertIn("scalp_exposure.py", evidence)`. Under D11 partition 1 that file **stays**, so this
      assertion is no longer at risk — recorded because an earlier revision listed it as breaking,
      and because it breaks again the day 7.1 moves hair.
      Also `test_rig_workflow_steps.py:199-211` — `SetupStepAssetsAgreement` asserts base-relative
      `grimoire/character/reconstruction.md` and `likeness_maximization.md` exist, and 3.6 deletes
      both. Its sibling `InstalledPluginOrderIsCheckedWhenPresent` at `:186` **survives** the id
      rename: it keys on the plugin *directory* name and reads `rigSteps`, neither of which changes.
      Name both dispositions, so the survivor is a decision rather than luck
- [ ] 3.8 `test_domain_registry`: in-repo domains are now empty. Per design D9, replace
      `test_both_registry_sources_register_hermetically` — whose comment reads "A seam with one
      consumer is a rename, so both sources are exercised" — with a test that **two installed
      plugins** resolve through the same mechanism and that no in-repo branch exists for either.
      The seam keeps two consumers; neither is in the repo. Do not simply delete the assertion
- [ ] 3.9 **Set** `COLLECTED_FLOOR` to the measured count, with the arithmetic
      (`1453 − 100 + added = measured`), in the same sitting as the measurement. The verb is `set`,
      not `lower`: the floor is **1192** against **1453** collected — 261 of slack today — so after
      ~100 tests move out the measured count is ~1353 and the floor goes **UP** by ~161. "Lower it"
      would preserve the slack this change exists to close. 22 is what slice 1.6 moves under
      partition 1 (13+9, confirmed by `--collect-only`); starting from the passed
      count instead would land it 66 below the tree
- [ ] 3.10 **`IMG2_HOME=$(mktemp -d) pytest forge/tests -q` → zero failures, zero errors.** Not
      "the same failures as before". Numbers in the commit message. This RUN is the primary gate;
      the floor is a second check for a different loss. The floor sees tests that stop being
      collected; only the run sees tests that break while still being collected, and the withdrawn
      attempt lost tests both ways
- [ ] 3.10a **Clean the installed clone before anything is captured.** `~/.img2/plugins/character`
      is at `796dd9c` (= v0.2.0) but carries **12 untracked files** hand-copied from the withdrawn
      attempt (`tools/character_template.py`, `tools/scalp_exposure.py`, `tools/humanoid_proportions.py`,
      `tools/derive_character_rig.py`, `tools/make_character_*.py`, …), none of them in v0.2.0.
      `img2 doctor` reads the directory, not the SHA, and **FAILs today** because of them. Every
      capture below would otherwise photograph that attempt instead of this release. Preserve the
      files somewhere first if anyone still wants them, then `img2 remove character` and re-add
- [ ] 3.11 **Only now install.** `img2 add --link ./plugin-character`, then `img2 doctor`, output
      captured. Bar: **zero FAILs**; the multi-capability WARN is expected and is part of the
      captured baseline. First confirm the installed clone is clean — a clone carrying untracked
      files from an abandoned attempt makes every "with the plugin installed" capture a picture of
      that attempt rather than of the release
- [ ] 3.12 Checklist capture with the plugin installed: the contributed steps appear at the declared
      anchors, attributed to the provider, and `--profile character` resolves to exactly one

## 4. The documentation stops lying

- [ ] 4.1 `SKILL.md`: the profile list, the `character` / `animated-character` prose at `:65`,
      `:77`, `:80-83`, the **four** moving `grimoire/character/` links at `:150`, `:157`, `:161-162`
      (`:163-164` name the two hair pages, which **stay**), and the `humanoid_proportions.py`
      reference at **`:168`**. The `scalp_exposure.py` hard-gate lines at **`:293`** and `:362` are
      **left alone** — that file stays, so those lines remain true. Every runnable example states the
      plugin as prerequisite.
      (Re-measured against `6e60b5e`: an earlier revision cited `:170` and `:296`; `:296` is
      `vertex_region_gate.py`, an unrelated gate)
- [ ] 4.2 `docs/ARCHITECTURE.md`: `stage5_rig/` is restated as library, not checklist authority.
      The Hair table lists `scalp_field.py` and `scalp_exposure.py` and is **left alone** — both stay
      under D11, so the table is already correct. An earlier revision had this task removing them.
- [ ] 4.3 Sweep `grimoire/` for links into `grimoire/character/`
- [ ] 4.3a **Disposition the seven documents no task covers.** `rg -c "animated-character"` over
      `6e60b5e`: covered — `SKILL.md` (2, task 4.1), `docs/ARCHITECTURE.md` (2, task 4.2),
      `CHANGELOG.md` (3, task 4.5). **Uncovered** — `README.md` (4), `ROADMAP.md` (5),
      `docs/GLB_ANIMATED_CHARACTER_PROMPT.md` (6), `docs/STAGE_R_BACKLOG.md` (3),
      `docs/STAGE_R_TEST_PLAN.md` (2), `docs/standard-prompts/build.md` (1),
      `forge/stage3_build/run_gates.py` (1, a comment). Two carry runnable commands that break:
      `docs/STAGE_R_TEST_PLAN.md:179` and `docs/GLB_ANIMATED_CHARACTER_PROMPT.md:93` both invoke
      `--profile animated-character`. An entire document is named after the withdrawn profile —
      give it an explicit verdict: rename, rewrite, or delete
- [ ] 4.4 Machine check, **as a test in `forge/tests/`, not a command someone remembers to run**
      (tasks 3.10 and 5.4 already force the suite): (a) every path named in `SKILL.md`, `docs/` and
      `grimoire/` exists — zero dead links, and scoped to include **`README.md`** (`:89`, `:91`,
      `:94`, `:140`, `:148`, `:342`, `:346`) and **Python docstrings**, since
      `extract_landmarks.py:6` names `grimoire/character/reconstruction.md` and that module **stays**
      per D5 — task 3.6 repoints one such string by hand, which proves the class exists, and an
      earlier revision then scoped the machine check to exclude the class;
      (b) `rg -n "animated-character"` returns zero outside an explicit allowlist of historical
      records — `CHANGELOG.md` (`:76` records that v1.5.2 *added* the profile and must not be
      rewritten), `openspec/` and archived change directories — plus a decision on
      `docs/GLB_ANIMATED_CHARACTER_PROMPT.md`, which carries the identifier in its **filename**. (b) is the half an earlier revision missed:
      the check was scoped to paths, and `--profile animated-character` is not a path, so the plan's
      one mechanical doc gate passed green while `domain-step-contribution`'s "every document that
      taught the withdrawn identifier SHALL be updated" was violated in seven files
- [ ] 4.5 Base CHANGELOG: the breaking entry, the withdrawn profile, the re-init remedy

## 5. Release and acceptance

- [ ] 5.1 Plugin CHANGELOG 0.3.0: what it now serves, the withdrawn `animated-character`, the
      re-block trigger for the `rigging` gate. No line describes work not in the release
- [ ] 5.2 Plugin SKILL.md: it is no longer "rigging and animation" — it serves the whole track.
      Frontmatter version moves with `plugin.json`
- [ ] 5.3 Tag `v0.3.0` and push. **"Publish" here means the git tag, not npm**: `git ls-tree v0.2.0`
      returns 44 files with no `package.json` and no `.github/workflows/` — both exist only on the
      abandoned branch this change does not reuse — and `npm view @img2threejs/plugin-character`
      404s, as does the cs2 package, while the registry is reachable. All four installed plugins
      resolve through GitHub refs. If npm distribution is wanted, it is a separate change that adds
      the manifest and the publish workflow. Then `img2 add img2threejs/plugin-character` and
      `img2 doctor`: zero FAILs
- [ ] 5.4 A1 base suite, empty `IMG2_HOME`: zero failures, zero errors
- [ ] 5.5 A2 plugin suite standalone; A3 doctor clean, captured
- [ ] 5.6 A4 **both** oracles green with the plugin installed — the second run that makes them
      oracles rather than snapshots
- [ ] 5.7 A5 structural checklist parity capture; A9 both floors asserted at measured values
- [ ] 5.8 A6 fail-loud without the plugin, naming the missing provider; A8 removal round-trip
- [ ] 5.9 A7 generic run with no plugin installed authors a spec and passes strict validation
- [ ] 5.10 A10 every skip states a reason; no skip's reason is a missing plugin
- [ ] 5.11 A11 one real character image end to end **through the checklist** — `state.py init
      --profile character`, then drain every step, ending in a bound rig. Not an import by hand:
      that is what the withdrawn attempt's evidence actually was. **Evidence is the emitted
      TypeScript**, asserted to contain `THREE.SkinnedMesh`, `THREE.Skeleton`, `new THREE.Bone` and
      `skinIndex` — the same anti-tamper markers task 0.4 freezes — captured with the state file and
      the reference image. A state file full of `done` marks is not evidence: every step may be
      marked skipped with a reason, and `rig-bind` is an agent instruction whose evidence is whatever
      the agent records
- [ ] 5.11a **Resolve `runtime/scripts/export_mesh_buffers.mjs` before attempting A11.** Two of the
      nine rig steps — `mesh-freeze` and `mesh-parity-verify` — invoke it, and it is not in this
      repo: `ls -d runtime` fails and the path appears only in four `.md` files. This is a
      pre-existing defect in the shipped v0.2.0 plugin, not one this change introduces, but A11
      cannot be honest while two of its steps cannot run. Locate it, or record the two steps as
      skipped-with-reason and say so in the capture

## 6. Rollback

- [ ] 6.1 Rehearse before publishing 0.3.0, and rehearse the case that will actually occur.
      **Four** host links, not three — `~/.claude`, `~/.codex`, `~/.config/opencode` and
      `~/.pi/agent` — and all four point at `img2threejs-beta`, **not** the checkout this change
      edits, so anything driven through the host skill (A11 especially) exercises beta. Record their
      real targets. Rehearsing before the tag exists proves nothing: `img2 add` defaults to the
      newest reachable tag (§6), so pre-release it resolves v0.2.0 and "succeeds" trivially. Record
      the **post-release** command verbatim:
      `img2 remove character && img2 add img2threejs/plugin-character --ref v0.2.0`
- [ ] 6.1a **Base and plugin roll back together, or not at all.** v0.2.0's `domain.json` declares
      `animated-character` and its `character-contract-read` reads `grimoire/character/reconstruction.md`
      base-relative — deleted by 3.6. Rolling back only the plugin leaves a user with no `character`
      profile and a broken `animated-character` one. Name the base lever alongside the plugin one,
      and note that "flip to a named pre-move checkout" is a developer's lever: a user who installed
      the skill normally has no such checkout
- [ ] 6.2 Record the commands and the observed output, so the lever is documented rather than assumed

## 7. Follow-ups — filed, not implemented here

- [ ] 7.1 **Let a plugin contribute a component role and its rules.** An earlier revision filed this
      as "extract hair, trigger: `role: \"hair\"` stops being a base schema role" — stating the work
      as though it were a precondition that might arrive on its own. It will not: the role stops
      being base schema only when somebody builds the mechanism. `_ALLOWED` is seven keys —
      `id`, `setupSteps`, `setupAnchorBefore`, `passSteps`, `passAnchorBefore`, `specCollection`,
      `rigSteps` — every one of them *workflow*. There is no key for schema, so a plugin can fill a
      `role` field with `"hair"` but cannot make the base's validator, its material physics, its
      skinning partition or its pass orchestration know what that string obliges
      (`validate_sculpt_spec.py:1549`, `material_physics.py:210`, `geodesic_skinning.py:66`,
      `orchestrate_passes.py:138`). **Hair extraction is that change's first consumer, not its
      blocker**
- [ ] 7.2 Close out `extract-character-into-its-own-plugin`: it is superseded by this change. Its
      two ADDED capability deltas already exist in the book from its own first archive, so archiving
      it again throws at `specs-apply.js:212`; strip those deltas or delete its `specs/` folders.
      Same close-out covers the abandoned branches: `img2threejs-lab` @
      `apply/extract-character-into-its-own-plugin`, `plugin-character` @ `release/v0.3.0`, and
      `img2-harness` @ `apply/slice-4-contract-clause` — the last leaves
      `docs/PLUGIN_CONTRACT.md:458-467` as garbled interleaved prose. Nothing is broken today (the
      installed harness is 0.2.4 at revision 14 and that branch is not `main`), but the branch should
      not be inherited by accident
- [ ] 7.3 `stage5_rig/` dedup, when the factory's rig imports move behind a core API
- [ ] 7.4 Re-block the `rigging` gate when its four producer-less checks gain producers
