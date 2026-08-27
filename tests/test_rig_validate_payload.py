"""Tests for the rig payload validator.

Ported from the base skill's forge/tests/test_validate_rig_payload.py. Its subject moved to this plugin as
`tools/rig_validate_payload.py` (PLUGIN_CONTRACT.md §4, §8), so the assertions that pin that module's
behaviour belong here, next to the code they describe. Only the import bootstrap and the
module's new name changed; every test keeps its name and its assertions.
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from rig_validate_payload import validate  # noqa: E402


def payload():
    return {
        "schemaVersion": 1,
        "coordinateSystem": {"up": "Y", "handedness": "right", "unit": "normalized"},
        "joints": [[0, 0, 0], [0, 1, 0], [0.5, 1.5, 0]],
        "parents": [None, 0, 1],
        "names": ["root", "spine", "arm_L"],
        "matrix_local": [
            [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0.5, 0, 1, 0, 0.5, 0, 0, 1, 0, 0, 0, 0, 1],
        ],
        "skinIndex": [[0, 1, 2, 0], [1, 2, 0, 0]],
        "skinWeight": [[0.5, 0.3, 0.2, 0], [0.2, 0.8, 0, 0]],
    }


class ValidateRigPayloadTest(unittest.TestCase):
    def test_valid_payload_passes(self):
        result = validate(payload())
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["summary"]["maxInfluences"], 4)

    def test_parent_order_is_hard_gate(self):
        value = payload()
        value["parents"][2] = 2
        result = validate(value)
        self.assertFalse(result["passed"])
        self.assertTrue(any("parent < child" in error for error in result["errors"]))

    def test_weight_normalization_and_nan_are_hard_gates(self):
        value = payload()
        value["skinWeight"][0] = [0.5, 0.5, 0.5, 0]
        value["skinWeight"][1][0] = float("nan")
        result = validate(value)
        self.assertFalse(result["passed"])
        self.assertTrue(any("must sum to 1" in error for error in result["errors"]))
        self.assertTrue(any("finite non-negative" in error for error in result["errors"]))

    def test_duplicate_names_and_bad_matrix_are_hard_gates(self):
        value = copy.deepcopy(payload())
        value["names"][2] = "spine"
        value["matrix_local"][1][15] = 0
        result = validate(value)
        self.assertFalse(result["passed"])
        self.assertTrue(any("duplicate joint name" in error for error in result["errors"]))
        self.assertTrue(any("affine last row" in error for error in result["errors"]))

    def test_multiple_roots_require_explicit_admission(self):
        value = payload()
        value["parents"][2] = None
        result = validate(value)
        self.assertFalse(result["passed"])
        self.assertTrue(any("allowMultipleRoots=true" in error for error in result["errors"]))
        value["allowMultipleRoots"] = True
        result = validate(value)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["summary"]["rootJointCount"], 2)

    def test_zero_length_control_bone_requires_index_admission(self):
        value = payload()
        value["joints"][2] = value["joints"][1]
        result = validate(value)
        self.assertFalse(result["passed"])
        self.assertTrue(any("zero-length parent bone" in error for error in result["errors"]))
        value["allowZeroLengthBones"] = [2]
        result = validate(value)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["summary"]["admittedZeroLengthBoneCount"], 1)


if __name__ == "__main__":
    unittest.main()
