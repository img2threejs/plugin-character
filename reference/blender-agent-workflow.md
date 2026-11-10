# Agent coordination for Blender character authoring

Use with `blender-character-route.md`. This defines who decides, who writes which file, and what
each stage must hand over — a coordination contract, not an agent launcher and not a harness
profile.

## 1. The main session is the single coordinator

The main session owns every decision that changes the result or the contract: reference/identity
decisions (what the character is, which views are authoritative, which landmarks are measured
versus inferred); the API and schema budgets (sidecar schema, region ids, attribute names, file
layout, the `character-plan.json` fields); visual, code and security review of every worker's
output; and final sign-off with the acceptance decision.

Workers propose; the main session decides. Workers do not renegotiate scope between themselves.

Use the **configured roles** (`scout`, `implementer`, `debugger`, `verifier`, and `sonic` where the
harness provides it). Never **hard-code model selection** — select configured roles rather than
provider/model selectors in the assignment. Apply conditional model-specific policy separately.

| Role | Use for | Never for |
|---|---|---|
| `scout` | read-only research on unmapped sources, licences, API facts | any file edit |
| `implementer` | an approved component, material recipe or native bpy script | deciding scope |
| `debugger` | one bounded defect with a reproduction | broad refactoring |
| `sonic` | an exact mechanical prescription with no open judgement | checklist padding |
| `verifier` | acceptance evidence, after all writers finish | editing source |

For MiniMax-M3 workers, state the preference explicitly: **keep thinking enabled and use the
highest supported OMP role level; prioritize correctness and completeness over token savings.** Do
not claim the role label sets an API reasoning depth, and do not invent a "maximum mode" the API
does not have. Other configured models keep their routine effort settings.

## 2. Assignment contract

Every assignment states all of these fields; a worker that cannot act on one returns the blocker
instead of guessing.

- **cwd and rules** — the exact checkout, applicable repository instructions, and "preserve
  unrelated dirty changes".
- **Target** — the observable outcome, the reference image paths, the measured landmarks it may
  use, and the explicit non-goals.
- **Ownership** — allowed and prohibited files (other workers' files, the master `.blend`, shared
  manifests). Name the exact output paths.
- **Input/output contract** — input files (with paths and hashes), required output paths and
  formats, naming conventions, units/axes, and the acceptance thresholds for this slice.
- **Prohibited edits** — e.g. no editing the job's `character-plan.json`, no writing into the
  integrated `.blend`, no overwriting another worker's export directory.
- **Evidence commands** — the exact commands and required environment the worker may run to
  produce evidence, and what it must report back.
- **Execution** — writers **skip build, lint, tests and formatters during the writing assignment**;
  the parent/verifier runs integrated validation after all writers finish. A focused runtime
  reproduction (a disposable fixture, a single export, a browser probe) needs explicit
  main-session authorization, and its observations are reported without claiming the integrated
  gate passed.

## 3. Decompose by artifact, not by checklist

Fan out **independent** garment, texture and material components as separate files so they can
proceed in parallel. Keep **one integration owner** for the assembled `.blend` and the main
authoring script; that owner appends component data through a reviewed integration script rather
than concatenating competing scene scripts. Dependent stages run **sequentially**, each consuming
the previously accepted artifact and hash:

```
geometry freeze → UV/PBR → rig/weights → masks + export → runtime/browser
```

A stage that receives a changed upstream artifact revalidates its own dependencies; it does not
silently continue, and workers never write to one `.blend` at the same time. Rules that keep this
honest:

- **No recursive delegation:** a worker does not spawn further workers. **No secondary
  orchestrator:** only the main session coordinates.
- **No agent created only to tick a checklist item.** If a slice needs no independent judgement,
  the main session does it inline.
- **No self-approval.** A worker never signs off its own visual quality, and no worker approves
  the shipped result. Verification runs after the writers, from the integrated state.

## 4. Staged handoff artifacts

Each stage hands over a named artifact, not a claim, and records the SHA-256 of every produced
file. Paths below are **job-directory** artifacts (the workspace named by
`blender-character-route.md`), not files inside this plugin.

