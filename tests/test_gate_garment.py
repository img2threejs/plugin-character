#!/usr/bin/env python3
"""Tests for tools/gate_garment.py - 'the garment is the outer layer: the skin never shows in front
of the cloth, however hard it is pulled'.

Two kinds of test, and the second is the one that matters. The real evidence (the JOB matrices that
shipped with the reference viewer, copied under fixtures/garment-gate/) must say what the files actually
record, no more. Then every counter-example - a case with skin in front of the cloth, a missing
angle, a gentle pull, synthetic events only, an empty matrix - must FAIL, for the intended check.

The gate is stdlib-only and is run as a subprocess so the exit code is what is asserted.
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
GATE = PLUGIN_DIR / "tools" / "gate_garment.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "garment-gate"
DESKTOP = FIX / "skin-guard-desktop.json"
OTHER = FIX / "skin-guard-other.json"
RELEASE = FIX / "connected-interaction.release.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class GateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._n = 0

    def write(self, doc):
        self._n += 1
        path = self.tmp / ("matrix-%d.json" % self._n)
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def run_gate(self, *matrices, extra=()):
        argv = [sys.executable, str(GATE), "--json"]
        for m in matrices:
            argv += ["--matrix", str(m)]
        argv += list(extra)
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        envelope = json.loads(proc.stdout.strip().splitlines()[-1])
        checks = {c["id"]: c for c in envelope["evidence"]["checks"]}
        return proc.returncode, envelope, checks

    def run_plain(self, *matrices):
        argv = [sys.executable, str(GATE)]
        for m in matrices:
            argv += ["--matrix", str(m)]
        return subprocess.run(argv, capture_output=True, text=True, timeout=60)


class RealEvidence(GateCase):
    def test_clean_and_complete_on_the_real_matrices(self):
        code, env, checks = self.run_gate(DESKTOP, OTHER)
        self.assertEqual(checks["G1"]["verdict"], "pass", checks["G1"])
        self.assertEqual(checks["G2"]["verdict"], "pass", checks["G2"])
        self.assertIn("93 cases", checks["G1"]["summary"])
        self.assertIn("48 mouse pulls, 16 touch, 16 tissue, 13 combos", checks["G2"]["summary"])
        self.assertNotEqual(code, 0)  # G3/G4/G5 do not pass on these two files alone

    def test_g3_reports_which_files_do_not_record_phase_counts(self):
        _, _, checks = self.run_gate(DESKTOP, OTHER)
        g3 = checks["G3"]
        self.assertEqual(g3["verdict"], "unmeasured")
        text = " ".join(g3["detail"])
        self.assertIn("skin-guard-desktop.json [pull]: 48 cases record no phases", text)
        self.assertIn("skin-guard-other.json [combo]: 13 cases record no phases", text)
        self.assertIn("32 record per-phase counts and meet the minimum", g3["summary"])

    def test_g3_passes_when_every_case_records_its_phases(self):
        # touch + tissue are the sections that record phases.{hold,rebound,settled}.n
        other = load(OTHER)
        phased = self.write({"touch": other["touch"], "tissue": other["tissue"]})
        _, _, checks = self.run_gate(phased)
        self.assertEqual(checks["G3"]["verdict"], "pass", checks["G3"])

    def test_g4_names_the_real_pulls_that_stayed_short_under_a_strict_fraction(self):
        code, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--min-pull-fraction", "0.75"])
        g4 = checks["G4"]
        self.assertEqual(g4["verdict"], "fail")
        text = " ".join(g4["detail"])
        for needle in ("green ribbon side +1(left) 225 deg: pull 25.93",
                       "green ribbon side -1(right) 315 deg: pull 25.92",
                       "orange ribbon side +1(left) 225 deg: pull 25.93"):
            self.assertIn(needle, text)
        self.assertEqual(code, 1)

    def test_g4_absolute_overrides_still_work(self):
        # the real minima are ribbon 25.92 mm and (two-handed combo) cup 17.18 mm
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--min-ribbon-pull-mm", "25.9", "--min-cup-pull-mm", "17.1"])
        self.assertEqual(checks["G4"]["verdict"], "pass", checks["G4"])
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--min-ribbon-pull-mm", "26", "--min-cup-pull-mm", "17.1"])
        self.assertEqual(checks["G4"]["verdict"], "fail")

    def test_g5_is_unmeasured_without_release_records_and_passes_with_them(self):
        _, _, checks = self.run_gate(DESKTOP, OTHER)
        self.assertEqual(checks["G5"]["verdict"], "unmeasured")
        self.assertIn("afterRelease", checks["G5"]["summary"])
        _, _, checks = self.run_gate(DESKTOP, OTHER, RELEASE)
        self.assertEqual(checks["G5"]["verdict"], "pass", checks["G5"])
        self.assertIn("16 released cases", checks["G5"]["summary"])

    def test_overall_never_passes_while_any_check_is_unmeasured_or_failed(self):
        code, env, checks = self.run_gate(DESKTOP, OTHER, RELEASE)
        self.assertEqual([k for k, v in checks.items() if v["verdict"] != "pass"], ["G3"])
        self.assertEqual(code, 2)
        self.assertEqual(env["status"], "error")
        self.assertEqual(env["kind"], "img2.gate-verdict")

    def test_plain_output_prints_every_verdict(self):
        proc = self.run_plain(DESKTOP, OTHER)
        for gid in ("G1 pass", "G2 pass", "G3 unmeasured", "G4 pass", "G5 unmeasured"):
            self.assertIn(gid, proc.stdout)
        self.assertEqual(proc.returncode, 2)


class CounterExamples(GateCase):
    def test_skin_in_front_of_the_cloth_fails_g1(self):
        doc = load(DESKTOP)
        doc["cases"][20]["inside"] = 3
        doc["cases"][20]["deepestMm"] = 2.1
        code, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G1"]["verdict"], "fail")
        self.assertIn("inside=3", " ".join(checks["G1"]["detail"]))
        self.assertIn("deepestMm=2.1", " ".join(checks["G1"]["detail"]))
        self.assertIn("1 of 48 cases", checks["G1"]["summary"])
        self.assertEqual(code, 1)

    def test_deeper_than_threshold_fails_g1_even_with_zero_inside(self):
        doc = load(DESKTOP)
        doc["cases"][0]["deepestMm"] = 0.31
        _, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G1"]["verdict"], "fail")

    def test_a_bad_phase_hides_nowhere(self):
        doc = load(OTHER)
        doc["touch"][3]["phases"]["rebound"]["insideSkin"] = 5
        _, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G1"]["verdict"], "fail")
        self.assertIn("inside=5", " ".join(checks["G1"]["detail"]))

    def test_case_without_inside_measurement_is_not_a_clean_pass(self):
        doc = load(DESKTOP)
        for key in ("inside", "deepestMm"):
            del doc["cases"][0][key]
        _, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G1"]["verdict"], "unmeasured")

    def test_one_missing_angle_fails_g2_and_names_it(self):
        doc = load(DESKTOP)
        doc["cases"] = [c for c in doc["cases"]
                        if not (c["kind"] == "ribbon" and c["side"] == 1 and c["angleDeg"] == 135)]
        code, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertIn("ribbon side +1(left) angles [135]", " ".join(checks["G2"]["detail"]))
        self.assertEqual(code, 1)

    def test_left_ribbon_in_one_outfit_only_fails_g2(self):
        doc = load(DESKTOP)
        doc["cases"] = [c for c in doc["cases"]
                        if not (c["kind"] == "ribbon" and c["side"] == 1 and c["outfit"] == "orange")]
        _, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertIn("left ribbon must be covered at all 8 angles in 2 outfits", " ".join(checks["G2"]["detail"]))

    def test_gentle_ribbon_pulls_fail_g4(self):
        doc = load(DESKTOP)
        for c in doc["cases"]:
            if c["kind"] == "ribbon":
                c["pullMm"] = 12.0
        code, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G4"]["verdict"], "fail")
        self.assertIn("pull 12 mm < 24.5", " ".join(checks["G4"]["detail"]))
        self.assertEqual(checks["G1"]["verdict"], "pass")  # clean skin, but the pulls proved nothing
        self.assertEqual(code, 1)

    def test_pull_distance_not_recorded_is_unmeasured_not_pass(self):
        doc = load(DESKTOP)
        for c in doc["cases"]:
            del c["pullMm"]
        _, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G4"]["verdict"], "unmeasured")

    def test_synthetic_events_only_fail_g2(self):
        doc = load(DESKTOP)
        for c in doc["cases"]:
            c["trusted"] = False
        code, _, checks = self.run_gate(self.write(doc))
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertIn("trusted mouse pull", " ".join(checks["G2"]["detail"]))
        self.assertEqual(code, 1)

    def test_touch_in_one_outfit_only_fails_g2(self):
        desktop, other = load(DESKTOP), load(OTHER)
        other["touch"] = [c for c in other["touch"] if c["outfit"] == "green"]
        _, _, checks = self.run_gate(self.write(desktop), self.write(other))
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertIn("trusted touch: orange", " ".join(checks["G2"]["detail"]))

    def test_missing_tissue_squeeze_on_right_cup_fails_g2(self):
        desktop, other = load(DESKTOP), load(OTHER)
        other["tissue"] = [c for c in other["tissue"] if not (c["mode"] == "squeeze" and c["side"] == "right")]
        _, _, checks = self.run_gate(self.write(desktop), self.write(other))
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertIn("tissue squeeze on cup side -1(right)", " ".join(checks["G2"]["detail"]))

    def test_too_few_combos_fail_g2(self):
        desktop, other = load(DESKTOP), load(OTHER)
        other["combos"] = other["combos"][:9]
        _, _, checks = self.run_gate(self.write(desktop), self.write(other))
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertIn("combos: 9 recorded, need >= 10", " ".join(checks["G2"]["detail"]))

    def test_under_sampled_phase_fails_g3(self):
        other = load(OTHER)
        other["touch"][0]["phases"]["hold"]["n"] = 1
        _, _, checks = self.run_gate(self.write(other))
        self.assertEqual(checks["G3"]["verdict"], "fail")
        self.assertIn("hold 1 < 3", " ".join(checks["G3"]["detail"]))

    def test_release_mismatch_or_still_grabbed_fails_g5(self):
        for patch in ({"renderMismatch": 0.002, "stillGrabbed": False}, {"renderMismatch": 0, "stillGrabbed": True}):
            doc = load(RELEASE)
            doc["matrix"]["desktop"][2]["afterRelease"] = patch
            _, _, checks = self.run_gate(self.write(doc))
            self.assertEqual(checks["G5"]["verdict"], "fail", patch)

    def test_missing_file_is_an_error_not_a_pass(self):
        missing = self.tmp / "does-not-exist.json"
        code, env, checks = self.run_gate(DESKTOP, missing)
        self.assertEqual(code, 2)
        self.assertEqual(env["status"], "error")
        self.assertIn("matrix file not found", env["reasons"][0])
        self.assertEqual(checks, {})
        proc = self.run_plain(missing)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("matrix file not found", proc.stdout)

    def test_unusable_inputs_are_errors(self):
        broken = self.tmp / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        code, env, _ = self.run_gate(broken)
        self.assertEqual((code, env["status"]), (2, "error"))
        code, env, _ = self.run_gate(self.write([1, 2, 3]))
        self.assertEqual((code, env["status"]), (2, "error"))
        code, env, _ = self.run_gate(self.write({"hello": 1}))
        self.assertEqual((code, env["status"]), (2, "error"))

    def test_no_matrix_argument_is_a_usage_error(self):
        proc = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)


class EmptyNeverPasses(GateCase):
    def test_empty_cases_list_passes_nothing(self):
        for doc in ({"cases": []}, {"cases": [], "touch": [], "tissue": [], "combos": []}):
            code, env, checks = self.run_gate(self.write(doc))
            self.assertEqual(set(checks), {"G1", "G2", "G3", "G4", "G5"})
            self.assertEqual([k for k, v in checks.items() if v["verdict"] == "pass"], [], checks)
            self.assertEqual(checks["G1"]["verdict"], "fail")
            self.assertEqual(checks["G2"]["verdict"], "fail")
            self.assertEqual(code, 1)
            self.assertNotEqual(env["status"], "pass")

    def test_only_release_records_prove_nothing_about_the_skin(self):
        _, _, checks = self.run_gate(RELEASE)
        self.assertEqual(checks["G1"]["verdict"], "fail")
        self.assertEqual(checks["G2"]["verdict"], "fail")
        self.assertNotEqual(checks["G3"]["verdict"], "pass")


class DeclaredSampling(GateCase):
    DECL = ["--sampling-declared", "hold 36 frames/12, release, rebound 60/12, settle 300 + 1 sample = 9 per case"]

    def test_no_declaration_is_unmeasured(self):
        _, _, checks = self.run_gate(DESKTOP, OTHER)
        self.assertEqual(checks["G3"]["verdict"], "unmeasured")
        self.assertIn("--sampling-declared", " ".join(checks["G3"]["detail"]))

    def test_declaration_with_nine_samples_passes_and_says_so(self):
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=self.DECL)
        self.assertEqual(checks["G3"]["verdict"], "pass", checks["G3"])
        self.assertIn("declared, not recorded: hold 36 frames/12", " ".join(checks["G3"]["detail"]))

    def test_declaration_with_five_samples_fails(self):
        desktop = load(DESKTOP)
        desktop["cases"][0]["samples"] = 5
        _, _, checks = self.run_gate(self.write(desktop), OTHER, extra=self.DECL)
        self.assertEqual(checks["G3"]["verdict"], "fail")
        self.assertIn("samples 5 < 9", " ".join(checks["G3"]["detail"]))

    def test_declaration_without_a_samples_field_stays_unmeasured(self):
        desktop = load(DESKTOP)
        del desktop["cases"][0]["samples"]
        _, _, checks = self.run_gate(self.write(desktop), OTHER, extra=self.DECL)
        self.assertEqual(checks["G3"]["verdict"], "unmeasured")

    def test_recorded_phase_counts_still_win_over_a_declaration(self):
        other = load(OTHER)
        other["touch"][0]["phases"]["hold"]["n"] = 1
        other["touch"][0]["samples"] = 50
        _, _, checks = self.run_gate(self.write(other), extra=self.DECL)
        self.assertEqual(checks["G3"]["verdict"], "fail")
        self.assertIn("hold 1 < 3", " ".join(checks["G3"]["detail"]))

    def test_real_evidence_with_declaration_passes_everything(self):
        code, env, checks = self.run_gate(DESKTOP, OTHER, RELEASE, extra=self.DECL)
        self.assertEqual({k: v["verdict"] for k, v in checks.items()}, {k: "pass" for k in ("G1", "G2", "G3", "G4", "G5")})
        self.assertEqual((code, env["status"]), (0, "pass"))


class RelativeG4(GateCase):
    def test_delivered_minima_pass_at_the_relative_threshold(self):
        _, _, checks = self.run_gate(DESKTOP, OTHER)
        g4 = checks["G4"]
        self.assertEqual(g4["verdict"], "pass", g4)
        text = " ".join(g4["detail"])
        self.assertIn("225/315 degrees", text)
        self.assertIn("stretches with resistance", text)
        self.assertIn("ribbon >= 0.7 x 35 mm = 24.50 mm", text)
        self.assertIn("cup >= 0.7 x 24 mm = 16.80 mm", text)

    def test_fraction_flag_is_honoured(self):
        # 0.75 x 35 = 26.25 > 25.92 -> the real 225/315 degree pulls now fall short
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--min-pull-fraction", "0.75"])
        self.assertEqual(checks["G4"]["verdict"], "fail")

    def test_twelve_mm_ribbon_pulls_fail(self):
        doc = load(DESKTOP)
        for c in doc["cases"]:
            if c["kind"] == "ribbon":
                c["pullMm"] = 12.0
        _, _, checks = self.run_gate(self.write(doc), OTHER)
        self.assertEqual(checks["G4"]["verdict"], "fail")

    def test_no_limit_is_unmeasured(self):
        empty = self.write({"constants": {}})
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--parameters", str(empty)])
        self.assertEqual(checks["G4"]["verdict"], "unmeasured")
        self.assertIn("no limit known", " ".join(checks["G4"]["detail"]))

    def test_limit_flags_are_the_fallback_when_the_file_has_none(self):
        empty = self.write({"constants": {}})
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--parameters", str(empty), "--ribbon-limit-mm", "35",
                                                            "--cup-limit-mm", "24"])
        self.assertEqual(checks["G4"]["verdict"], "pass", checks["G4"])
        _, _, checks = self.run_gate(DESKTOP, OTHER, extra=["--parameters", str(empty), "--ribbon-limit-mm", "50",
                                                            "--cup-limit-mm", "24"])
        self.assertEqual(checks["G4"]["verdict"], "fail")

    def test_missing_explicit_parameters_file_is_an_error(self):
        code, env, _ = self.run_gate(DESKTOP, extra=["--parameters", str(self.tmp / "nope.json")])
        self.assertEqual((code, env["status"]), (2, "error"))


class UsageAndCoverageDetail(GateCase):
    def test_help_mentions_connected_interaction_for_release_evidence(self):
        proc = subprocess.run([sys.executable, str(GATE), "--help"], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("connected-interaction.json", proc.stdout)
        self.assertIn("--sampling-declared", proc.stdout)

    def test_g2_reports_two_handed_combos(self):
        other = load(OTHER)
        expected = sum(1 for c in other["combos"] if len(c.get("pulls", [])) >= 2)
        _, _, checks = self.run_gate(DESKTOP, OTHER)
        self.assertEqual(expected, 7)
        self.assertIn("%d of 13 combos are two-handed" % expected, " ".join(checks["G2"]["detail"]))


class AllPass(GateCase):
    def test_a_fully_recorded_clean_matrix_passes_every_check(self):
        """The positive control: the gate CAN say pass. The real files lack per-phase counts for the
        desktop and combo sections, so build the full record from them - every record carries what
        the gate needs - and require exit 0."""
        desktop, other = load(DESKTOP), load(OTHER)
        phases = {"hold": {"n": 3}, "rebound": {"n": 5}, "settled": {"n": 1}}
        for c in desktop["cases"]:
            c["phases"] = copy.deepcopy(phases)
            c["pullMm"] = 34.0 if c["kind"] == "ribbon" else 24.0
        for c in other["combos"]:
            c["phases"] = copy.deepcopy(phases)
            for kind, floor in (("strap", 34.0), ("panel", 24.0)):
                for side in ("1", "-1"):
                    if c["pullMmAtHold"][kind][side]:
                        c["pullMmAtHold"][kind][side] = floor
        code, env, checks = self.run_gate(self.write(desktop), self.write(other), RELEASE)
        self.assertEqual({k: v["verdict"] for k, v in checks.items()},
                         {"G1": "pass", "G2": "pass", "G3": "pass", "G4": "pass", "G5": "pass"})
        self.assertEqual((code, env["status"]), (0, "pass"))


if __name__ == "__main__":
    unittest.main()
