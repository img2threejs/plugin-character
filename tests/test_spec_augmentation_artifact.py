#!/usr/bin/env python3
"""The artifact this plugin publishes, checked against the base's REAL merge.

`tests/test_character_authoring_oracle.py` pins what the template produces. This pins what happens
when the base merges it — a different thing, and the one that actually ships. It is the only test
here that legitimately needs the base checkout, because the property it asserts spans both sides;
it skips with a reason when `IMG2THREEJS_BASE` is unset, and `IMG2THREEJS_REQUIRE_BASE=1` turns that
skip into a failure.

THE ONE INTENDED DIFFERENCE. Merging the artifact produces the frozen spec plus
`preSpecAssessment.objectClass.domain = "character"`. That field did not exist before the
extraction: the base sets it from domain resolution and only ever reaches that code path when an
augmentation artifact is pulled, which never happened while the template lived in the base. It is a
behaviour change, it is the one `domain-recognition` requires ("the resolution record SHALL name the
provider"), and it is asserted here by name so that it stays the *only* one.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "oracle-character"
DEFAULT_BASE = ROOT.parent / "img2threejs"
BASE_RELATIVE_MERGE = Path("forge/_shared/spec_augmentation.py")

sys.path.insert(0, str(ROOT / "tools"))

import emit_spec_augmentation as E  # noqa: E402


def _base_spec_augmentation():
    """The base's real merge module, or a skip naming the checkout it needs."""
    configured = os.environ.get("IMG2THREEJS_BASE")
    root = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
    if (root / BASE_RELATIVE_MERGE).is_file():
        sys.path[:0] = [str(root / "forge"), str(root / "forge" / "_shared")]
        import spec_augmentation  # noqa: PLC0415
        return spec_augmentation
    where = "from IMG2THREEJS_BASE" if configured else "the default; IMG2THREEJS_BASE is unset"
    message = ("the artifact/merge integration pin needs the base checkout: set IMG2THREEJS_BASE to "
               f"an img2threejs checkout containing {BASE_RELATIVE_MERGE}. Looked in {root} ({where}).")
    if os.environ.get("IMG2THREEJS_REQUIRE_BASE") == "1":
        raise RuntimeError(message + " IMG2THREEJS_REQUIRE_BASE=1 forbids skipping this check.")
    raise unittest.SkipTest(message + " Skipping: the artifact's own shape is still pinned by the "
                                      "rest of this suite, but this run did NOT merge it.")


def _base_merge():
    return _base_spec_augmentation().merge_spec_augmentation


class ArtifactShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.anatomy = json.loads((FIXTURES / "anatomy.json").read_text(encoding="utf-8"))
        cls.artifact = E.build(cls.anatomy)

    def test_the_kind_and_provenance_are_what_the_base_reads(self) -> None:
        self.assertEqual(self.artifact["kind"], "spec-augmentation-v1")
        self.assertEqual(self.artifact["provenance"]["provider"], "character")
        self.assertEqual(self.artifact["provenance"]["version"],
                         json.loads((ROOT / "plugin.json").read_text())["version"])

    def test_no_section_claims_a_base_owned_key(self) -> None:
        self.assertEqual(set(self.artifact["specSections"]) & set(E.BASE_OWNED), set())

    def test_the_artifact_carries_no_key_outside_the_schema(self) -> None:
        # The merge refuses an unknown key rather than ignoring it, so a typo here is a hard fail at
        # spec-authoring time, not a section that silently contributes nothing.
        self.assertTrue(set(self.artifact)
                        <= {"kind", "provenance", "specSections", "assessmentPatch", "qualityFloors"})

    def test_it_does_not_propose_the_resolved_domain_marker(self) -> None:
        # Set by domain resolution, never by the artifact resolution selected. The merge refuses it.
        self.assertNotIn("domain", self.artifact["assessmentPatch"]["objectClass"])

    def test_the_sections_are_the_six_the_domain_authors(self) -> None:
        self.assertEqual(sorted(self.artifact["specSections"]),
                         ["buildPasses", "componentTree", "featureReviewTargets", "materials",
                          "rig", "sculptPipeline"])


