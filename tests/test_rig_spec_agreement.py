"""The drift pin for the one function this plugin duplicates from the base skill.

`derive_envelope_radius` (PLAN_1.5 §4.3) exists twice on purpose: once in the base skill's
forge/stage5_rig/rig_spec.py, where forge/stage3_build/generate_threejs_factory.py:2106 imports it,
and once in this plugin's tools/rig_spec.py, where tools/rig_emit_rig.py imports it. The duplication
is forced -- a plugin may not import forge.* (PLUGIN_CONTRACT.md section 8) -- so the only thing
standing between "two copies" and "two behaviours" is this file.

Loading the base copy does NOT import forge. The base file is read off disk and executed by absolute
path through importlib, in a module namespace of its own; nothing named `forge` or `stage5_rig` is
put on sys.path or in sys.modules. That distinction is the whole point of this test: the contract
bans the import, not the comparison.

The base checkout is optional. IMG2THREEJS_BASE points at it (default: the sibling ~/Documents/
personal/img2threejs); when it is absent the tests skip with a message naming the variable, so the
plugin's suite still passes on a machine that has only the plugin. Modelled on the base's own
forge/tests/showcase_test_support.py, which handles IMG2THREEJS_SHOWCASE_ROOT the same way and
escalates the skip to a hard error under IMG2THREEJS_REQUIRE_BASE=1 for CI that must not skip.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from rig_spec import derive_envelope_radius as plugin_derive  # noqa: E402

DEFAULT_BASE = Path.home() / "Documents" / "personal" / "img2threejs"
BASE_RELATIVE_RIG_SPEC = Path("forge") / "stage5_rig" / "rig_spec.py"


def _base_rig_spec_path() -> Path:
    configured = os.environ.get("IMG2THREEJS_BASE")
    root = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
    candidate = root / BASE_RELATIVE_RIG_SPEC
    if candidate.is_file():
        return candidate
    where = "from IMG2THREEJS_BASE" if configured else "the default; IMG2THREEJS_BASE is unset"
    message = (
        "the rig_spec drift pin needs the base skill checkout: set IMG2THREEJS_BASE to an "
        f"img2threejs checkout containing {BASE_RELATIVE_RIG_SPEC}. Looked in {root} ({where}) "
        "and found no such file."
    )
    if os.environ.get("IMG2THREEJS_REQUIRE_BASE") == "1":
        raise RuntimeError(message + " IMG2THREEJS_REQUIRE_BASE=1 forbids skipping this check.")
    raise unittest.SkipTest(
        message + " Skipping: the plugin's own copy is still exercised by the rest of the suite, "
        "but this run did NOT check it against the base."
    )


def _load_base_derive():
    """Execute the base rig_spec.py by path and hand back its derive_envelope_radius.

    Deliberately NOT `from stage5_rig.rig_spec import ...` -- see the module docstring. Nothing is
    added to sys.path; the module is given a private name that cannot collide with the plugin's own
    `rig_spec`, and that name is removed from sys.modules once execution finishes. It has to be
    present *during* exec: @dataclass looks its own module up in sys.modules while processing the
    class, and fails with an opaque AttributeError when it is missing.
    """
    path = _base_rig_spec_path()
    name = "_base_rig_spec_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not build an import spec for the base rig_spec at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    try:
        return module.derive_envelope_radius
    except AttributeError as exc:  # the base renamed or removed it -- that is drift too
        raise AssertionError(
            f"the base rig_spec at {path} has no derive_envelope_radius; the plugin's copy in "
            "tools/rig_spec.py is now orphaned"
        ) from exc


# Signature swept: derive_envelope_radius(width, depth, overlap_factor=1.2) -> float.
#
# width/depth are bounding-box extents and must be > 0 (the function rejects <= 0), so the degenerate
# end of their range is "as close to zero as a float gets", not zero itself: sys.float_info.min and a
# subnormal below it. The other ends are the huge values where 0.5 * x * F can still round, and the
# max(width, depth) tie where the branch could be taken either way.
_POSITIVE_EXTENTS = (
    5e-324,  # smallest positive subnormal
    sys.float_info.min,  # smallest positive normal
    1e-9,
    0.001,
    0.1,
    0.5,
    1.0,
    1.0000000000000002,  # 1.0 + 1 ulp, to catch a rewritten formula that rounds differently
    2.0,
    3.7,
    100.0,
    1e9,
    sys.float_info.max / 4,  # 0.5 * x * 1.2 still finite
)
_OVERLAP_FACTORS = (
    5e-324,
    sys.float_info.min,
    1e-6,
    0.5,
    1.0,
    1.2,  # the plan default
    1.9999999999999998,
    2.0,
    7.5,
    1e6,
)
# Values the function must reject, on every parameter.
_NON_POSITIVE = (0.0, -0.0, -5e-324, -1e-9, -1.0, -1e9, float("-inf"))


def _outcome(fn, args) -> str:
    """What `fn(*args)` did, as a comparable string: the exception type, or the exact result.

    repr() of a float is round-trip exact and distinguishes nan from 0.6 from inf, so comparing
    outcome strings is as strict as comparing the values -- and it also compares the raise/return
    decision, which a bare value comparison cannot.
    """
    try:
        return f"returned {float(fn(*args))!r}"
    except Exception as exc:  # noqa: BLE001 -- the exception type IS the observation
        return f"raised {type(exc).__name__}"


class RigSpecFormulaAgreement(unittest.TestCase):
    """Both copies of §4.3 must compute the same number for the same inputs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.base_derive = staticmethod(_load_base_derive())

    # Exact equality, not an epsilon. Both copies evaluate the identical expression
    # `0.5 * max(width, depth) * overlap_factor` -- same operations, same order, same IEEE-754
    # doubles, same interpreter -- so agreement is bit-for-bit or it is drift. An epsilon here would
    # be strictly worse: it would wave through a rewrite to, say, `max(w, d) * f / 2` or
    # `max(w, d) * (0.5 * f)`, which is a different rounding and therefore exactly the kind of
    # silent divergence this pin exists to catch. assertEqual on floats is the strict comparison.
    def test_agrees_across_the_default_factor_sweep(self) -> None:
        for width in _POSITIVE_EXTENTS:
            for depth in _POSITIVE_EXTENTS:
                with self.subTest(width=width, depth=depth):
                    self.assertEqual(
                        plugin_derive(width, depth),
                        self.base_derive(width, depth),
                        "plugin tools/rig_spec.py and the base forge/stage5_rig/rig_spec.py "
                        "disagree on derive_envelope_radius; the deliberate duplicate has drifted",
                    )

    def test_agrees_across_the_overlap_factor_sweep(self) -> None:
        for width in _POSITIVE_EXTENTS:
            for depth in (width, width * 2.0, width / 2.0):
                if depth <= 0:  # width/2 can underflow to 0 at the subnormal end
                    continue
                for factor in _OVERLAP_FACTORS:
                    with self.subTest(width=width, depth=depth, overlap_factor=factor):
                        self.assertEqual(
                            plugin_derive(width, depth, factor),
                            self.base_derive(width, depth, factor),
                            "plugin and base derive_envelope_radius disagree once overlap_factor "
                            "is varied; the deliberate duplicate has drifted",
                        )

    def test_default_overlap_factor_matches(self) -> None:
        # A changed default is drift the value sweep above cannot see, because it passes the factor
        # explicitly on every call that varies it.
        for width, depth in ((1.0, 1.0), (3.0, 7.0), (7.0, 3.0)):
            with self.subTest(width=width, depth=depth):
                self.assertEqual(
                    plugin_derive(width, depth),
                    self.base_derive(width, depth, 1.2),
                    "the plugin's default overlap_factor is no longer the base's 1.2",
                )
                self.assertEqual(
                    self.base_derive(width, depth),
                    plugin_derive(width, depth, 1.2),
                    "the base's default overlap_factor is no longer 1.2",
                )

    def test_both_reject_the_same_non_positive_inputs(self) -> None:
        # Agreement is not only about returned numbers: a copy that stopped fail-closed on a
        # degenerate extent has drifted just as badly as one that changed the arithmetic.
        for bad in _NON_POSITIVE:
            for args in ((bad, 1.0), (1.0, bad)):
                with self.subTest(args=args):
                    with self.assertRaises(ValueError):
                        plugin_derive(*args)
                    with self.assertRaises(ValueError):
                        self.base_derive(*args)
            with self.subTest(overlap_factor=bad):
                with self.assertRaises(ValueError):
                    plugin_derive(1.0, 1.0, bad)
                with self.assertRaises(ValueError):
                    self.base_derive(1.0, 1.0, bad)

    def test_both_handle_nan_and_infinity_identically(self) -> None:
        # NaN fails every `<= 0` comparison, so neither copy fail-closes on it; and `max()` is not
        # NaN-symmetric (max(1.0, nan) is 1.0, max(nan, 1.0) is nan), so what comes back depends on
        # argument order. This test deliberately does not pin WHICH answer is right -- it pins that
        # both copies give the same one, which is the only claim this file is making.
        nan = float("nan")
        inf = float("inf")
        for args in ((nan, 1.0), (1.0, nan), (nan, nan), (1.0, 1.0, nan), (inf, 1.0), (1.0, 1.0, inf)):
            with self.subTest(args=args):
                self.assertEqual(_outcome(plugin_derive, args), _outcome(self.base_derive, args))


