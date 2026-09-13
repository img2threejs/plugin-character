#!/usr/bin/env python3
"""Emit the spec-augmentation artifact the base pipeline pulls.

The base authors a skeleton and lets the agent infer the shape from the reference. When this plugin
is installed, this step publishes the character track instead, and the base merges it at
`spec-authoring` — which already passes `--augmentation spec-augmentation.json`, so nothing in the
base has to change to invoke this.

The base PULLS; this never writes into the base's spec (PLUGIN_CONTRACT.md §14). It takes **no
`--spec` argument** by design: a tool that read the base's output and handed it back would make the
base's spec an input to the artifact the base then merges, which is the push relationship inverted
rather than avoided. Everything here is authored from this plugin's own knowledge and from the
evidence its own checklist steps produced.

    specSections     wholesale spec sections this domain authors
    assessmentPatch  fields merged into preSpecAssessment (which is base-owned, so it cannot ride
                     in specSections)
    qualityFloors    merged RAISE-ONLY by the base; this domain proposes none today

WHOLESALE MEANS WHOLESALE. `merge_spec_augmentation` assigns `spec[key] = value` for every
specSection, so a section this plugin contributes must be COMPLETE, not a patch. Measured against
the frozen oracle: five of the six sections below are byte-identical when authored from an empty
dict, and `sculptPipeline` is not — the template sets `passOrder` and `currentPass` while the base
owns `passGateMode`, `completedPasses`, `lastCompletedPass`, `blockedReason` and
`nextRequiredEvidence`. Those five are static defaults, carried here as `BASE_PIPELINE_DEFAULTS` and
pinned by `tests/test_character_authoring_oracle.py`, exactly as `BASE_DEFAULT_MATERIAL` is in
`character_spec_template.py`.

(The alternative — have the base derive `sculptPipeline.passOrder` from the contributed
`buildPasses` and let the plugin contribute neither — is a cleaner end state and a base change this
slice does not need. Recorded as a follow-up rather than taken.)
"""

from __future__ import annotations

import argparse
import json
import os, sys
root = os.environ.get("IMG2_HOME")
if root: sys.path.insert(0, os.path.join(root, "harness"))
else:
    try: import _img2_local; sys.path.insert(0, _img2_local.CORE)
    except ImportError: sys.exit("img2: core not linked - run `img2 sync`")
from img2_core import require_core_api
require_core_api(1)

from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from character_spec_template import apply_character_template  # noqa: E402

ARTIFACT_KIND = "spec-augmentation-v1"
PLUGIN_ID = "character"

# The anatomy gate, moved here from the base's deleted `validate_character_track`. It fired under
# `--strict-quality`, which promotes warnings to errors, and `strict-validation` is a MANDATORY base
# checklist step -- so before the extraction a character run whose agent never filled `anatomy.json`
# was BLOCKED with "anatomy.applies is not true; fill anatomy (styleHeads, proportions, pose,
# faceLandmarks) from the reference".
#
# The base cannot keep that check: it has no view on anatomy any more. If the producer does not make
# it, it exists in neither repo -- which is what a code review measured here, against a test
# docstring of mine that ASSERTED the producer refused. It did not. `build(None)` authored a full
# default humanoid and exited 0, so a run with no landmark evidence at all shipped a spec with
# invented proportions and nothing anywhere said so.
#
# Refusing at the producer is stricter than the base was, deliberately. The base could only warn
# until strict; here there is a real alternative for a figure with no reference -- `--style-heads`,
# which labels its numbers as canon. "I have no measurements" is a statement the caller must now
# make out loud instead of one the default quietly makes for them.
#
# The fifth of the old checks -- featureReviewTargets covering anatomy/face/pose/outfit -- is not
# repeated: the template authors all four unconditionally (pinned by the authoring oracle), so it
# can no longer fail. Named here so the next reader knows it was considered, not dropped.
ANATOMY_REQUIRED = (
    ("styleHeads", ("styleHeads",),
     "styleHeads must be greater than 0 (the head-unit proportion read off the reference)"),
    ("proportions", ("torso", "legs"),
     "proportions must set a torso or legs head-unit ratio"),
    ("faceLandmarks", ("eyeLine", "noseBase", "mouthLine"),
     "faceLandmarks must set eyeLine, noseBase or mouthLine from the reference"),
)


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0


