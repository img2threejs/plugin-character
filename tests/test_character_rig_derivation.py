"""The character rig is DERIVED from the component tree (PLAN_1.5 WS-A, spec half).

These tests pin the defects that were actually found while building it, not just the happy
path. The load-bearing one is `test_spine_bones_point_upward`: the first implementation read
each bone's segment from `attachment.localStart`/`localEnd`, which is correct for a limb --
whose component origin IS its proximal joint -- and wrong for the torso, whose origin is its
centre. That produced a spine bone running from the chest DOWN to the neck attach point: a
2 cm stub pointing the wrong way, which would have pulled leg vertices onto the torso's
weight during skinning. Nothing else in the suite would have noticed.

Pure Python 3.10+ stdlib. No pip installs.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from character_spec_template import (  # noqa: E402
    apply_character_pose,
    derive_character_rig,
    make_character_component_tree,
)

DEFAULT_BASE = ROOT.parent / "img2threejs"
BASE_RELATIVE_RIG_SPEC = Path("forge/stage5_rig/rig_spec.py")

SPINE = ("pelvis", "abdomen", "chest", "neck", "head")


def _length(bone: dict) -> float:
    return sum((bone["tipPos"][i] - bone["jointPos"][i]) ** 2 for i in range(3)) ** 0.5


class CharacterRigDerivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rig = derive_character_rig(make_character_component_tree())
        cls.by_id = {b["id"]: b for b in cls.rig["bones"]}

    def test_single_root_is_the_pelvis(self) -> None:
        """Hips-as-root, and since US-001 it needs no special case at all.

        The spine used to be a single `torso` parented to "root" alongside the pelvis, so the
        derivation had to pick one of two siblings as the bone root by hand. Now `abdomen` is
        parented to `pelvis`, so the pelvis is the only root-parented body part and falls out of
        the tree walk on its own.
        """
        roots = [b["id"] for b in self.rig["bones"] if b["parent"] in (None, "", "root")]
        self.assertEqual(roots, ["pelvis"])

    def test_spine_bones_point_upward(self) -> None:
        """The defect this whole module exists for. A spine bone whose tip sits BELOW its
        joint is pointing at the floor."""
        for bone_id in SPINE:
            bone = self.by_id[bone_id]
            self.assertGreater(
                bone["tipPos"][1],
                bone["jointPos"][1],
                f"spine bone {bone_id!r} points DOWN: joint.y={bone['jointPos'][1]} "
                f"tip.y={bone['tipPos'][1]} -- its joint must be its PROXIMAL end",
            )

    def test_spine_chain_is_contiguous(self) -> None:
        """Each spine bone starts where its parent ended. Limb branch points legitimately do
        NOT (a thigh leaves the pelvis at the hip socket, not at the spine's tip), so this is
        asserted for the spine only rather than for every bone."""
        for child, parent in zip(SPINE[1:], SPINE[:-1]):
            gap = sum(
                (self.by_id[child]["jointPos"][i] - self.by_id[parent]["tipPos"][i]) ** 2
                for i in range(3)
            ) ** 0.5
            self.assertLess(gap, 1e-6, f"{parent} -> {child} leaves a {gap:.5f} gap")

    def test_no_bone_is_degenerate(self) -> None:
        degenerate = [b["id"] for b in self.rig["bones"] if _length(b) < 1e-6]
        self.assertEqual(degenerate, [], f"zero-length bones cannot be posed: {degenerate}")

    def test_limb_chains_are_fully_linked_per_side(self) -> None:
        """Arms are four deep since US-002 added a clavicle; legs remain three."""
        for chain in (
            ("clavicle-l", "upper-arm-l", "forearm-l", "hand-l"),
            ("clavicle-r", "upper-arm-r", "forearm-r", "hand-r"),
            ("thigh-l", "shin-l", "foot-l"),
            ("thigh-r", "shin-r", "foot-r"),
        ):
            for parent, child in zip(chain, chain[1:]):
                self.assertEqual(self.by_id[child]["parent"], parent,
                                 f"{child} should hang off {parent}")

    def test_clavicles_are_arm_chain_bones_rooted_on_the_chest(self) -> None:
        for side in ("l", "r"):
            bone = self.by_id[f"clavicle-{side}"]
            self.assertEqual(bone["parent"], "chest")
            self.assertEqual(bone["chain"], "arm")
            self.assertGreater(_length(bone), 1e-6)

    def test_details_are_not_bones(self) -> None:
        """A brow does not articulate. Only body segments become bones, so a detail riding
        its parent must never acquire one."""
        for detail in ("brow-l", "nose", "mouth", "hair", "eye-l", "eye-cavity-l",
                       "ear-l", "ear-r"):
            self.assertNotIn(detail, self.by_id)

    def test_left_and_right_limbs_are_mirrored_in_x(self) -> None:
        for left, right in (("upper-arm-l", "upper-arm-r"), ("thigh-l", "thigh-r")):
            self.assertAlmostEqual(
                self.by_id[left]["jointPos"][0], -self.by_id[right]["jointPos"][0], places=5
            )


class CharacterPoseApplication(unittest.TestCase):
    """`anatomy.pose.jointAngles` was declared in two places and consumed in none until now.

    Posing a hierarchy of RIGID segments needs no skeleton — only a parent chain that
    propagates rotation, which the template has. So these tests also pin the claim that a
    reference pose is reachable without skinning.
    """

    POSE = {
        "pose": {
            "type": "contrapposto",
            "jointAngles": {
                "neck": [0.0, 0.22, 0.05],
                "rightShoulder": [-0.35, 0.0, 0.30],
                "leftElbow": [-0.30, 0.0, -0.55],
                "leftHip": [0.0, 0.0, -0.08],
            },
        }
    }

    def test_no_anatomy_applies_no_pose(self) -> None:
        tree = make_character_component_tree()
        self.assertEqual(apply_character_pose(tree, None), [])
        for component in tree:
            rotation = (component.get("transform") or {}).get("rotation") or [0, 0, 0]
            if component["id"] != "nose":  # the one authored rotation in the template
                self.assertTrue(all(abs(float(v)) < 1e-9 for v in rotation), component["id"])

    def test_joint_angles_land_on_the_anatomically_correct_components(self) -> None:
        """"left" is the CHARACTER's left, which the tree spells `-l` — on a front-facing
        reference that is the viewer's right. Getting this backwards mirrors the pose."""
        tree = make_character_component_tree()
        applied = apply_character_pose(tree, self.POSE)
        self.assertEqual(len(applied), 4)
        by_id = {c["id"]: c for c in tree}
        self.assertEqual(by_id["neck"]["transform"]["rotation"], [0.0, 0.22, 0.05])
        self.assertEqual(by_id["upper-arm-r"]["transform"]["rotation"], [-0.35, 0.0, 0.30])
        self.assertEqual(by_id["forearm-l"]["transform"]["rotation"], [-0.30, 0.0, -0.55])
        self.assertEqual(by_id["thigh-l"]["transform"]["rotation"], [0.0, 0.0, -0.08])

    def test_rig_is_derived_at_bind_pose_not_posed(self) -> None:
        """A skeleton is bind-pose data. Derive first, pose second."""
        tree = make_character_component_tree()
        rig = derive_character_rig(tree)
        chest_before = [b for b in rig["bones"] if b["id"] == "chest"][0]["jointPos"]
        apply_character_pose(tree, self.POSE)
        rig_again = derive_character_rig(make_character_component_tree())
        chest_after = [b for b in rig_again["bones"] if b["id"] == "chest"][0]["jointPos"]
        self.assertEqual(chest_before, chest_after)

    def test_deriving_a_rig_from_a_posed_tree_fails_closed(self) -> None:
        """The precondition behind `model_pos` — summing parent-local offsets is only valid
        while every ancestor rotation is identity. Violating it silently would move every
        descendant joint with nothing failing, so it raises instead."""
        tree = make_character_component_tree()
        apply_character_pose(tree, self.POSE)
        with self.assertRaises(ValueError) as caught:
            derive_character_rig(tree)
        self.assertIn("bind pose", str(caught.exception))


class AdmittedByTheBase(unittest.TestCase):
    """The derived rig still passes the base's gates — the half of this file that spans both repos.

    Before the extraction this was one assertion in the class above, because the derivation and
    the gate lived in the same checkout. They no longer do, so it is separated: everything above
    is this plugin's own property and runs from a bare clone, and only these two need the base.

    `validate_rig_spec` is the stage5 gate the rig has always had to satisfy. `validate_rig_admission`
    is the one the extraction NEWLY routes it through: `rig` is not in `BASE_OWNED`, so a plugin now
    writes it wholesale and the merge admits it opaquely — those five checks are the base's only
    look at rig content arriving that way, and nothing asserted they pass on a plugin's submission.
    """

    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("IMG2THREEJS_BASE")
        root = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
        if not (root / BASE_RELATIVE_RIG_SPEC).is_file():
            where = "from IMG2THREEJS_BASE" if configured else "the default; IMG2THREEJS_BASE is unset"
            message = ("the rig admission pin needs the base checkout: set IMG2THREEJS_BASE to an "
                       f"img2threejs checkout containing {BASE_RELATIVE_RIG_SPEC}. Looked in {root} "
                       f"({where}).")
            if os.environ.get("IMG2THREEJS_REQUIRE_BASE") == "1":
                raise RuntimeError(message + " IMG2THREEJS_REQUIRE_BASE=1 forbids skipping this.")
            raise unittest.SkipTest(message + " Skipping: the derivation's own properties are still "
                                              "pinned above, but this run did NOT gate the rig.")
        sys.path[:0] = [str(root / "forge"), str(root / "forge" / "_shared"),
                        str(root / "forge" / "stage2_spec")]
        from stage5_rig.rig_spec import BoneSpec, RigSpec, validate_rig_spec  # noqa: PLC0415
        from validate_sculpt_spec import validate_rig_admission  # noqa: PLC0415
        cls.validate_rig_spec = staticmethod(validate_rig_spec)
        cls.validate_rig_admission = staticmethod(validate_rig_admission)
        cls.BoneSpec, cls.RigSpec = BoneSpec, RigSpec
        cls.rig = derive_character_rig(make_character_component_tree())

    def test_the_derived_rig_satisfies_the_stage5_rig_spec_gate(self) -> None:
        spec = self.RigSpec(
            version=self.rig["version"],
            bind_pose=self.rig["bindPose"],
            forward=self.rig["forward"],
            bones=[self.BoneSpec(id=b["id"], parent=b["parent"], joint_pos=tuple(b["jointPos"]),
                                 component=b["component"], role=b["role"], chain=b["chain"],
                                 tip_pos=tuple(b["tipPos"])) for b in self.rig["bones"]],
        )
        self.assertEqual(self.validate_rig_spec(spec), [])

    def test_the_derived_rig_is_admitted_without_error_or_snap(self) -> None:
        # A snap would mean the shipped spec differs from what this plugin emitted, so the
        # authoring oracle would agree with itself while disagreeing with what the base wrote.
        import copy  # noqa: PLC0415
        spec = {"rig": copy.deepcopy(self.rig)}
        errors: list[str] = []
        warnings: list[str] = []
        self.validate_rig_admission(spec, errors, warnings)
        self.assertEqual(errors, [])
        self.assertEqual(spec["rig"], self.rig, "SYMMETRY_PARITY snapped a bone this plugin authored")


if __name__ == "__main__":
    unittest.main()
