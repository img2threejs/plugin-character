"""The character domain declaration, and the manifest that carries it.

The domain id is now `character`, not `animated-character` (OpenSpec change
`extract-character-sculpt-into-the-plugin`, D1): one id that always carries the nine rig steps. A
static build skips a rig step with a recorded reason, which the checklist already supports; a second
profile that omitted the Stage R gates entirely is how animation shipped broken in 1.5.1.

`img2 doctor` checks this file's subject too, but only once installed — after the tag is cut. The
harness rules transcribed below are checked here instead, each with the line of `bin/img2.mjs` that
defines it, and where the base and this file could drift the base's real parser is used.

WHY THE PATH CHECK EXISTS. The withdrawn attempt shipped `character-contract-read` pointing at
`grimoire/character/reconstruction.md` — BASE-relative, correct while the pages lived there and
dangling the moment they moved. Nothing failed: a step is spliced as text and rendered for an agent,
so a dead path becomes a step nobody can carry out rather than an error anybody sees.

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
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT.parent / "img2threejs"
BASE_RELATIVE_REGISTRY = Path("forge/_shared/domains/__init__.py")
MANIFEST = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))

# Transcribed from img2-harness `bin/img2.mjs`, each with the line that defines it. A plugin cannot
# import the harness's JavaScript, so these are pinned duplicates in the sense BASE_OWNED is.
ALLOWED_PLACEHOLDERS = {"{plugin_dir}", "{reference}", "{spec}", "{pass_id}"}   # :966
SHELL_METACHARS = re.compile(r"[;|&$`><()\n]")                                 # :732
INTERPRETERS = {"python3", "python", "node", "bash", "sh"}                      # :745
DOMAIN_KEYS = {"id", "setupSteps", "setupAnchorBefore", "passSteps", "passAnchorBefore",
               "specCollection", "rigSteps"}                                    # :940
STEP_KEYS = ("setupSteps", "passSteps", "rigSteps")
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
        self.assertEqual(DOMAIN["id"], "character")
        self.assertEqual(DOMAIN["setupAnchorBefore"], "local-spec-search")

    def test_animated_character_is_withdrawn_from_every_declaration(self):
        for path in ("domain.json", "plugin.json"):
            self.assertNotIn("animated-character", (ROOT / path).read_text(encoding="utf-8"), path)

    def test_setup_steps_are_the_three_the_domain_contributes(self):
        # The grimoire paths are PLUGIN-relative now: those pages moved here, and the base deletes
        # its copies. `extract_landmarks.py` stays base-relative because it stays in the base.
        ids = [s for s, _ in DOMAIN["setupSteps"]]
        self.assertEqual(ids, ["character-contract-read", "character-landmarks",
                               "character-spec-augmentation"])
        commands = dict(DOMAIN["setupSteps"])
        self.assertIn("{plugin_dir}/grimoire/character/reconstruction.md",
                      commands["character-contract-read"])
        self.assertNotIn(" grimoire/", commands["character-contract-read"])
        self.assertIn("forge/stage1_intake/extract_landmarks.py {reference}", commands["character-landmarks"])
        self.assertIn("{plugin_dir}/tools/emit_spec_augmentation.py",
                      commands["character-spec-augmentation"])

    def test_the_augmentation_step_runs_after_the_step_producing_its_input(self):
        # Within a group the splice preserves order, so `anatomy.json` exists by then only because
        # character-landmarks is listed first. Anchoring alone does not buy this.
        ids = [s for s, _ in DOMAIN["setupSteps"]]
        self.assertLess(ids.index("character-landmarks"), ids.index("character-spec-augmentation"))

    def test_the_declared_collection_is_one_this_plugin_contributes(self):
        profile = json.loads((ROOT / "spec_search_profile.json").read_text(encoding="utf-8"))
        self.assertIn(DOMAIN["specCollection"], profile["collections"])

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


def _rows(domain: dict) -> list[tuple[str, str, str]]:
    return [(key, step_id, command)
            for key in STEP_KEYS for step_id, command in domain.get(key, [])]


def _is_command_row(command: str) -> bool:
    """A path form or a known interpreter marks a row something a caller actually runs (`:970`).

    Everything else is prose an agent reads, where a parenthesis is English, not a shell hazard.
    The existing rig steps lean on this: `glb-rig-reference` begins with the word "Run", so its
    explanatory parentheses are legal exactly because nothing execs it.
    """
    leading = (shlex.split(command)[0] if command.strip() else "").replace("{plugin_dir}", "/p")
    return "/" in leading or leading in INTERPRETERS


class HarnessRules(unittest.TestCase):
    """The checks `img2 doctor` runs, run before the commit instead of after the tag."""

    def test_it_carries_no_key_the_registry_would_refuse(self) -> None:
        # `_validate` RAISES on an unknown key rather than ignoring it, so a typo is a hard failure
        # for every run on the machine — not just a character one.
        self.assertEqual(sorted(set(DOMAIN) - DOMAIN_KEYS), [])

    def test_every_step_group_with_steps_declares_its_anchor(self) -> None:
        for steps_key, anchor_key in (("setupSteps", "setupAnchorBefore"),
                                      ("passSteps", "passAnchorBefore")):
            if DOMAIN.get(steps_key):
                self.assertTrue(DOMAIN.get(anchor_key), f"{steps_key} needs {anchor_key}")

    def test_every_row_is_an_id_and_command_pair_of_strings(self) -> None:
        for key in STEP_KEYS:
            for row in DOMAIN.get(key, []):
                self.assertEqual(len(row), 2, f"{key}: {row!r}")
                self.assertTrue(all(isinstance(v, str) and v for v in row), f"{key}: {row!r}")

    def test_step_ids_are_unique_across_every_group(self) -> None:
        ids = [step_id for _, step_id, _ in _rows(DOMAIN)]
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_every_placeholder_is_in_domain_json_s_own_closed_set(self) -> None:
        # Not the harness's steps.json set: `{workspace}` and `{image}` are legal there and raise
        # KeyError in `workflow_state._format_command`, so they crash at runtime, not at doctor.
        for key, step_id, command in _rows(DOMAIN):
            for brace in re.findall(r"\{[^{}]*\}", command):
                self.assertIn(brace, ALLOWED_PLACEHOLDERS, f"{key}/{step_id}")

    def test_no_command_row_needs_a_shell(self) -> None:
        for key, step_id, command in _rows(DOMAIN):
            if not _is_command_row(command):
                continue
            stripped = command
            for placeholder in ALLOWED_PLACEHOLDERS:
                stripped = stripped.replace(placeholder, "")
            self.assertIsNone(SHELL_METACHARS.search(stripped),
                              f"{key}/{step_id} contains a shell metacharacter")

    def test_no_row_uses_an_angle_bracket_pseudo_placeholder(self) -> None:
        # A shell reads `<name>` as redirection. The base's own steps use them; a plugin's may not.
        for key, step_id, command in _rows(DOMAIN):
            self.assertIsNone(re.search(r"<[^<>\n]*>", command), f"{key}/{step_id}")

    def test_every_plugin_relative_path_a_step_names_exists(self) -> None:
        named = 0
        for key, step_id, command in _rows(DOMAIN):
            for match in re.findall(r"\{plugin_dir\}/(\S+)", command):
                target = ROOT / match.rstrip(".,)")
                self.assertTrue(target.is_file(), f"{key}/{step_id} names {match}, which is missing")
                named += 1
        self.assertGreater(named, 0, "no step names a plugin-relative path; the check tests nothing")


class TheManifest(unittest.TestCase):
    def test_the_sculpt_edge_is_declared(self) -> None:
        edges = {(c["from"], c["to"]) for c in MANIFEST["capabilities"]}
        self.assertIn(("image", "character-sculpt-spec"), edges)

    def test_the_rigging_edges_this_plugin_already_served_are_kept(self) -> None:
        edges = {(c["from"], c["to"]) for c in MANIFEST["capabilities"]}
        self.assertIn(("character-mesh", "rigged-character"), edges)
        self.assertIn(("glb", "rig-reference"), edges)

    def test_the_name_is_the_domain_id(self) -> None:
        # The registry keys domains by `domain.json`'s id and the harness keys rows by the manifest
        # name; they are different files and nothing outside this assertion ties them together.
        self.assertEqual(MANIFEST["name"],
                         json.loads((ROOT / "domain.json").read_text(encoding="utf-8"))["id"])

    def test_the_skill_frontmatter_version_moves_with_the_manifest(self) -> None:
        front = (ROOT / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        declared = dict(line.split(": ", 1) for line in front.strip().splitlines() if ": " in line)
        self.assertEqual(declared["version"], MANIFEST["version"])


class AgreesWithTheBase(unittest.TestCase):
    """Checked against the base's real registry rather than a transcription of it."""

    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("IMG2THREEJS_BASE")
        root = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
        if not (root / BASE_RELATIVE_REGISTRY).is_file():
            where = "from IMG2THREEJS_BASE" if configured else "the default; IMG2THREEJS_BASE is unset"
            message = ("the declaration/base agreement needs the base checkout: set IMG2THREEJS_BASE "
                       f"to an img2threejs checkout containing {BASE_RELATIVE_REGISTRY}. Looked in "
                       f"{root} ({where}).")
            if os.environ.get("IMG2THREEJS_REQUIRE_BASE") == "1":
                raise RuntimeError(message + " IMG2THREEJS_REQUIRE_BASE=1 forbids skipping this.")
            raise unittest.SkipTest(message + " Skipping: the declaration's own shape is still "
                                              "pinned above, but this run did NOT compare it.")
        sys.path[:0] = [str(root / "forge"), str(root / "forge" / "_shared")]
        pass

    def test_the_registry_accepts_this_declaration(self) -> None:
        from domains import _validate  # noqa: PLC0415
        _validate(dict(DOMAIN), ROOT / "domain.json")

    def test_the_allowed_keys_transcribed_here_are_the_registry_s(self) -> None:
        from domains import _ALLOWED  # noqa: PLC0415
        self.assertEqual(DOMAIN_KEYS, set(_ALLOWED))

    def test_the_setup_anchor_is_a_real_base_step(self) -> None:
        from workflow_state import SETUP_STEPS  # noqa: PLC0415
        self.assertIn(DOMAIN["setupAnchorBefore"], [step_id for step_id, _ in SETUP_STEPS])

    def test_the_augmentation_step_runs_before_the_base_reads_its_artifact(self) -> None:
        """`spec-authoring` passes `--augmentation spec-augmentation.json` unconditionally.

        The artifact has to exist by then or the base authors the generic skeleton and the whole
        extraction contributes nothing — silently, since a missing augmentation is not an error.
        """
        from workflow_state import SETUP_STEPS  # noqa: PLC0415
        order = [step_id for step_id, _ in SETUP_STEPS]
        authoring = dict(SETUP_STEPS)["spec-authoring"]
        self.assertIn("--augmentation spec-augmentation.json", authoring)
        self.assertLess(order.index(DOMAIN["setupAnchorBefore"]), order.index("spec-authoring"))


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
