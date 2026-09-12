#!/usr/bin/env python3
"""The AUTHORING oracle: anatomy in, the same sculpt spec out, byte for byte.

This is the only test that can see the character extraction regress. The base's emission oracle
(`forge/tests/test_character_oracle_replay.py`) replays an ALREADY-AUTHORED spec through an emitter
that never leaves the base, so it stays green even if the humanoid template and the derived rig are
deleted outright. That is not hypothetical: a previous attempt deleted the authoring side, and every
oracle it had stayed green.

So this one starts where the authoring starts — `anatomy.json` — and asserts the spec that comes
out is the one frozen from `img2threejs` @ `6e60b5e` before anything moved.

WHERE IT READS THE TEMPLATE FROM, and why that changes:

  slice 0 (now)   the base checkout, via IMG2THREEJS_BASE. The template still lives there.
  slice 1 onward  `tools/character_spec_template.py`, this plugin's own copy.

It prefers the plugin's copy and falls back to the base, so the day the template arrives here the
oracle follows it with no edit. During the transition a missing base checkout is a skip WITH a
reason — the mirror of the base suite's own rule, and transitional by construction: once slice 1
lands, this test needs no base at all.

KEY ORDER IS PART OF THE COMPARISON. The base's emitter embeds a spec's dict key order in the
TypeScript it writes, so "same content, different order" is a real difference downstream. The frozen
fixture is serialised without `sort_keys` and this test compares the serialised forms, which is
what binds the plugin to author its sections in the order the base did.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "oracle-character"
ANATOMY_PATH = FIXTURES / "anatomy.json"
SPEC_PATH = FIXTURES / "spec.json"

DEFAULT_BASE = ROOT.parent / "img2threejs"
BASE_RELATIVE_TEMPLATE = Path("forge/stage2_spec/new_sculpt_spec.py")
PLUGIN_TEMPLATE = ROOT / "tools" / "character_spec_template.py"


def _load_template():
    """The module that authors a character spec: this plugin's if it has one, else the base's."""
    if PLUGIN_TEMPLATE.is_file():
        sys.path.insert(0, str(ROOT / "tools"))
        import character_spec_template  # noqa: PLC0415
        return character_spec_template, "plugin"

    configured = os.environ.get("IMG2THREEJS_BASE")
    root = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
    candidate = root / BASE_RELATIVE_TEMPLATE
    if candidate.is_file():
        sys.path[:0] = [str(root / "forge"), str(root / "forge" / "_shared"),
                        str(root / "forge" / "stage2_spec")]
        import new_sculpt_spec  # noqa: PLC0415
        return new_sculpt_spec, "base"

    where = "from IMG2THREEJS_BASE" if configured else "the default; IMG2THREEJS_BASE is unset"
    message = (
        "the character authoring oracle needs a template to run: this plugin has no "
        f"tools/character_spec_template.py yet, and the base checkout was not found. Looked in "
        f"{root} ({where}) for {BASE_RELATIVE_TEMPLATE}."
    )
    if os.environ.get("IMG2THREEJS_REQUIRE_BASE") == "1":
        raise RuntimeError(message + " IMG2THREEJS_REQUIRE_BASE=1 forbids skipping this check.")
    raise unittest.SkipTest(
        message + " Skipping: this is transitional — once slice 1 moves the template here, this "
        "test needs no base checkout. It did NOT verify the authoring on this run."
    )


class CharacterAuthoringOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template, cls.source = _load_template()
        cls.anatomy = json.loads(ANATOMY_PATH.read_text(encoding="utf-8"))
        cls.frozen_text = SPEC_PATH.read_text(encoding="utf-8")
        cls.frozen = json.loads(cls.frozen_text)

    def _author(self) -> dict:
        spec = self.template.make_spec("Oracle Figure", None, None)
        self.template.apply_character_template(spec, self.anatomy, include_accessories=False)
        return spec

    def test_the_authored_spec_is_byte_identical_to_the_frozen_one(self) -> None:
        produced = json.dumps(self._author(), indent=2) + "\n"
        if produced != self.frozen_text:
            # A 282KB diff helps nobody; name the sections that moved.
            a, b = json.loads(produced), self.frozen
            moved = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            self.fail(f"authored spec differs from the frozen oracle in: {moved} "
                      f"(template read from the {self.source})")

    def test_authoring_is_deterministic(self) -> None:
        self.assertEqual(json.dumps(self._author(), indent=2),
                         json.dumps(self._author(), indent=2))

    def test_the_frozen_spec_still_carries_the_humanoid_track(self) -> None:
        # Without these the fixture could be satisfied by a spec that authored nothing, and the
        # byte comparison would pass against an equally empty expectation.
        self.assertEqual(len(self.frozen["componentTree"]), 61)
        self.assertEqual(len(self.frozen["rig"]["bones"]), 49)
        self.assertEqual(len(self.frozen["materials"]), 9)

    def test_anatomy_actually_reaches_the_template(self) -> None:
        # If the template ignored its anatomy argument, every test above would still pass.
        taller = dict(self.anatomy, proportions=dict(self.anatomy["proportions"], torso=3.0))
        spec = self.template.make_spec("Oracle Figure", None, None)
        self.template.apply_character_template(spec, taller, include_accessories=False)
        self.assertNotEqual(spec["componentTree"], self.frozen["componentTree"])


if __name__ == "__main__":
    unittest.main()
