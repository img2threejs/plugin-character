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
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "oracle-character"
BASE_RELATIVE_MERGE = Path("forge/_shared/spec_augmentation.py")

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import emit_spec_augmentation as E  # noqa: E402
from _base_checkout import on_base_path, require_base  # noqa: E402


def _base_spec_augmentation():
    """The base's real merge module, or a skip naming the checkout it needs."""
    root = require_base(BASE_RELATIVE_MERGE, "the artifact/merge integration pin",
                        "the artifact's own shape is still pinned by the rest of this suite, but "
                        "this run did NOT merge it.")
    on_base_path(root, "forge", "forge/_shared")
    import spec_augmentation  # noqa: PLC0415
    return spec_augmentation


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


class ThePipelineDefaultsMatchTheFrozenSpec(unittest.TestCase):
    """The FIVE VALUES this plugin carries for the base, pinned against the frozen spec.

    `MergedAgainstTheFrozenSpec` needs the base checkout and therefore SKIPS by default, and
    `test_sculptPipeline_keeps_the_base_keys_the_template_does_not_set` only asserts key PRESENCE.
    Between them, a stale `blockedReason` string -- copied by hand from the base at `6e60b5e`,
    including its user-facing wording -- could ship on every character run with nothing red. A
    review called that a silent-drift liability dressed as a documented follow-up, correctly.

    This closes it with no base checkout: `fixtures/oracle-character/spec.json` is the base's own
    output, frozen, and it travels with this plugin. So the check is NOT SKIPPABLE, and it compares
    values rather than names.

    It does not make the follow-up unnecessary. The clean end state is the base preserving its own
    gate state instead of trusting a provider to carry it; this makes the interim shim falsifiable
    rather than merely documented.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8"))["sculptPipeline"]

    def test_every_carried_default_equals_the_value_the_base_produced(self) -> None:
        for key, carried in E.BASE_PIPELINE_DEFAULTS.items():
            self.assertEqual(carried, self.frozen[key],
                             f"BASE_PIPELINE_DEFAULTS[{key!r}] has drifted from the base's value")

    def test_the_carried_set_is_exactly_what_the_template_does_not_set(self) -> None:
        # Too few and the merge drops a key; too many and this plugin is asserting authority over
        # something the template already decides. Derived from the template, not transcribed.
        authored = set(E.build(json.loads((FIXTURES / "anatomy.json").read_text(encoding="utf-8")))
                       ["specSections"]["sculptPipeline"])
        self.assertEqual(set(E.BASE_PIPELINE_DEFAULTS) | {"passOrder", "currentPass"}, authored)
        self.assertEqual(set(E.BASE_PIPELINE_DEFAULTS) & {"passOrder", "currentPass"}, set())

    def test_the_section_carries_every_key_the_base_had(self) -> None:
        authored = E.build(json.loads((FIXTURES / "anatomy.json").read_text(encoding="utf-8")))
        self.assertEqual(list(authored["specSections"]["sculptPipeline"]), list(self.frozen),
                         "key order is part of the comparison: the emitter embeds it")


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

class TheAnatomyGate(unittest.TestCase):
    """The check the base deleted with `validate_character_track`, now made at the producer.

    It fired under `--strict-quality`, which promotes warnings to errors, and `strict-validation`
    is a mandatory base step -- so a character run that never filled `anatomy.json` used to be
    BLOCKED. The base cannot keep the check (it has no view on anatomy any more), so if the
    producer does not make it, it exists in NEITHER repo.

    That is what a code review measured, against a docstring of mine in the base's `test_pipeline.py`
    asserting the producer already refused. It did not: `build(None)` authored a full default
    humanoid and exited 0. These tests are that claim made true, and the reason the base test's
    docstring is allowed to keep pointing here.
    """

    ANATOMY = {"applies": True, "styleHeads": 8,
               "proportions": {"torso": 2.2, "legs": 3.6},
               "faceLandmarks": {"eyeLine": 0.45}}

    def _emit(self, *argv) -> int:
        import contextlib, io, tempfile  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                return E.main([*argv, "--out", str(Path(tmp) / "a.json")])

    def _emit_with(self, payload) -> int:
        import tempfile  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "anatomy.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            return self._emit("--anatomy", str(source))

    def test_no_anatomy_and_no_style_heads_is_refused(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            self._emit()
        self.assertEqual(caught.exception.code, 2)

    def test_an_anatomy_file_that_measured_nothing_is_refused(self) -> None:
        for payload in ({}, {"preSpecAssessment": {}}, {"applies": False, "styleHeads": 8}):
            with self.subTest(payload=payload), self.assertRaises(SystemExit):
                self._emit_with(payload)

    def test_each_missing_field_is_named_rather_than_lumped_together(self) -> None:
        # "anatomy is invalid" tells the agent to guess which part. The base's deleted checks named
        # styleHeads, the torso/legs ratios and the face landmarks separately; so does this.
        self.assertEqual(E.anatomy_problems({"applies": True}), [
            "styleHeads must be greater than 0 (the head-unit proportion read off the reference)",
            "proportions must set a torso or legs head-unit ratio",
            "faceLandmarks must set eyeLine, noseBase or mouthLine from the reference",
        ])
        self.assertEqual(E.anatomy_problems(dict(self.ANATOMY)), [])

    def test_a_zero_or_boolean_measurement_does_not_count_as_measured(self) -> None:
        # `True` is an `int` in Python, so a field accidentally set to True would read as 1.
        for bad in (0, True, "8", None):
            with self.subTest(styleHeads=bad):
                problems = E.anatomy_problems(dict(self.ANATOMY, styleHeads=bad))
                self.assertTrue(any("styleHeads" in p for p in problems), bad)

    def test_style_heads_is_the_reference_free_way_through(self) -> None:
        self.assertEqual(self._emit("--style-heads", "8"), 0)

    def test_measured_anatomy_is_the_other_way_through(self) -> None:
        self.assertEqual(self._emit_with(self.ANATOMY), 0)


class TheAnatomyFileIsActuallyRead(unittest.TestCase):
    """`_anatomy_from` missed the shape the checklist actually writes, and nothing noticed.

    It looked only for an `"anatomy"` key, so a BARE anatomy block -- which is what
    `extract_landmarks.py --out anatomy.json` produces, and what `domain.json` passes -- returned
    None and the tool silently authored the DEFAULT humanoid instead of the measured one.

    It stayed invisible for an unlucky reason: the frozen fixture's measurements equal the
    template's defaults, so the emitted spec was byte-identical either way and every oracle stayed
    green. The byte-identity that proves this extraction correct was, for this one function, also
    what hid a bug in it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.bare = json.loads((FIXTURES / "anatomy.json").read_text(encoding="utf-8"))

    def test_the_bare_block_the_checklist_writes_is_read(self) -> None:
        self.assertEqual(E._anatomy_from(self.bare), self.bare)

    def test_the_wrapped_and_assessment_shapes_are_read_too(self) -> None:
        self.assertEqual(E._anatomy_from({"anatomy": self.bare}), self.bare)
        self.assertEqual(E._anatomy_from({"preSpecAssessment": {"anatomy": self.bare}}), self.bare)

    def test_nothing_anatomy_shaped_returns_none_rather_than_a_default(self) -> None:
        for payload in ({}, {"preSpecAssessment": {}}, {"anatomy": 5}, 5, None, []):
            with self.subTest(payload=payload):
                self.assertIsNone(E._anatomy_from(payload))

    def test_measurements_that_differ_from_the_defaults_survive_the_read(self) -> None:
        # The assertion the byte-identity could never make. A file whose numbers are NOT the
        # template defaults must produce a spec that is not the default one.
        taller = dict(self.bare, proportions=dict(self.bare["proportions"], torso=3.0))
        self.assertNotEqual(E.build(E._anatomy_from(taller))["specSections"]["componentTree"],
                            E.build(None)["specSections"]["componentTree"])


if __name__ == "__main__":
    unittest.main()