def anatomy_problems(anatomy: Any) -> list[str]:
    """What stops this anatomy block counting as measured evidence. Empty means it counts."""
    if not isinstance(anatomy, dict):
        return ["no anatomy block was supplied"]
    if anatomy.get("applies") is not True:
        return ["anatomy.applies is not true"]
    problems = []
    for key, fields, message in ANATOMY_REQUIRED:
        block = anatomy if key == "styleHeads" else anatomy.get(key)
        source = block if isinstance(block, dict) else {}
        if key == "styleHeads":
            source = anatomy
        if not any(_positive(source.get(field)) for field in fields):
            problems.append(message)
    return problems

# Keys the BASE owns; a section named here is refused by the merge. Pinned duplicate of
# `forge/_shared/spec_augmentation.py:26` — a plugin may not import base code, so the agreement is
# asserted by `tests/test_character_template.py` from this side and by the base from the other.
BASE_OWNED = ("qualityContract", "preSpecAssessment", "pipelineRouting", "sourceImage",
              "targetName", "localSpecSearch")

# preSpecAssessment is base-owned, so the one field the template sets inside it travels separately.
ASSESSMENT_FIELDS = ("objectClass",)

# The base's own sculptPipeline defaults, which the character template does not set and a wholesale
# replace would therefore drop. Copied from `make_spec` at `6e60b5e`; pinned by the authoring oracle.
BASE_PIPELINE_DEFAULTS: dict[str, Any] = {
    "passGateMode": "locked-sequential",
    "completedPasses": [],
    "lastCompletedPass": "",
    "blockedReason": "blockout requires a browser screenshot and self-correction review before structural-pass unlocks",
    "nextRequiredEvidence": [
        "blockout browser render screenshot from your agent's browser/screenshot tool",
        "side-by-side reference/render comparison sheet",
        "AI vision score >= 0.7 with layer scores and mismatch critique",
        "critical semantic feature scores from the same image pair meeting their individual thresholds",
        "reviewHistory entry for blockout with action=continue",
    ],
}


def _plugin_version() -> str:
    manifest = Path(__file__).resolve().parent.parent / "plugin.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def _anatomy_from(payload: Any) -> dict | None:
    """The anatomy block, in any of the three shapes it actually arrives in.

        {"applies": true, "styleHeads": …}                  BARE -- what the checklist writes
        {"anatomy": {...}}                                  wrapped
        {"preSpecAssessment": {"anatomy": {...}}}           inside an assessment

    The bare form is the one that matters and the one this function used to MISS: it only ever
    looked for an `"anatomy"` key, so `--anatomy anatomy.json` pointed at the real fixture returned
    None and the tool authored the DEFAULT humanoid instead of the measured one.

    Nothing caught it, for an unlucky reason: the fixture's measurements happen to equal the
    template's defaults, so the emitted spec was byte-identical either way and every oracle stayed
    green. The test that looked like it covered this (`test_anatomy_actually_reaches_the_template`)
    passes its dict straight to the template and never goes through this function. It took adding
    the anatomy gate below -- which refuses when no block is found -- to make the silence audible.
    """
    if not isinstance(payload, dict):
        return None
    for candidate in (payload.get("preSpecAssessment", {}).get("anatomy")
                      if isinstance(payload.get("preSpecAssessment"), dict) else None,
                      payload.get("anatomy"),
                      payload if "applies" in payload else None):
        if isinstance(candidate, dict):
            return candidate
    return None