class MergedAgainstTheFrozenSpec(unittest.TestCase):
    """The end-to-end property: base skeleton + this artifact == what the base used to produce."""

    @classmethod
    def setUpClass(cls) -> None:
        # staticmethod, or Python binds it as a method and passes `self` as the spec.
        cls.merge = staticmethod(_base_merge())
        cls.anatomy = json.loads((FIXTURES / "anatomy.json").read_text(encoding="utf-8"))
        cls.skeleton_text = (FIXTURES / "skeleton.json").read_text(encoding="utf-8")
        cls.frozen = json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8"))

    def _merged(self) -> dict:
        spec = json.loads(self.skeleton_text)
        self.merge(spec, E.build(self.anatomy), domain_id="character")
        spec.pop("specAugmentation", None)   # the base's own provenance record, not a spec section
        return spec

    def test_every_section_but_the_domain_marker_is_identical(self) -> None:
        merged = self._merged()
        differing = sorted(k for k in set(merged) | set(self.frozen)
                           if merged.get(k) != self.frozen.get(k))
        self.assertEqual(differing, ["preSpecAssessment"],
                         "only preSpecAssessment may differ, and only by the resolved-domain marker")

    def test_the_only_difference_is_the_resolved_domain_marker(self) -> None:
        merged = self._merged()["preSpecAssessment"]
        frozen = self.frozen["preSpecAssessment"]
        differing = {k for k in set(merged) | set(frozen) if merged.get(k) != frozen.get(k)}
        self.assertEqual(differing, {"objectClass"})
        a, b = merged["objectClass"], frozen["objectClass"]
        self.assertEqual({k for k in set(a) | set(b) if a.get(k) != b.get(k)}, {"domain"})
        self.assertEqual(a["domain"], "character")
        self.assertIsNone(b.get("domain"))

    def test_the_merge_clamps_nothing(self) -> None:
        # This domain proposes no quality floors, so nothing should be refused or lowered.
        spec = json.loads(self.skeleton_text)
        record = self.merge(spec, E.build(self.anatomy), domain_id="character")
        self.assertEqual(record.get("clamped") or [], [])

    def test_sculptPipeline_keeps_the_base_keys_the_template_does_not_set(self) -> None:
        # The section is replaced wholesale, so the five base defaults must be carried by the
        # artifact or they vanish. This is the assertion that catches that class of loss.
        pipeline = self._merged()["sculptPipeline"]
        for key in ("passGateMode", "completedPasses", "lastCompletedPass", "blockedReason",
                    "nextRequiredEvidence"):
            self.assertIn(key, pipeline)
        self.assertEqual(pipeline["passOrder"], self.frozen["sculptPipeline"]["passOrder"])


if __name__ == "__main__":
    unittest.main()


class RuledOnByTheBase(unittest.TestCase):
    """Every section this plugin contributes is one the base has written a ruling for.

    `spec-augmentation`'s "authority is stated" scenarios describe a document, and a document no
    test reads is a document that drifts. Without this, a section added here ships with the base
    having never decided whether a plugin may author it — the merge would admit it opaquely and
    nothing would ask the question.

    This is a check on the BASE having ruled, not a gate on this plugin: `SECTION_AUTHORITY` is
    explicitly not an allow-list, and the merge still admits sections named nowhere in it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.authority = _base_spec_augmentation().SECTION_AUTHORITY
        cls.artifact = E.build(json.loads((FIXTURES / "anatomy.json").read_text(encoding="utf-8")))

    def test_every_contributed_section_is_named_in_the_ruling(self) -> None:
        unruled = sorted(set(self.artifact["specSections"]) - set(self.authority))
        self.assertEqual(unruled, [], "the base has no authority ruling for these sections")

    def test_every_contributed_section_is_ruled_writable_by_a_plugin(self) -> None:
        for section in sorted(self.artifact["specSections"]):
            self.assertTrue(self.authority[section].startswith("PLUGIN"),
                            f"{section} is ruled {self.authority[section].split('.')[0]!r}")

    def test_the_deny_list_this_plugin_pins_matches_the_base_s(self) -> None:
        # E.BASE_OWNED is a deliberate duplicate — a plugin may not import base code — so the
        # agreement has to be asserted rather than assumed.
        self.assertEqual(set(E.BASE_OWNED), set(_base_spec_augmentation().BASE_OWNED))


class TheToolWritesOnlyItsArtifact(unittest.TestCase):
    """It takes no `--spec`, so it cannot write the base's spec even by accident.

    A tool that read the base's output and handed it back would make the base's spec an input to
    the artifact the base then merges: the push relationship inverted rather than avoided. The
    argument's absence is the design; this asserts the design rather than the docstring.
    """

    def test_there_is_no_spec_argument_to_point_at_the_base_s_output(self) -> None:
        options = {s for action in E.build_parser()._actions for s in action.option_strings}
        self.assertNotIn("--spec", options)
        self.assertEqual(options & {"--out", "--anatomy"}, {"--out", "--anatomy"})

    def test_a_run_creates_exactly_one_file(self) -> None:
        import tempfile  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "spec-augmentation.json"
            import contextlib, io  # noqa: PLC0415
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(E.main(["--out", str(out),
                                         "--anatomy", str(FIXTURES / "anatomy.json")]), 0)
            written = sorted(p.relative_to(tmp).as_posix() for p in Path(tmp).rglob("*") if p.is_file())
            self.assertEqual(written, ["nested/spec-augmentation.json"])
            self.assertEqual(json.loads(out.read_text())["kind"], "spec-augmentation-v1")

