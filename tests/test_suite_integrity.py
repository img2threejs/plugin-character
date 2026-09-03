"""This suite must not shrink silently.

A module that fails to import is replaced by one synthetic `_FailedTest`, so N real tests become 1
error and the count drops with nothing naming what went missing. That risk is sharper here than
almost anywhere: every test module in this plugin resolves its imports through a module-level
`sys.path.insert(..., "tools")`, so one renamed tool silently costs a whole file's worth of tests.

Discovery runs in a subprocess deliberately. Discovering a suite from inside itself is order- and
path-dependent -- importing a test module runs its module-level `sys.path.insert`, so a second
in-process discover resolves against a path the first did not have.

Modelled on plugin-cs2/tests/test_suite_integrity.py, which was written after an indentation error
left three tests uncollected and only a manual `def test_` count caught it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Raise when tests are added. Never lower it to make a red suite green: a drop means tests stopped
# being collected, which is the failure this file exists to catch.
#
# Where the number came from: 218 tests ported from the base skill's forge/tests (test_clip_features
# 40, test_action_design 38, test_glb_rig_reference 32, test_mesh_parity 31, test_skin_conditioning
# 25, test_emit_animation_runtime 25, test_geodesic_skinning 12, test_rig_milestone0 9,
# test_validate_rig_payload 6), plus 9 in test_gate_rigging. This file's own 2 are not counted --
# the probe discovers them too, but a floor that counts the checker inflates itself.
COLLECTED_FLOOR = 235

_PROBE = """
import json, unittest
def leaves(s):
    for x in s:
        if isinstance(x, unittest.TestSuite):
            yield from leaves(x)
        else:
            yield x
tests = list(leaves(unittest.TestLoader().discover("tests", pattern="test_*.py")))
print(json.dumps({
    "collected": len(tests),
    "failed": [t.id() for t in tests if type(t).__name__ == "_FailedTest"],
}))
"""


@lru_cache(maxsize=1)
def _discover() -> dict:
    proc = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"test discovery itself failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


class SuiteIntegrity(unittest.TestCase):
    def test_no_module_fails_to_import(self) -> None:
        broken = _discover()["failed"]
        self.assertEqual(broken, [], "a test module failed to import: " + "; ".join(broken))

    def test_collected_count_has_not_dropped(self) -> None:
        collected = _discover()["collected"]
        self.assertGreaterEqual(
            collected,
            COLLECTED_FLOOR,
            f"collects {collected} tests but the floor is {COLLECTED_FLOOR}; find out which module "
            "stopped importing before touching this number",
        )


if __name__ == "__main__":
    unittest.main()