def build(anatomy: dict | None, include_accessories: bool = False,
          style_heads: float | None = None) -> dict[str, Any]:
    """Author the character track into an empty dict and partition it for the base's merge."""
    derived_anatomy = None
    if style_heads is not None:
        import humanoid_proportions  # noqa: PLC0415
        anatomy = derived_anatomy = humanoid_proportions.derive_anatomy(style_heads)

    scratch: dict[str, Any] = {}
    apply_character_template(scratch, anatomy, include_accessories=include_accessories)

    # sculptPipeline is the one section the template only partially fills. Base defaults first so
    # the key order matches what the base produced; the template's own keys then land in place.
    pipeline = dict(BASE_PIPELINE_DEFAULTS)
    pipeline.update(scratch.get("sculptPipeline") or {})
    missing = [k for k in ("passOrder", "currentPass") if k not in pipeline]
    if missing:
        # Unreachable while the template sets them, and pinned by
        # `test_the_carried_set_is_exactly_what_the_template_does_not_set`. A bare KeyError three
        # lines down would name the key and not the reason.
        raise ValueError(f"the character template stopped setting sculptPipeline {missing}; the "
                         f"base owns the rest and this tool has nothing to carry them onto")
    scratch["sculptPipeline"] = {
        "passGateMode": pipeline["passGateMode"],
        "passOrder": pipeline["passOrder"],
        "currentPass": pipeline["currentPass"],
        "completedPasses": pipeline["completedPasses"],
        "lastCompletedPass": pipeline["lastCompletedPass"],
        "blockedReason": pipeline["blockedReason"],
        "nextRequiredEvidence": pipeline["nextRequiredEvidence"],
    }

    pre = scratch.get("preSpecAssessment") or {}
    assessment_patch = {k: pre[k] for k in ASSESSMENT_FIELDS if k in pre}
    # The resolved-domain marker is set by domain resolution, never proposed by the artifact that
    # resolution selected. The merge refuses it; popping it here keeps the refusal from firing.
    assessment_patch.get("objectClass", {}).pop("domain", None)
    # Only anatomy this plugin DERIVED travels back. Anatomy read from the base's own assessment is
    # already in the spec; echoing it into the patch would overwrite the base's copy with a
    # round-tripped one and change the authored spec for no gain. Measured: doing so was the only
    # difference besides the resolved-domain marker when this artifact was first merged.
    if derived_anatomy is not None:
        assessment_patch["anatomy"] = derived_anatomy

    artifact: dict[str, Any] = {
        "kind": ARTIFACT_KIND,
        "provenance": {"provider": PLUGIN_ID, "version": _plugin_version()},
        "specSections": {k: v for k, v in scratch.items() if k not in BASE_OWNED},
    }
    if assessment_patch:
        artifact["assessmentPatch"] = assessment_patch
    return artifact


def build_parser() -> argparse.ArgumentParser:
    """Separate from `main` so a test can ask argparse what the options ARE.

    The alternative -- grepping `--help` -- reads the docstring too, and the docstring's whole
    subject is the `--spec` argument that deliberately does not exist. It found it, and passed.
    """
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="write the artifact here")
    # No `--assessment`. This step is anchored before `local-spec-search`, which is before
    # `pre-spec-assessment`, so at the moment it runs there IS no assessment -- only the
    # `anatomy.json` that `character-landmarks` wrote one step earlier. A flag for an input that
    # cannot exist yet is surface a reader has to reason about and nothing can produce.
    parser.add_argument("--anatomy", type=Path,
                        help="anatomy.json from the character-landmarks step")
    parser.add_argument("--accessories", action="store_true",
                        help="include the four accessory materials and their feature targets. "
                             "Replaces the base's removed --accessories flag")
    parser.add_argument("--style-heads", type=float,
                        help="reference-free figure: derive anatomy from public canon at this many "
                             "head heights instead of measuring it")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.style_heads is not None and args.anatomy is not None:
        parser.error("--style-heads derives anatomy from public canon; it cannot be combined with "
                     "the measured anatomy in --anatomy")

    anatomy = None
    if args.anatomy is not None:
        anatomy = _anatomy_from(json.loads(args.anatomy.expanduser().read_text(encoding="utf-8")))

    if args.style_heads is None:
        problems = anatomy_problems(anatomy)
        if problems:
            parser.error(
                "this domain will not author a figure from invented proportions: "
                + "; ".join(problems)
                + ". Run the character-landmarks step to measure them from the reference, or say "
                  "the figure is reference-free with --style-heads N to take them from public "
                  "figure-drawing canon, which is labelled as canon rather than as evidence"
            )

    try:
        artifact = build(anatomy, args.accessories, args.style_heads)
    except ValueError as exc:
        parser.error(str(exc))

    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sections = artifact["specSections"]
    print(json.dumps({"kind": artifact["kind"], "out": str(out),
                      "components": len(sections["componentTree"]),
                      "bones": len(sections["rig"].get("bones", [])),
                      "materials": len(sections["materials"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
