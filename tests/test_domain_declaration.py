"""The animated-character domain declaration (OpenSpec change `extract-animated-character`).

domain.json is the CANONICAL rig-step order after the base's in-repo module was deleted — the only
place the real order exists. The order pins below assert its ids against a separately declared
expected list in THIS file: two files, so one careless edit changes one of them and the pin trips.
That is the repo's existing drift-pin pattern (test_rig_spec_agreement.py), replacing the base's
StageROrderIsLoadBearing class, whose authority moved here with the module.

Why the order is load-bearing and not a preference (moved verbatim from the base module's docstring):
  - mesh repair happens BEFORE the freeze, because a mesh may legitimately need fixing;
  - the freeze happens BEFORE any rig work, because after it the geometry is evidence;
  - mesh-parity is verified AFTER binding, because that is the only moment the claim
    "implementation did not touch the mesh" can be falsified.
Moving the freeze later would let a bind quietly rewrite vertices and then freeze the result, and
the manifest would certify the damage instead of catching it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = json.loads((ROOT / "domain.json").read_text(encoding="utf-8"))
GATES = json.loads((ROOT / "gates.json").read_text(encoding="utf-8"))

# The expected rig order, declared HERE, separately from domain.json (the two-file pin).
EXPECTED_RIG_ORDER = [
    "rig-contract-read",
    "glb-rig-reference",
    "mesh-repair",
    "mesh-freeze",
    "rig-payload-validate",
    "rig-bind",
    "mesh-parity-verify",
    "clip-measure",
    "rig-gates",
]

# Content pins for the reference docs the rig-contract-read step names. The base keeps its own
# copies; nothing else asserts the two stay equal, so divergence must fail HERE, not pass silently.
# Re-record deliberately, in the same commit as a doc change.
REFERENCE_DOC_HASHES = {
    "reference/animation-contract.md": "c1c2c931e602854b8dba696dd6d1b7779290ac5b86c9d96e2c24ab784b453118",
    "reference/character-rigging-animation-1.5.2.md": "fb1aa7c45a82effcb563b2c0669ebb596c91c219d686ccdfe4329cb3fed9ae9c",
}


def rig_ids() -> list[str]:
    return [step_id for step_id, _ in DOMAIN["rigSteps"]]


class RigOrderIsLoadBearing(unittest.TestCase):
    def index(self, step_id: str) -> int:
        ids = rig_ids()
        self.assertIn(step_id, ids)
        return ids.index(step_id)

    def test_the_full_order_matches_the_two_file_pin(self):
        self.assertEqual(rig_ids(), EXPECTED_RIG_ORDER)

    def test_repair_precedes_the_freeze(self):
        self.assertLess(self.index("mesh-repair"), self.index("mesh-freeze"))

    def test_the_freeze_precedes_every_rig_step(self):
        freeze = self.index("mesh-freeze")
        self.assertLess(freeze, self.index("rig-payload-validate"))
        self.assertLess(freeze, self.index("rig-bind"))

    def test_parity_is_verified_after_the_bind(self):
        self.assertLess(self.index("rig-bind"), self.index("mesh-parity-verify"))

    def test_the_glb_reference_precedes_binding(self):
        self.assertLess(self.index("glb-rig-reference"), self.index("rig-bind"))

    def test_the_contract_is_read_first_and_the_gates_run_last(self):
        self.assertEqual(rig_ids()[0], "rig-contract-read")
        self.assertEqual(rig_ids()[-1], "rig-gates")


class DeclarationShape(unittest.TestCase):
    def test_domain_id_and_anchor(self):
        self.assertEqual(DOMAIN["id"], "animated-character")
        self.assertEqual(DOMAIN["setupAnchorBefore"], "local-spec-search")

    def test_setup_steps_are_the_two_base_relative_character_steps(self):
        # Deliberately base-relative: the static `character` domain stays in-repo and owns these
        # assets. A base-side agreement test pins that the referenced paths exist.
        ids = [s for s, _ in DOMAIN["setupSteps"]]
        self.assertEqual(ids, ["character-contract-read", "character-landmarks"])
        commands = dict(DOMAIN["setupSteps"])
        self.assertIn("grimoire/character/reconstruction.md", commands["character-contract-read"])
        self.assertIn("forge/stage1_intake/extract_landmarks.py {reference}", commands["character-landmarks"])

    def test_every_tool_invocation_bypasses_workspace_resolution(self):
        # Parity over confinement (design D3): each tool row carries --out or --payload so no step
        # tool reaches resolve_workspace, whose checkout refusal the base pipeline cannot satisfy.
        commands = dict(DOMAIN["rigSteps"])
        for step_id in ("glb-rig-reference", "mesh-freeze", "rig-payload-validate",
                        "mesh-parity-verify", "clip-measure"):
            self.assertRegex(commands[step_id], r"--(out|payload)\s", step_id)
        self.assertIn("--payload rig-gate-payload.json", commands["rig-gates"])
        for step_id, command in DOMAIN["rigSteps"]:
            self.assertNotIn("{workspace}", command, step_id)
            self.assertNotIn("<", command, step_id)

    def test_load_bearing_caveats_survive_as_prose_rows(self):
        commands = dict(DOMAIN["rigSteps"])
        self.assertIn("structural payload integrity ONLY", commands["rig-payload-validate"])
        self.assertIn("an unevaluated gate is not a pass", commands["rig-gates"])
        # Prose-row classification: the caveat-bearing rows must not lead with an interpreter,
        # or doctor's metachar hardening refuses their parentheses.
        for step_id in ("glb-rig-reference", "rig-payload-validate", "clip-measure", "rig-gates"):
            self.assertTrue(commands[step_id].startswith("Run "), step_id)

    def test_the_rigging_gate_is_declared_non_blocking(self):
        # Four of twelve checks have no producer yet, so the gate cannot return pass on a healthy
        # rig; a blocking declaration would halt any post-rig sweep on an honest verdict.
        # Re-block trigger: the producers exist and the oracle rig passes (CHANGELOG v0.2.0).
        rigging = next(g for g in GATES if g["id"] == "rigging")
        self.assertIs(rigging["blocking"], False)


class ReferenceDocDriftPins(unittest.TestCase):
    def test_reference_docs_match_their_recorded_hashes(self):
        for rel, expected in REFERENCE_DOC_HASHES.items():
            actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, f"{rel} drifted; re-record deliberately")


class GatePayloadMode(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        import os
        env = dict(os.environ)
        env.setdefault("IMG2_HOME", str(Path.home() / ".img2"))
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "gate_rigging.py"), *args],
            capture_output=True, text=True, env=env,
        )

    def test_payload_mode_works_from_a_checkout_cwd(self):
        # The plugin checkout contains plugin.json (a checkout marker); --payload must never
        # consult resolve_workspace, so this succeeds where --workspace would refuse. Reuses the
        # in-suite full payload builder so the two files cannot drift.
        from tests.test_gate_rigging import full_payload
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "rig-gate-payload.json"
            payload.write_text(json.dumps(full_payload()), encoding="utf-8")
            proc = self._run("--payload", str(payload))
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["kind"], "img2.gate-verdict")
        self.assertIn(envelope["status"], ("pass", "fail"))
        self.assertNotIn("looks like a skill or plugin checkout", " ".join(envelope["reasons"]))

    def test_missing_payload_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.json"
            proc = self._run("--payload", str(missing))
        self.assertEqual(proc.returncode, 2)
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["status"], "error")
        self.assertTrue(any("absent.json" in reason for reason in envelope["reasons"]))


if __name__ == "__main__":
    unittest.main()