class DriftPinActuallyFails(unittest.TestCase):
    """A pin that cannot fail is not a pin.

    These do not test the product; they test the comparison above. Each stands in a perturbed
    implementation for one copy and asserts the sweep rejects it. If any of these ever passes
    silently, the sweeps in RigSpecFormulaAgreement have stopped being able to catch drift.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.base_derive = staticmethod(_load_base_derive())

    def _sweep_disagreement(self, perturbed) -> list[tuple[float, float, float]]:
        """Run the same sweep the real test runs, collecting inputs where the two disagree."""
        found: list[tuple[float, float, float]] = []
        for width in _POSITIVE_EXTENTS:
            for depth in _POSITIVE_EXTENTS:
                for factor in _OVERLAP_FACTORS:
                    if perturbed(width, depth, factor) != self.base_derive(width, depth, factor):
                        found.append((width, depth, factor))
        return found

    def test_sweep_catches_a_one_ulp_perturbation(self) -> None:
        # The smallest change a float can carry: nudge the result by a single ulp. Exact equality
        # sees it; an epsilon comparison would not, which is why this test is the argument for
        # assertEqual over assertAlmostEqual.
        def one_ulp_off(width: float, depth: float, factor: float) -> float:
            return math.nextafter(plugin_derive(width, depth, factor), math.inf)

        disagreements = self._sweep_disagreement(one_ulp_off)
        self.assertTrue(
            disagreements,
            "the sweep did not notice a one-ulp perturbation: it can no longer catch drift",
        )

    def test_sweep_catches_a_changed_default_factor(self) -> None:
        def wrong_default(width: float, depth: float, factor: float = 1.25) -> float:
            return 0.5 * max(width, depth) * factor

        for width, depth in ((1.0, 1.0), (3.0, 7.0)):
            self.assertNotEqual(wrong_default(width, depth), self.base_derive(width, depth))

    def test_sweep_catches_a_reassociated_formula(self) -> None:
        # `max(w, d) * (0.5 * f)` is algebraically the plan's formula and numerically is not, on
        # some inputs. This is the realistic drift: someone "tidies" one copy.
        def reassociated(width: float, depth: float, factor: float) -> float:
            return max(width, depth) * (0.5 * factor)

        disagreements = self._sweep_disagreement(reassociated)
        self.assertTrue(
            disagreements,
            "the sweep did not notice a reassociated formula: the input range is too narrow to "
            "expose rounding differences and can no longer catch this class of drift",
        )

    def test_sweep_catches_min_instead_of_max(self) -> None:
        def uses_min(width: float, depth: float, factor: float) -> float:
            return 0.5 * min(width, depth) * factor

        disagreements = self._sweep_disagreement(uses_min)
        self.assertTrue(
            disagreements,
            "the sweep did not notice max() becoming min(): it can no longer catch drift",
        )


if __name__ == "__main__":
    unittest.main()
