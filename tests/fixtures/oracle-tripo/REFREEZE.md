# Re-freeze log

An oracle that is re-frozen without accounting is not an oracle. Every re-freeze is recorded here
with what changed and why it was accepted.

## 2026-08-27 — the artifact envelope

**Caught by:** `test_the_replay_is_byte_identical_to_the_frozen_run`, on the Slice 6 workspace and
artifact plumbing.

**Diff, measured — exactly two keys, nothing else:**

| key | before | after |
|---|---|---|
| `kind` | `glb-rig-reference` | `rigging.glb-rig-v1` |
| `provenance` | absent | `{"provider": "character", "version": "0.1.0"}` |

Every other key was byte-identical: all 42 joints in skin order, 11 clips, the inverse-bind
accessor, `deformVsTechnical`. The change touched the envelope and **not one measurement**, which is
what made it safe to accept.

**Why accepted:** namespaced artifact kinds and a provenance stamp are the Slice 6 deliverable. A
reader is required to raise on an unexpected `kind`, so the rename is the point rather than a side
effect.

**What would NOT have been accepted:** a changed joint count, a reordered joint list, a moved
`nodeIndex`, a different clip duration. The oracle's other five assertions cover exactly those, and
they stayed green through this re-freeze — so the re-freeze narrowed nothing.