| Stage | Artifact | Contents |
|---|---|---|
| Reference | job files: anatomy record + camera notes | measured landmarks with confidence, camera/projection assumption, observed vs inferred anatomy, open uncertainties |
| Build | job files: main build script + component recipes, checkpoint `.blend`s | runnable native scripts, parameters separated from mesh ops, editable master |
| Assets | job asset manifest + UV/PBR evidence | source paths, licences, hashes, texel density, albedo-only and normal-off captures |
| Rig | job rig inventory + pose captures | joint list, weight statistics, per-joint measured deltas, neutral-parity result |
| Interaction | job files: region config, prepared `.blend`, GLB, sidecar `softbody.json`, receipt `preparation.json` | region config, export working copy and integrity receipt |
| Runtime | browser captures + runtime metrics | fixed views, neutral/deformed metrics, contact and decay measurements, console errors |

A stage that cannot produce its artifact names the missing prerequisite (reference quality,
licence, tool access, capture ability) and stops; it does not switch to neural generation, a
generic avatar, a flat photo plane or an unbounded retry loop.

## 5. Screenshot and fixture discipline

- Every screenshot is **attributed to the final artifact hashes**; a capture of an earlier build is
  labelled as such. Run a **fixed view batch**: reference, front, quarter (both), side, rear, plus
  head/face and hand close-ups, from a locked camera/light contract and the same pose set.
- **Paired metrics**: neutral and deformed under the *same* bone pose, compared per region, so the
  difference is the deformation and not the camera.
- A geometric diagnostic fixture is never a reference avatar. The bundled
  `../examples/softbody/` fixture proves the runtime path, not likeness, collision or performance.
- Source fidelity is checked against the admitted reference; topology is checked **scale-aware**
  (relative to the recorded figure height `H`), not by absolute counts. Device performance is
  reported only when measured on that device; a desktop viewport is not a phone result.

## 6. Repair discipline
Repair **one causal group per iteration** and re-measure it. Do not retune a threshold to make a
failing check pass, relabel a mismatched render as accepted, re-freeze geometry to hide a rigging
regression, or fall back to a neural mesh generator, a paid asset or an unrestricted download.
Obey the route's correction caps, and **stop only on a real stop condition**: repeated attempts
that no longer improve the measurement, an exhausted correction budget, or an actual missing
prerequisite (reference quality, licence, tool access, capture ability). Never stop merely
because one fix was attempted while actionable repairs remain. When you do stop, name the missing
prerequisite; do not switch to neural generation, a generic avatar, a flat photo plane or an
unbounded retry loop. Record what changed, what was re-measured and what is still open.

## 7. Main-session integration checklist

1. Read the workers' actual files and artifacts, not only their reports, and confirm the integrated
   `.blend` opens, regenerates from the build script, and matches the recorded component list and
   bounds.
2. Run the relevant repository regression **once, when plugin implementation changed** (for example
   `python3 -m unittest discover -s tests` and `npm run test:softbody`, with `IMG2_CC5_PYTHON` set
   to a real bpy interpreter to include the preparation roundtrip). A job-only modeling edit that
   changes no plugin code does not require the whole suite.
3. **Always run the actual native export and the actual browser behaviour on the final job
   artifact.** Tests alone cannot validate a new character: the exported GLB must load, the rig
   must move, the regions must respond, and the captures must exist.
4. Verify the exported skin's joint order and inverse binds against the loaded GLB, and the
   neutral-parity result; review the view batch and the paired neutral/deformed metrics, and record
   remaining mismatches.
5. Record acceptance separately for appearance and for interaction.
6. Publish the final report: changed files, source evidence, measured results, and open blockers.

## Sources

- `blender-character-route.md` — stage order, deliverables, stop conditions
- `blender-geometry-workflow.md` — continuous surfaces, destructive-before-freeze, provenance
- `blender-source-assets.md` — rights, catalogues, asset manifest fields
- `blender-pbr-workflow.md` — skin vs cloth materials, UV/PBR bake and freeze order
- `blender-rig-interaction.md` — skeleton derivation, weights, soft regions, runtime limits
- `blender-export-parity.md` — verified Blender/Three.js export gaps that constrain rig claims
- `softbody-character-route.md`, `softbody-runtime.md` — mask authoring, preparation, acceptance
