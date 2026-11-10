"""Integrity gates for the garment-character runtime (route `garment-character`).

runtime/garment-character/manifest.json records the sha256/size of every runtime file and
of the node tests beside it. These tests keep them honest: every recorded file must match,
nothing may sit unlisted next to them, the node tests must import the runtime through the
plugin layout, the stored parameters must equal what the runtime exports now, and every
hand-read `subjectLiterals` citation must still point at the quoted source text. Each check
is a function with a counter-example test proving that it reports a deliberately broken input.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "garment-character"
TESTS = ROOT / "tests" / "garment-character"
MANIFEST = RUNTIME / "manifest.json"
PARAMETERS = ROOT / "reference" / "garment-parameters.json"
EXTRACTOR = ROOT / "tools" / "extract_garment_parameters.mjs"
CLASSES = {"subject", "behaviour"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_files(root: Path, entries: list[dict]) -> list[str]:
    """Return one message per recorded file that is missing or differs in size or sha256."""
    problems: list[str] = []
    for entry in entries:
        path = root / entry["path"]
        if not path.is_file():
            problems.append(f"{entry['path']}: missing")
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"]:
            problems.append(f"{entry['path']}: {len(data)} bytes, recorded {entry['bytes']}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            problems.append(f"{entry['path']}: sha256 {digest}, recorded {entry['sha256']}")
    return problems


def unlisted_files(entries: list[dict]) -> list[str]:
    """Files present in the copy directories that manifest.json does not record."""
    recorded = {entry["path"] for entry in entries}
    found = [p for p in RUNTIME.iterdir() if p.is_file() and p.name != "manifest.json"]
    found += [p for p in TESTS.iterdir() if p.is_file() and not p.name.startswith(".")]
    return sorted(str(p.relative_to(ROOT)) for p in found if str(p.relative_to(ROOT)) not in recorded)


def check_test_imports(root: Path, entries: list[dict]) -> list[str]:
    """Node tests must import runtime modules through ../../runtime/garment-character/, never from `./`."""
    problems: list[str] = []
    for entry in entries:
        if entry["kind"] != "test":
            continue
        text = (root / entry["path"]).read_text(encoding="utf-8")
        for number, line in enumerate(text.split("\n"), 1):
            if line.startswith("import ") and " from './" in line:
                problems.append(f"{entry['path']}:{number}: runtime module imported from the test directory")
    return problems


def check_subject_literals(root: Path, literals: list[dict]) -> list[str]:
    """Every entry's `literal` must be a verbatim substring of the cited line."""
    problems: list[str] = []
    cache: dict[str, list[str]] = {}
    for item in literals:
        if item.get("class") not in CLASSES:
            problems.append(f"{item.get('file')}:{item.get('line')}: class {item.get('class')!r} not in {sorted(CLASSES)}")
        lines = cache.setdefault(item["file"], (root / item["file"]).read_text(encoding="utf-8").split("\n"))
        number = item["line"]
        if not (1 <= number <= len(lines)):
            problems.append(f"{item['file']}:{number}: line out of range")
        elif item["literal"] not in lines[number - 1]:
            problems.append(f"{item['file']}:{number}: {item['literal']!r} not on that line")
    return problems


def constants_drift(stored: dict, current: dict) -> bool:
    return stored != current


class ManifestFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load(MANIFEST)
        cls.entries = cls.manifest["files"]

    def test_header(self):
        self.assertEqual(self.manifest["route"], "garment-character")
        self.assertEqual(self.manifest["buildStamp"], "guard-1")

    def test_every_recorded_file_matches_sha256_and_size(self):
        self.assertEqual(len(self.entries), 15)
        self.assertEqual(verify_files(ROOT, self.entries), [])

    def test_no_unlisted_file_beside_the_copies(self):
        self.assertEqual(unlisted_files(self.entries), [])

    def test_node_tests_import_the_runtime_through_the_plugin_layout(self):
        self.assertEqual(check_test_imports(ROOT, self.entries), [])

    def test_viewer_build_stamp_matches_the_copy(self):
        self.assertIn("build: '%s'" % self.manifest["buildStamp"], (RUNTIME / "viewer.mjs").read_text(encoding="utf-8"))

    def test_hash_check_reports_a_single_flipped_byte(self):
        entry = next(e for e in self.entries if e["path"].endswith("garment.mjs"))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / entry["path"]
            target.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / entry["path"], target)
            self.assertEqual(verify_files(Path(tmp), [entry]), [])
            data = bytearray(target.read_bytes())
            data[len(data) // 2] ^= 0x01  # same size, one bit different
            target.write_bytes(bytes(data))
            problems = verify_files(Path(tmp), [entry])
            self.assertEqual(len(problems), 1)
            self.assertIn("sha256", problems[0])
            target.write_bytes(bytes(data) + b"\n")
            self.assertTrue(any("bytes" in p for p in verify_files(Path(tmp), [entry])))
            target.unlink()
            self.assertEqual(verify_files(Path(tmp), [entry]), [f"{entry['path']}: missing"])

    def test_unlisted_and_misimporting_files_are_reported(self):
        trimmed = [e for e in self.entries if not e["path"].endswith("picking.mjs")]
        self.assertEqual(unlisted_files(trimmed), ["runtime/garment-character/picking.mjs"])
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "tests" / "garment-character" / "x.test.mjs"
            bad.parent.mkdir(parents=True)
            bad.write_text("import { a } from './garment.mjs';\n", encoding="utf-8")
            entry = {"path": "tests/garment-character/x.test.mjs", "kind": "test"}
            self.assertEqual(len(check_test_imports(Path(tmp), [entry])), 1)


@unittest.skipUnless(shutil.which("node") and (ROOT / "node_modules" / "three").is_dir(), "node and node_modules/three are required")
class ParametersMatchRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stored = load(PARAMETERS)
        cls.current = json.loads(subprocess.run(
            ["node", str(EXTRACTOR)], cwd=ROOT, check=True, capture_output=True, text=True, timeout=60).stdout)

    def test_stored_constants_equal_extractor_output(self):
        self.assertFalse(constants_drift(self.stored["constants"], self.current["constants"]))
        self.assertEqual(self.stored["generatedFrom"], self.current["generatedFrom"])

    def test_required_constants_are_present(self):
        constants = self.stored["constants"]
        for name in ("STRAP", "PANEL", "PULL_PATCH", "STRAP_FIELD", "CUP_LIFT", "CONTACT_STEADY", "SKIN_GUARD", "FLAP", "TRANSITION", "REDUCED_TRANSITION", "OUTFITS"):
            self.assertIn(name, constants["garment"])
        self.assertIn("ROUND_CHEST", constants["chest-field"])
        self.assertEqual(sorted(constants["softbody"]), ["PROFILES", "REGION_IDS"])

    def test_drift_is_detected(self):
        changed = json.loads(json.dumps(self.stored["constants"]))
        changed["garment"]["SKIN_GUARD"]["floor"] += 0.0001
        self.assertTrue(constants_drift(changed, self.current["constants"]))


class SubjectLiterals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.literals = load(PARAMETERS)["subjectLiterals"]

    def test_every_citation_points_at_its_quoted_text(self):
        self.assertEqual(check_subject_literals(RUNTIME, self.literals), [])

    def test_coordinate_and_name_literals_are_listed(self):
        quoted = {(item["file"], item["literal"]) for item in self.literals if item["class"] == "subject"}
        for expected in (
            ("garment.mjs", "yAttach: 1.425"), ("garment.mjs", "yTop: 1.49"), ("garment.mjs", "(0, 1.47, 0.04)"),
            ("garment.mjs", "'Body'"), ("cloth-contact.mjs", "< 1.19"), ("cloth-contact.mjs", "> 1.65"),
            ("viewer.mjs", "m.name==='Body'"), ("viewer.mjs", "m.name === 'BikiniTop'"),
        ):
            self.assertIn(expected, quoted)

    def test_wrong_line_or_class_is_reported(self):
        wrong_line = [dict(self.literals[0], line=self.literals[0]["line"] + 1, literal="no such text anywhere")]
        self.assertTrue(check_subject_literals(RUNTIME, wrong_line))
        wrong_class = [dict(self.literals[0], **{"class": "guess"})]
        self.assertTrue(check_subject_literals(RUNTIME, wrong_class))


if __name__ == "__main__":
    unittest.main()
