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
# THE FLOOR IS THE MEASURED COUNT, and the measurement is the probe below — not a tally kept by
# hand. v0.2.0 declared 235 while actually collecting 258, so 23 tests could have stopped being
# collected with nothing going red. That gap was not a drift; the 235 was a hand-built sum that was
# never checked against a run, and it also excluded this file's own 2 on the reasoning that a floor
# counting its own checker inflates itself. It does, by exactly 2, every release, forever — which is
# a smaller error than the 23 the hand-built sum cost. So the floor is now simply what the probe
# returns, this file included, and re-measuring it is one command:
#
#   IMG2_HOME=$HOME/.img2 python3 -m pytest tests/ -q --collect-only | tail -2
#
# Arithmetic for this value, so the next reader can check it rather than trust it:
#
#     258   measured on a clean v0.2.0 checkout (226 passed, 32 skipped)
#   +  14   test_character_rig_derivation, moved from the base with its subject (13 there, plus
#           one new: the rig is now admitted through merge_spec_augmentation, and nothing asserted
#           validate_rig_admission passes on a plugin's submission)
#   +   9   test_humanoid_proportions, moved from the base with its subject
#   +  10   test_character_authoring_oracle: 5, plus the five named template properties that
#           came from the base's test_pipeline.py with their subject -- accessories, digits,
#           the parent chain and the palette. The byte comparison covers them all already,
#           but only as an opaque 282KB equality that says 'componentTree differs'
#   +  14   test_spec_augmentation_artifact
#   +   7   test_spec_search_profile
#   +  19   test_domain_declaration, which grew from 14: the harness's own doctor rules, run
#           before the commit rather than after the tag, plus the manifest agreements
#   = 331
COLLECTED_FLOOR = 331

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
