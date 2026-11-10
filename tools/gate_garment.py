#!/usr/bin/env python3
"""Garment gate: the garment is the OUTER LAYER - the skin must never show in front of the cloth,
however hard it is pulled.

It judges recorded evidence, it does not measure. The measuring is done in a browser by
tools/skin_probes.js (`window.__inside`, `__combo*`): for every garment vertex and triangle centre
it finds the signed distance to the nearest triangle of the CPU-skinned body and counts a sample as
"inside" when it is more than 0.3 mm under the skin. A matrix run writes one record per case; this
gate reads those matrices and returns one verdict per check:

  G1 clean      no case has inside > 0 and none is deeper than 0.3 mm
  G2 coverage   the matrix is complete, not merely clean (an unmeasured cell is not a pass)
  G3 phases     every case sampled hold (>=3), rebound (>=3) and settled (>=1)
  G4 hard pull  each ribbon/cup pull reached >= 0.7 x its limit (default; see below)
  G5 release    after release the render is restored exactly (renderMismatch == 0, not grabbed)

Verdicts are pass | fail | unmeasured. Only a recorded value can pass: a field the file does not
record gives `unmeasured`, and unmeasured is NOT passing. Exit 0 only when all five pass; 1 when
any check fails; 2 when nothing fails but something is unmeasured or an input is unusable (the
gate_rigging.py convention: "we did not check" is never "we checked and it was fine").

Input shapes it understands (field names differ between sections, on purpose of the recorder):
  {cases:[...]}                 mouse pull matrix: kind ribbon|cup, side +1|-1, angleDeg, pullMm,
                                inside, deepestMm, trusted, samples (no per-phase counts)
  {touch:[...], tissue:[...], combos:[...]}
                                touch: kind strap|panel, side left|right, sideValue, phases{n},
                                insideSkin, pullMm; tissue: mode grab|squeeze; combos: API pulls,
                                pullMmAtHold{kind:{side:mm}}, runWorst{phase:mm}
  {matrix:{group:[...]}}        connected-interaction evidence; read for afterRelease only (G5)
strap == ribbon and panel == cup; side +1 == left, -1 == right.

Scope of G4: a case counts as a hard pull when it pulls the garment (pull matrix, touch, combo
pulls); tissue grab/squeeze never grab the cloth and are exempt. The recorded files do not say
whether each drag went past the limit, so G4 requires every garment pull to reach a FRACTION
(default 0.7, --min-pull-fraction) of its limit, read from reference/garment-parameters.json
(constants STRAP.maxPull for ribbons, PANEL.maxPull for cups; --parameters FILE, or the flags
--ribbon-limit-mm / --cup-limit-mm). No limit known -> unmeasured. Direction-limited pulls
(225/315 degrees) stop short of the nominal limit because the pull stretches with resistance.
--min-ribbon-pull-mm / --min-cup-pull-mm stay as optional absolute overrides.

Scope of G3: per-phase counts (>= 3 hold, >= 3 rebound, >= 1 settled) win when a case records them.
A case with only a total `samples` is unmeasured unless --sampling-declared "<text>" is passed and
every such case has samples >= 9 (pass, reported as "declared, not recorded"); fewer fails.

Release evidence needs evidence/connected-interaction.json as an extra --matrix (G5).

    python3 tools/gate_garment.py --matrix desktop.json --matrix other.json --matrix connected-interaction.json [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

GATE_ID = "garment"
PLUGIN_ID = "character"

PASS, FAIL, UNMEASURED = "pass", "fail", "unmeasured"

MAX_DEEPEST_MM = 0.3  # the probe's own inside threshold
REQUIRED_ANGLES = (0, 45, 90, 135, 180, 225, 270, 315)
TOUCH_ANGLES_REQUIRED = 4
MIN_COMBOS = 10
MIN_PHASE_SAMPLES = {"hold": 3, "rebound": 3, "settled": 1}
DECLARED_MIN_SAMPLES = 9
DEFAULT_MIN_PULL_FRACTION = 0.7
DEFAULT_PARAMETERS = Path(__file__).resolve().parent.parent / "reference" / "garment-parameters.json"
USAGE_EPILOG = ("Release evidence (G5) needs evidence/connected-interaction.json as an extra --matrix, "
                "next to the skin-guard matrices.")
KINDS = ("ribbon", "cup")
SIDES = (1, -1)
LIST_LIMIT = 8


class InputError(Exception):
    """An input the gate cannot read. Never a pass."""


# --------------------------------------------------------------------------------------- loading

def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _kind(value):
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("ribbon", "strap"):
            return "ribbon"
        if v in ("cup", "panel"):
            return "cup"
    return None


def _side(rec):
    for key in ("sideValue", "side"):
        value = rec.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value in (1, -1):
            return int(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v == "left":
                return 1
            if v == "right":
                return -1
    return None


def _phase_counts(rec):
    phases = rec.get("phases")
    if not isinstance(phases, dict):
        return None
    counts = {}
    for name in MIN_PHASE_SAMPLES:
        entry = phases.get(name)
        n = _num(entry.get("n")) if isinstance(entry, dict) else None
        if n is None:
            return None
        counts[name] = int(n)
    return counts


def _depths(rec):
    """Every recorded depth for one case: the headline and each per-phase figure. Returns
    (insideCounts, deepestMm values, complete) - complete is False when the headline is missing."""
    inside = _num(rec.get("inside"))
    if inside is None:
        inside = _num(rec.get("insideSkin"))
    deepest = _num(rec.get("deepestMm"))
    insides, deepests = [], []
    if inside is not None:
        insides.append(inside)
    if deepest is not None:
        deepests.append(deepest)
    phases = rec.get("phases")
    if isinstance(phases, dict):
        for entry in phases.values():
            if isinstance(entry, dict):
                a, b = _num(entry.get("insideSkin")), _num(entry.get("deepestMm"))
                if a is not None:
                    insides.append(a)
                if b is not None:
                    deepests.append(b)
    worst = rec.get("runWorst")
    if isinstance(worst, dict):
        deepests.extend(v for v in (_num(x) for x in worst.values()) if v is not None)
    return insides, deepests, inside is not None and deepest is not None


def _release(rec):
    after = rec.get("afterRelease")
    mismatch = _num(after.get("renderMismatch")) if isinstance(after, dict) else None
    if mismatch is None:
        mismatch = _num(rec.get("renderMismatch"))
    if isinstance(after, dict) or mismatch is not None:
        grabbed = after.get("stillGrabbed") if isinstance(after, dict) else None
        return {"renderMismatch": mismatch, "stillGrabbed": grabbed}
    return None


def _combo_pulls(rec):
    out = []
    held = rec.get("pullMmAtHold")
    for pull in rec.get("pulls") or []:
        if not isinstance(pull, dict):
            continue
        kind, side = _kind(pull.get("kind")), _side(pull)
        mm = None
        if isinstance(held, dict) and kind is not None and side is not None:
            by_kind = held.get("strap" if kind == "ribbon" else "panel")
            if isinstance(by_kind, dict):
                mm = _num(by_kind.get(str(side)))
        out.append({"kind": kind, "side": side, "pullMm": mm})
    return out


def _normalise(rec, section, src, index):
    if not isinstance(rec, dict):
        raise InputError("%s: %s[%d] is not an object" % (src, section, index))
    mode = rec.get("mode")
    if mode is None and isinstance(rec.get("group"), str) and rec["group"].startswith("tissue-"):
        mode = rec["group"][len("tissue-"):]
    declared = rec.get("input")
    if declared is None:
        declared = "mouse" if section == "pull" else None
    insides, deepests, complete = _depths(rec)
    return {
        "src": src,
        "section": section,
        "id": str(rec.get("id") or "%s[%d]" % (section, index)),
        "outfit": rec.get("outfit"),
        "kind": _kind(rec.get("kind")),
        "side": _side(rec),
        "angle": _num(rec.get("angleDeg")),
        "mode": mode,
        "input": declared,
        "trusted": rec.get("trusted") is True,
        "insides": insides,
        "deepests": deepests,
        "measured": complete,
        "pull": _num(rec.get("pullMm")),
        "combo_pulls": _combo_pulls(rec) if section == "combo" else [],
        "phases": _phase_counts(rec),
        "samples": _num(rec.get("samples")),
        "release": _release(rec),
    }


def load_records(paths):
    """Records from every matrix file. Raises InputError for a missing/unreadable/unrecognised file."""
    records = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise InputError("matrix file not found: %s" % path)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as err:
            raise InputError("matrix file %s could not be read: %s" % (path, err))
        except ValueError as err:
            raise InputError("matrix file %s is not valid JSON: %s" % (path, err))
        if not isinstance(doc, dict):
            raise InputError("matrix file %s must be a JSON object, not %s" % (path, type(doc).__name__))
        src = path.name
        found = False
        for key, section in (("cases", "pull"), ("touch", "touch"), ("tissue", "tissue"), ("combos", "combo")):
            rows = doc.get(key)
            if isinstance(rows, list):
                found = True
                records.extend(_normalise(r, section, src, i) for i, r in enumerate(rows))
        matrix = doc.get("matrix")
        if isinstance(matrix, dict):
            for group, rows in matrix.items():
                if isinstance(rows, list):
                    found = True
                    records.extend(_normalise(r, "release", src, i) for i, r in enumerate(rows))
        if not found:
            raise InputError("matrix file %s has none of cases / touch / tissue / combos / matrix" % path)
    return records


# --------------------------------------------------------------------------------------- helpers

def _fmt_side(side):
    return {1: "+1(left)", -1: "-1(right)"}.get(side, str(side))


def _fmt_case(rec):
    parts = [rec["src"], rec["id"]] if rec["section"] not in ("pull",) else [rec["src"]]
    parts += [str(rec[k]) for k in ("outfit", "kind") if rec.get(k)]
    if rec.get("side") is not None:
        parts.append("side " + _fmt_side(rec["side"]))
    if rec.get("angle") is not None:
        parts.append("%g deg" % rec["angle"])
    if rec.get("mode"):
        parts.append(str(rec["mode"]))
    return " ".join(parts)


def _listed(items):
    head = "; ".join(items[:LIST_LIMIT])
    return head if len(items) <= LIST_LIMIT else "%s; ... %d more" % (head, len(items) - LIST_LIMIT)


def _check(cid, name, verdict, summary, detail=()):
    return {"id": cid, "name": name, "verdict": verdict, "summary": summary, "detail": list(detail)}


def _probe_records(records):
    return [r for r in records if r["section"] != "release"]


# ----------------------------------------------------------------------------------------- checks

def check_g1(records):
    name = "no skin in front of the cloth"
    probed = _probe_records(records)
    if not probed:
        return _check("G1", name, FAIL, "no cases: an empty matrix proves nothing")
    offenders, unmeasured = [], []
    for rec in probed:
        if not rec["measured"]:
            unmeasured.append(rec)
        worst_inside = max(rec["insides"], default=0)
        worst_deepest = max(rec["deepests"], default=0)
        if worst_inside > 0 or worst_deepest > MAX_DEEPEST_MM:
            offenders.append("%s: inside=%g deepestMm=%g" % (_fmt_case(rec), worst_inside, worst_deepest))
    if offenders:
        return _check("G1", name, FAIL,
                      "%d of %d cases have skin in front of the cloth (inside > 0 or deepestMm > %g)"
                      % (len(offenders), len(probed), MAX_DEEPEST_MM), offenders[:LIST_LIMIT])
    if unmeasured:
        return _check("G1", name, UNMEASURED,
                      "%d of %d cases record no inside/insideSkin and deepestMm" % (len(unmeasured), len(probed)),
                      [_fmt_case(r) for r in unmeasured[:LIST_LIMIT]])
    return _check("G1", name, PASS,
                  "%d cases, none inside the skin, deepest %g mm (limit %g)"
                  % (len(probed), max((max(r["deepests"], default=0) for r in probed), default=0), MAX_DEEPEST_MM))


def check_g2(records):
    name = "coverage is complete"
    probed = _probe_records(records)
    missing = []
    pulls = [r for r in probed if r["section"] == "pull"]
    mouse = [r for r in pulls if r["input"] == "mouse" and r["trusted"]]

    def angles_for(kind, side, outfit=None):
        return {int(r["angle"]) for r in mouse
                if r["kind"] == kind and r["side"] == side and r["angle"] is not None
                and (outfit is None or r["outfit"] == outfit)}

    for kind in KINDS:
        for side in SIDES:
            have = angles_for(kind, side)
            gaps = [a for a in REQUIRED_ANGLES if a not in have]
            if gaps:
                missing.append("trusted mouse pull: %s side %s angles %s" % (kind, _fmt_side(side), gaps))

    for kind in KINDS:
        full = {r["outfit"] for r in mouse
                if r["kind"] == kind and r["side"] == 1 and r["outfit"] is not None
                and set(REQUIRED_ANGLES) <= angles_for(kind, 1, r["outfit"])}
        if len(full) < 2:
            missing.append("left %s must be covered at all %d angles in 2 outfits (have %s)"
                           % (kind, len(REQUIRED_ANGLES), sorted(full) or "none"))

    outfits = sorted({r["outfit"] for r in pulls if r["outfit"] is not None})
    touch = [r for r in probed if r["section"] == "touch" and r["input"] == "touch" and r["trusted"]]
    for outfit in outfits:
        for kind in KINDS:
            have = {int(r["angle"]) for r in touch
                    if r["outfit"] == outfit and r["kind"] == kind and r["angle"] is not None}
            if len(have) < TOUCH_ANGLES_REQUIRED:
                missing.append("trusted touch: %s %s has %d angles, need %d"
                               % (outfit, kind, len(have), TOUCH_ANGLES_REQUIRED))
    if not outfits:
        missing.append("trusted touch: no outfit recorded in the pull matrix")

    tissue = [r for r in probed if r["section"] == "tissue" and r["input"] == "mouse" and r["trusted"]
              and r["kind"] == "cup"]
    for mode in ("grab", "squeeze"):
        for side in SIDES:
            if not any(r["mode"] == mode and r["side"] == side for r in tissue):
                missing.append("trusted mouse tissue %s on cup side %s" % (mode, _fmt_side(side)))

    combos = [r for r in probed if r["section"] == "combo"]
    if len(combos) < MIN_COMBOS:
        missing.append("combos: %d recorded, need >= %d" % (len(combos), MIN_COMBOS))

    if missing:
        return _check("G2", name, FAIL, "%d required cells missing or untrusted (an unmeasured cell is not a pass)"
                      % len(missing), missing)
    two_handed = sum(1 for r in combos if len(r["combo_pulls"]) >= 2)
    return _check("G2", name, PASS,
                  "%d mouse pulls, %d touch, %d tissue, %d combos; every required cell present"
                  % (len(mouse), len(touch), len(tissue), len(combos)),
                  ["%d of %d combos are two-handed (>= 2 pulls)" % (two_handed, len(combos))])


def check_g3(records, sampling_declared=None):
    name = "hold / rebound / settled sampled"
    probed = _probe_records(records)
    if not probed:
        return _check("G3", name, UNMEASURED, "no cases")
    short, absent = [], []
    for rec in probed:
        counts = rec["phases"]
        if counts is None:
            absent.append(rec)
            continue
        bad = ["%s %d < %d" % (p, counts[p], need) for p, need in MIN_PHASE_SAMPLES.items() if counts[p] < need]
        if bad:
            short.append("%s: %s" % (_fmt_case(rec), ", ".join(bad)))
    declared = sampling_declared.strip() if isinstance(sampling_declared, str) and sampling_declared.strip() else None
    if declared:
        for rec in absent:
            if rec["samples"] is not None and rec["samples"] < DECLARED_MIN_SAMPLES:
                short.append("%s: samples %g < %d (declared sampling needs >= %d per case)"
                             % (_fmt_case(rec), rec["samples"], DECLARED_MIN_SAMPLES, DECLARED_MIN_SAMPLES))
    if short:
        return _check("G3", name, FAIL, "%d cases under-sampled" % len(short), short[:LIST_LIMIT])
    if absent:
        if declared:
            unknown = [r for r in absent if r["samples"] is None]
            if not unknown:
                return _check("G3", name, PASS,
                              "%d cases: %d record per-phase counts (>= %s), %d record only samples >= %d"
                              % (len(probed), len(probed) - len(absent),
                                 "/".join("%d %s" % (v, k) for k, v in MIN_PHASE_SAMPLES.items()),
                                 len(absent), DECLARED_MIN_SAMPLES),
                              ["declared, not recorded: %s" % declared])
            return _check("G3", name, UNMEASURED,
                          "%d cases record neither per-phase counts nor a total sample count" % len(unknown),
                          [_fmt_case(r) for r in unknown[:LIST_LIMIT]])
        by = {}
        for rec in absent:
            by.setdefault((rec["src"], rec["section"]), 0)
            by[(rec["src"], rec["section"])] += 1
        detail = ["%s [%s]: %d cases record no phases.{hold,rebound,settled}.n (only a total sample count)"
                  % (s, sec, n) for (s, sec), n in sorted(by.items())]
        detail.append("pass --sampling-declared \"<how phases were sampled>\" to accept a declared scheme "
                      "(needs samples >= %d per case)" % DECLARED_MIN_SAMPLES)
        return _check("G3", name, UNMEASURED,
                      "not recorded for %d of %d cases (%d record per-phase counts and meet the minimum)"
                      % (len(absent), len(probed), len(probed) - len(absent)), detail)
    return _check("G3", name, PASS, "%d cases, each >= %s samples"
                  % (len(probed), "/".join("%d %s" % (v, k) for k, v in MIN_PHASE_SAMPLES.items())))


def load_limits(parameters, fallback_mm):
    """Pull limits in mm per kind: from the parameters file (constants.STRAP / PANEL .maxPull, metres;
    also found under constants.garment), else the fallback flags. A kind with no limit maps to None."""
    explicit = parameters is not None
    path = Path(parameters).expanduser() if explicit else DEFAULT_PARAMETERS
    limits = {"ribbon": None, "cup": None}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as err:
            if explicit:
                raise InputError("parameters file %s could not be read: %s" % (path, err))
            doc = None
        consts = doc.get("constants") if isinstance(doc, dict) else None
        if isinstance(consts, dict):
            garment = consts.get("garment") if isinstance(consts.get("garment"), dict) else {}
            for kind, key in (("ribbon", "STRAP"), ("cup", "PANEL")):
                for scope in (consts, garment):
                    entry = scope.get(key)
                    value = _num(entry.get("maxPull")) if isinstance(entry, dict) else None
                    if value is not None and value > 0:
                        limits[kind] = value * 1000.0
                        break
    elif explicit:
        raise InputError("parameters file not found: %s" % path)
    for kind in KINDS:
        if limits[kind] is None and fallback_mm.get(kind) is not None and fallback_mm[kind] > 0:
            limits[kind] = float(fallback_mm[kind])
    return limits


def check_g4(records, min_pull=None, limits_mm=None, fraction=DEFAULT_MIN_PULL_FRACTION):
    name = "pulls reached the limit"
    min_pull = min_pull or {}
    limits_mm = limits_mm or {}
    need, basis = {}, []
    for kind in KINDS:
        if min_pull.get(kind) is not None:
            need[kind] = float(min_pull[kind])
            basis.append("%s >= %g mm (absolute)" % (kind, need[kind]))
        elif limits_mm.get(kind) is not None:
            need[kind] = fraction * limits_mm[kind]
            basis.append("%s >= %g x %g mm = %.2f mm" % (kind, fraction, limits_mm[kind], need[kind]))
        else:
            need[kind] = None
            basis.append("%s: no limit known (pass --parameters, --%s-limit-mm or --min-%s-pull-mm)"
                         % (kind, kind, kind))
    note = ("direction-limited pulls (225/315 degrees) stop short of the nominal limit because the pull "
            "stretches with resistance, hence a fraction of the limit rather than the limit")
    pulled, unmeasured, low = 0, [], []

    def judge(kind, mm, label):
        nonlocal pulled
        if kind is None or mm is None:
            unmeasured.append("%s: pull distance not recorded" % label)
        elif need[kind] is None:
            unmeasured.append("%s: no limit known for %s" % (label, kind))
        else:
            pulled += 1
            if mm < need[kind]:
                low.append("%s: pull %g mm < %g" % (label, mm, need[kind]))

    for rec in _probe_records(records):
        if rec["section"] in ("pull", "touch"):
            if rec["kind"] is None:
                unmeasured.append("%s: kind not recorded" % _fmt_case(rec))
            elif rec["pull"] is None:
                unmeasured.append("%s: pullMm not recorded" % _fmt_case(rec))
            else:
                judge(rec["kind"], rec["pull"], _fmt_case(rec))
        elif rec["section"] == "combo":
            for pull in rec["combo_pulls"]:
                judge(pull["kind"], pull["pullMm"], "%s %s %s" % (
                    _fmt_case(rec), pull["kind"], _fmt_side(pull["side"])))
    detail_tail = ["required: " + "; ".join(basis), note]
    if low:
        return _check("G4", name, FAIL,
                      "%d of %d garment pulls stayed under the limit: too gentle, or blocked by the body, "
                      "to test the guarantee" % (len(low), pulled + len(unmeasured)),
                      low[:LIST_LIMIT * 2] + detail_tail)
    if unmeasured:
        return _check("G4", name, UNMEASURED, "%d pulls cannot be judged (no distance or no limit)" % len(unmeasured),
                      unmeasured[:LIST_LIMIT] + detail_tail)
    if pulled == 0:
        return _check("G4", name, UNMEASURED, "no garment pull recorded", detail_tail)
    return _check("G4", name, PASS, "%d garment pulls reached their required fraction of the limit" % pulled,
                  detail_tail)


def check_g5(records):
    name = "release restores exactly"
    rel = [r for r in records if r["release"] is not None]
    if not rel:
        return _check("G5", name, UNMEASURED,
                      "no case records afterRelease / renderMismatch (pass the connected-interaction evidence)")
    bad, unmeasured = [], []
    for rec in rel:
        mismatch, grabbed = rec["release"]["renderMismatch"], rec["release"]["stillGrabbed"]
        if mismatch is None:
            unmeasured.append("%s: afterRelease.renderMismatch not recorded" % _fmt_case(rec))
        elif mismatch != 0 or grabbed is True:
            bad.append("%s: renderMismatch=%g stillGrabbed=%s" % (_fmt_case(rec), mismatch, grabbed))
    if bad:
        return _check("G5", name, FAIL, "%d of %d released cases did not restore exactly" % (len(bad), len(rel)),
                      bad[:LIST_LIMIT])
    cells = {(r["kind"], r["side"]) for r in rel if r["kind"] is not None}
    gaps = ["%s %s" % (k, _fmt_side(s)) for k in KINDS for s in SIDES if (k, s) not in cells]
    if unmeasured or gaps:
        return _check("G5", name, UNMEASURED,
                      "release not recorded for every ribbon/cup x side",
                      unmeasured[:LIST_LIMIT] + ["no release record for " + g for g in gaps])
    return _check("G5", name, PASS, "%d released cases, renderMismatch 0 and not grabbed, all four ribbon/cup x side"
                  % len(rel))


def run_checks(records, min_pull=None, limits_mm=None, fraction=DEFAULT_MIN_PULL_FRACTION, sampling_declared=None):
    return [check_g1(records), check_g2(records), check_g3(records, sampling_declared),
            check_g4(records, min_pull, limits_mm, fraction), check_g5(records)]


# ------------------------------------------------------------------------------------------- CLI

def _status(checks):
    verdicts = [c["verdict"] for c in checks]
    if FAIL in verdicts:
        return "fail", 1
    if all(v == PASS for v in verdicts):
        return "pass", 0
    return "error", 2


def _emit_json(status, reasons, checks, files):
    print(json.dumps({
        "kind": "img2.gate-verdict", "version": 1, "gate": GATE_ID, "plugin": PLUGIN_ID,
        "status": status, "reasons": reasons,
        "evidence": {"files": files, "checks": checks, "ok": status == "pass"},
    }))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gate_garment.py", description=__doc__.split("\n\n")[0],
                                     epilog=USAGE_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", action="append", required=True, metavar="FILE",
                        help="matrix evidence JSON (repeatable); release evidence also needs "
                             "evidence/connected-interaction.json as an extra --matrix (G5)")
    parser.add_argument("--json", action="store_true", help="print one img2.gate-verdict JSON envelope")
    parser.add_argument("--parameters", metavar="FILE", default=None,
                        help="garment-parameters.json holding the pull limits (default: %s)" % DEFAULT_PARAMETERS)
    parser.add_argument("--min-pull-fraction", type=float, default=DEFAULT_MIN_PULL_FRACTION,
                        help="G4: each pull must reach this fraction of its limit (default %(default)s)")
    parser.add_argument("--ribbon-limit-mm", type=float, default=None,
                        help="G4 fallback ribbon limit when the parameters file has none")
    parser.add_argument("--cup-limit-mm", type=float, default=None,
                        help="G4 fallback cup limit when the parameters file has none")
    parser.add_argument("--min-ribbon-pull-mm", type=float, default=None,
                        help="G4 optional absolute minimum for ribbon pulls (overrides the fraction)")
    parser.add_argument("--min-cup-pull-mm", type=float, default=None,
                        help="G4 optional absolute minimum for cup pulls (overrides the fraction)")
    parser.add_argument("--sampling-declared", metavar="TEXT", default=None,
                        help="G3: how phases were sampled when cases record only a total `samples`; "
                             "needs samples >= %d in every such case" % DECLARED_MIN_SAMPLES)
    args = parser.parse_args(argv)
    min_pull = {"ribbon": args.min_ribbon_pull_mm, "cup": args.min_cup_pull_mm}
    try:
        limits = load_limits(args.parameters, {"ribbon": args.ribbon_limit_mm, "cup": args.cup_limit_mm})
        records = load_records(args.matrix)
    except InputError as err:
        if args.json:
            _emit_json("error", [str(err)], [], args.matrix)
        else:
            print("error: %s" % err)
        return 2
    checks = run_checks(records, min_pull, limits, args.min_pull_fraction, args.sampling_declared)
    status, code = _status(checks)
    reasons = ["%s %s: %s" % (c["id"], c["verdict"], c["summary"]) for c in checks if c["verdict"] != PASS]
    if args.json:
        _emit_json(status, reasons, checks, args.matrix)
        return code
    for c in checks:
        print("%s %-10s %s: %s" % (c["id"], c["verdict"], c["name"], c["summary"]))
        for line in c["detail"]:
            print("    - %s" % line)
    print("garment gate: %s (%d records from %d file(s))" % (status if status != "error" else "NOT PASSED (unmeasured)",
                                                              len(records), len(args.matrix)))
    return code


if __name__ == "__main__":
    sys.exit(main())
