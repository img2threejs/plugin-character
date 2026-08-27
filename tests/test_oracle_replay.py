"""The correctness oracle for extracting rigging into this plugin.

If any output drifts by a single byte during the extraction, this fails.

Deliberately a byte comparison rather than a semantic one. A semantic assertion has to enumerate
what matters, and the whole point of an oracle is to catch the change nobody predicted -- the
renamed field, the reordered list, the float that gained a digit. Every one of those is invisible
to an assertion written by someone who already knows what the code does.

WHY THIS EXISTS AT ALL. The rigging modules were moved out of `forge/stage5_rig/`, renamed,
rewired to import each other under new names, and had a `forge.stage1_intake.probe_glb` import
removed by copying the functions it supplied. Each of those is a change that compiles, imports and
passes a unit test while producing different bytes. `rig_glb_reference` is the module most exposed:
it lost a base import, and the replacement was hand-copied.

WHAT IS FROZEN, AND THE ONE THING THAT IS NOT. The frozen artifact is the full rig report for a
real 113-node GLB carrying a real skin and eleven real clips. The `path` key is dropped before
comparison and before freezing: it is the absolute path of the input on whichever machine ran it,
so freezing it would make the oracle fail on every other machine for a reason that has nothing to
do with correctness. Everything else is compared verbatim.

THE SUBJECT. `tripo.glb` from the showcase checkout -- the asset the 1.5.2 pipeline was distilled
from, and the one Slice 0 observed running. The oracle and the damage baseline therefore describe
the same character rather than two different ones.

The comparison is canonical JSON (`sort_keys`, no whitespace) rather than raw file bytes, so a
formatter changing its mind is not a reported change while a changed *number* still is. That is the
same reasoning `rig_mesh_parity` uses for hashing packed bytes rather than JSON text.

Pure Python 3.10+ stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PLUGIN = TESTS.parent
TOOLS = PLUGIN / "tools"
FIXTURE = TESTS / "fixtures" / "oracle-tripo" / "glb-rig.json"

# The subject. Overridable so the oracle can be re-frozen on another checkout, and skipped rather
# than failed when the showcase is not present -- a machine with only the plugin still runs green.
DEFAULT_GLB = Path(
    os.environ.get(
        "IMG2_ORACLE_GLB",
        str(Path.home() / "Documents/personal/img2threejs-showcase/public/mesh/tripo.glb"),
    )
)

# Machine-specific, and therefore excluded from the comparison. See the module docstring.
VOLATILE_KEYS = ("path",)


def canonical(payload: dict) -> bytes:
    """Canonical JSON: key order fixed, whitespace removed, volatile keys dropped."""
    stripped = {key: value for key, value in payload.items() if key not in VOLATILE_KEYS}
    return json.dumps(stripped, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: dict) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


class OracleReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE.is_file():
            raise unittest.SkipTest(f"oracle fixture missing at {FIXTURE}")
        if not DEFAULT_GLB.is_file():
            raise unittest.SkipTest(
                f"oracle subject missing at {DEFAULT_GLB}; set IMG2_ORACLE_GLB to a GLB with a "
                f"skin and clips, or re-freeze the fixture"
            )
        cls.frozen = json.loads(FIXTURE.read_text(encoding="utf-8"))
        # An explicit throwaway workspace, deliberately not the checkout: `resolve_workspace`
        # refuses a directory holding SKILL.md/plugin.json, which is the anti-footgun working --
        # a tool that wrote into its own checkout would leave artifacts in git rather than in the
        # user's project. This oracle found that rule by tripping it.
        cls._workspace = tempfile.mkdtemp(prefix="img2-oracle-ws-")
        completed = subprocess.run(
            [sys.executable, str(TOOLS / "rig_glb_reference.py"), str(DEFAULT_GLB),
             "--workspace", cls._workspace],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"rig_glb_reference exited {completed.returncode}: {completed.stderr[-2000:]}"
            )
        cls.replayed = json.loads(completed.stdout)

    def test_the_replay_is_byte_identical_to_the_frozen_run(self) -> None:
        """The whole argument for this file. Any drift, anywhere, fails here."""
        self.assertEqual(
            digest(self.replayed),
            digest(self.frozen),
            "rig report drifted from the frozen oracle; diff the canonical JSON to see what moved",
        )

    def test_the_frozen_run_is_not_degenerate(self) -> None:
        """An empty or trivial output must not be able to pass by matching an equally empty freeze.

        Without this, freezing a broken run would make every later slice faithfully preserve it --
        which is the failure mode the whole Slice 0 ordering exists to prevent.
        """
        self.assertEqual(self.frozen["skinCount"], 1)
        self.assertEqual(self.frozen["clipCount"], 11)
        self.assertEqual(len(self.frozen["joints"]), 42)
        self.assertTrue(self.frozen["ok"])

    def test_the_skin_ordering_survived_the_move(self) -> None:
        """§R0.3: bones[i] is the node for skin.joints[i]; the ordering is the SKIN'S.

        `joints[0]` is node 40 on this asset, not node 0. A move that quietly re-sorted the joint
        list -- by node index, by name, by traversal -- would still produce 42 joints and would
        still look right in a summary. This is the assertion that catches it.
        """
        self.assertEqual(self.replayed["joints"][0]["nodeIndex"], 40)
        self.assertEqual(self.replayed["joints"][0]["nodeName"], "Root")

    def test_the_volatile_key_is_the_only_thing_excluded(self) -> None:
        """Guard the exclusion list itself: it is the one place drift could hide legitimately."""
        self.assertEqual(VOLATILE_KEYS, ("path",))
        self.assertIn("path", self.replayed, "if `path` stopped being emitted, re-freeze the oracle")

    def test_the_comparison_would_catch_a_single_changed_number(self) -> None:
        """A pin that cannot fail is not a pin."""
        perturbed = json.loads(json.dumps(self.frozen))
        perturbed["joints"][0]["nodeIndex"] += 1
        self.assertNotEqual(digest(perturbed), digest(self.frozen))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(getattr(cls, "_workspace", ""), ignore_errors=True)

    def test_the_comparison_ignores_formatting_but_not_content(self) -> None:
        """Canonical JSON, not raw bytes: a reformat is not a regression, a changed value is."""
        reformatted = json.loads(json.dumps(self.frozen, indent=7, sort_keys=False))
        self.assertEqual(digest(reformatted), digest(self.frozen))


if __name__ == "__main__":
    unittest.main()
