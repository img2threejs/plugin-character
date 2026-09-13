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

  slice 0   the base checkout, via IMG2THREEJS_BASE. The template still lived there.
  slice 1+  `tools/character_spec_template.py`, this plugin's own copy — and NO base checkout,
            because the base's contribution is frozen too.

`skeleton.json` is the output of the base's `make_spec()` before any template runs. Freezing it as
an INPUT is what makes this a plugin-side property rather than a two-repo integration test: the
oracle asserts that this plugin's template, applied to the base's own starting point, yields the
spec the base used to produce by itself. `make_spec` stays in the base and is not this plugin's to
test; what is this plugin's is everything that happens after it.

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
SKELETON_PATH = FIXTURES / "skeleton.json"
SPEC_PATH = FIXTURES / "spec.json"

DEFAULT_BASE = ROOT.parent / "img2threejs"
BASE_RELATIVE_TEMPLATE = Path("forge/stage2_spec/new_sculpt_spec.py")
PLUGIN_TEMPLATE = ROOT / "tools" / "character_spec_template.py"


def _load_template():
    """The module that applies the character template: this plugin's if it has one, else the base's.

    The fallback exists only for the window before slice 1 lands the module here. Once it has
    landed, this test needs no base checkout at all.
    """
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
        message + " Skipping: transitional only — once slice 1 moves the template here this test "
        "needs no base checkout. It did NOT verify the authoring on this run."
    )


class CharacterAuthoringOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template, cls.source = _load_template()
        cls.anatomy = json.loads(ANATOMY_PATH.read_text(encoding="utf-8"))
        cls.skeleton_text = SKELETON_PATH.read_text(encoding="utf-8")
        cls.frozen_text = SPEC_PATH.read_text(encoding="utf-8")
        cls.frozen = json.loads(cls.frozen_text)

    def _author(self, anatomy=None) -> dict:
        # The base's own starting point, frozen. json.loads gives a fresh object each call, so the
        # template never sees a spec a previous test already mutated.
        spec = json.loads(self.skeleton_text)
        self.template.apply_character_template(
            spec, self.anatomy if anatomy is None else anatomy, include_accessories=False)
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

    def test_the_skeleton_fixture_is_the_base_s_starting_point_not_the_answer(self) -> None:
        # If skeleton.json already carried the humanoid tree, every assertion here would pass
        # against an input that had done the work.
        skeleton = json.loads(self.skeleton_text)
        self.assertEqual([m["id"] for m in skeleton["materials"]], ["base"])
        self.assertNotIn("rig", skeleton)
        self.assertLess(len(skeleton.get("componentTree", [])), 5)

    def test_the_frozen_spec_still_carries_the_humanoid_track(self) -> None:
        # Without these the fixture could be satisfied by a spec that authored nothing, and the
        # byte comparison would pass against an equally empty expectation.
        self.assertEqual(len(self.frozen["componentTree"]), 61)
        self.assertEqual(len(self.frozen["rig"]["bones"]), 49)
        self.assertEqual(len(self.frozen["materials"]), 9)

    def test_the_default_figure_is_a_general_humanoid_not_one_person_s_bust(self) -> None:
        """Moved from the base's `test_pipeline.py` with its subject.

        The byte comparison above already covers this, but only as an opaque 282KB equality: when it
        fails it says "componentTree differs" and nothing about WHAT the template is for. These are
        the named properties the humanoid was designed around, and each one is a defect that shipped.
        """
        ids = {c["id"] for c in self._author()["componentTree"]}
        for part in ("root", "head", "abdomen", "chest", "neck", "hair",
                     "pelvis", "thigh-l", "shin-l", "foot-l",
                     "upper-arm-l", "forearm-l", "hand-l",
                     "eye-l", "eye-cavity-l"):
            self.assertIn(part, ids)
        # Accessories are one reference person's traits, opt-in since Plan 1.5.
        for accessory in ("glasses-frame-l", "hp-band", "shirt-decal"):
            self.assertNotIn(accessory, ids)

    def test_accessories_are_opt_in_and_actually_arrive(self) -> None:
        spec = json.loads(self.skeleton_text)
        self.template.apply_character_template(spec, self.anatomy, include_accessories=True)
        ids = {c["id"] for c in spec["componentTree"]}
        for accessory in ("glasses-frame-l", "hp-band", "shirt-decal"):
            self.assertIn(accessory, ids)

    def test_digits_are_baseline_rather_than_a_mitten(self) -> None:
        """US-003 replaced the `--fingers` flag with real digits in the default template.

        The flag added ONE box called `fingers-l` plus one called `thumb-l` — a mitten, opt-in. A
        humanoid that cannot curl a finger is not finished. Both halves are asserted: the digits
        exist with no flag, and the mitten ids do not come back.
        """
        tree = self._author()["componentTree"]
        ids = {c["id"] for c in tree}
        for side in ("l", "r"):
            for digit in ("thumb", "index", "middle", "ring", "little"):
                for phalanx in (1, 2, 3):
                    self.assertIn(f"{digit}-{side}-{phalanx}", ids)
        self.assertNotIn("fingers-l", ids)
        self.assertNotIn("thumb-l", ids)
        by_id = {c["id"]: c for c in tree}
        self.assertEqual(by_id["middle-l-1"]["parent"], "hand-l")
        self.assertEqual(by_id["middle-l-3"]["parent"], "middle-l-2")

    def test_the_tree_is_a_real_parent_chain_not_a_flat_list(self) -> None:
        """WS-E: a non-uniformly-scaled parent can no longer distort a nested child, so the
        template authors anatomically sensible parents instead of flattening onto `root`."""
        by_id = {c["id"]: c for c in self._author()["componentTree"]}
        for child, parent in {
            # US-001 split torso into abdomen + chest so the waist flexes, and parented the spine
            # to the pelvis — which is what made the rig derivation's hand-picked bone root and its
            # torso joint exception unnecessary.
            "pelvis": "root", "abdomen": "pelvis", "chest": "abdomen",
            "neck": "chest", "head": "neck",
            # US-002 inserted a clavicle so the shoulder can shrug and the arm's rotation origin
            # sits on the joint instead of inside the ribcage.
            "clavicle-l": "chest", "upper-arm-l": "clavicle-l",
            "forearm-l": "upper-arm-l", "hand-l": "forearm-l",
            "thigh-l": "pelvis", "shin-l": "thigh-l", "foot-l": "shin-l",
            "hair": "head", "eye-l": "head", "eye-cavity-l": "head",
        }.items():
            self.assertEqual(by_id[child]["parent"], parent, child)

    def test_the_palette_is_per_part_rather_than_one_beige_fallback(self) -> None:
        materials = {m["id"]: m for m in self._author()["materials"]}
        colors = {materials[k].get("color") for k in ("skin", "hair", "shirt")}
        self.assertEqual(len(colors), 3, "skin, hair and shirt must not share one colour")
        for key in ("skin", "hair", "shirt"):
            self.assertGreaterEqual(len(materials[key].get("colorVariation", {}).get("palette", [])), 2)

    def test_anatomy_actually_reaches_the_template(self) -> None:
        # If the template ignored its anatomy argument, every test above would still pass.
        taller = dict(self.anatomy, proportions=dict(self.anatomy["proportions"], torso=3.0))
        self.assertNotEqual(self._author(taller)["componentTree"], self.frozen["componentTree"])


if __name__ == "__main__":
    unittest.main()
