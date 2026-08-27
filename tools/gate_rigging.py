import os, sys
root = os.environ.get("IMG2_HOME")
if root: sys.path.insert(0, os.path.join(root, "harness"))
else:
    try: import _img2_local; sys.path.insert(0, _img2_local.CORE)
    except ImportError: sys.exit("img2: core not linked - run `img2 sync`")
from img2_core import require_core_api
require_core_api(1)

import argparse
import json
import math

from img2_core.paths import resolve_workspace

GATE_ID = "rigging"
PLUGIN_ID = "character"
PAYLOAD_NAME = "rig-gate-payload.json"

# rig_gate_core.py is a sibling of this file. It imports its own siblings flat (anim_action_design,
# anim_clip_features, rig_glb_reference, rig_mesh_parity, rig_skin_conditioning), so this directory has to be
# importable before it is imported.
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.append(TOOLS_DIR)

# rig_gate_core reports three statuses; the verdict envelope allows pass|fail|error. The third
# status survives in `reasons` and in `evidence`, and NEVER in `status`: gate_runner.parse_verdict
# rejects any other string, throws the envelope away, and every reason below is lost with it.
STATUS_FAIL = "fail"
STATUS_UNEVALUATED = "unevaluated"


def emit(status, reasons, evidence):
    print(json.dumps({
        "kind": "img2.gate-verdict",
        "version": 1,
        "gate": GATE_ID,
        "plugin": PLUGIN_ID,
        "status": status,
        "reasons": reasons,
        "evidence": evidence,
    }))


def jsonable(value):
    """Evidence carries `measured` payloads the twelve checks build, which are loosely typed by
    design. Anything json.dumps could not write strictly - a non-finite float, a tuple key, an
    object - becomes a string rather than an unparseable envelope."""
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {(k if isinstance(k, str) else str(k)): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return str(value)


def describe(result, spec):
    """One readable line for a check that is not a pass."""
    reason = (result.get("reason") or "").strip()
    label = "%s %s" % (result.get("id"), result.get("gate") or result.get("name") or "")
    if result.get("status") == STATUS_UNEVALUATED:
        line = "%s: not evaluated - input %r was absent or unusable" % (
            label.strip(), spec.input_key if spec is not None else "input")
    else:
        line = "%s: failed" % label.strip()
    if reason:
        line += ": %s" % reason
    criterion = result.get("criterion") or (spec.criterion if spec is not None else "")
    if criterion:
        line += " (criterion: %s)" % criterion
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gate_rigging.py")
    parser.add_argument("--workspace", default=None)
    args = parser.parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
    except ValueError as err:
        emit("error", [str(err)], {})
        return 2
    payload_path = workspace / ".img2" / "artifacts" / PLUGIN_ID / PAYLOAD_NAME
    evidence = {"payload": str(payload_path), "ok": False, "gates": [], "failed": [], "unevaluated": []}
    if not payload_path.is_file():
        emit("error", ["rig gate payload not found at %s" % payload_path], evidence)
        return 2
    try:
        raw = payload_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        emit("error", ["rig gate payload at %s could not be read: %s" % (payload_path, err)], evidence)
        return 2
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as err:
        emit("error", ["rig gate payload at %s is not valid JSON: %s" % (payload_path, err)], evidence)
        return 2
    if not isinstance(payload, dict):
        emit("error", ["rig gate payload at %s must be a JSON object, not %s"
                       % (payload_path, type(payload).__name__)], evidence)
        return 2
    try:
        import rig_gate_core
    except Exception as err:
        emit("error", ["the twelve-check rig gate core could not be imported from %s: %s"
                       % (TOOLS_DIR, err)], evidence)
        return 2
    try:
        report = rig_gate_core.run_gates(payload)
        summary = report.summary()
        rows = [jsonable(row) for row in summary.get("rows", [])]
    except Exception as err:
        emit("error", ["the twelve-check rig gate could not evaluate %s: %s: %s"
                       % (payload_path, type(err).__name__, err)], evidence)
        return 2

    specs = getattr(rig_gate_core, "GATE_SPEC_BY_ID", {})
    failed = [row["id"] for row in rows if row.get("status") == STATUS_FAIL]
    unevaluated = [row["id"] for row in rows if row.get("status") == STATUS_UNEVALUATED]
    evidence = {
        "payload": str(payload_path),
        # Every check, always: this gate is one row precisely so that a single failure cannot
        # turn the other eleven answers into "skipped".
        "gates": rows,
        "failed": failed,
        "unevaluated": unevaluated,
        "ok": bool(summary.get("ok")) and not failed and not unevaluated,
        "counts": jsonable(summary.get("counts", {})),
        "figureHeight": jsonable(summary.get("figureHeight")),
        "sweepCoverage": jsonable(summary.get("sweepCoverage")),
        "note": summary.get("note"),
    }

    reasons = [describe(row, specs.get(row.get("id"))) for row in rows
               if row.get("status") in (STATUS_FAIL, STATUS_UNEVALUATED)]
    if failed:
        header = "%d of %d rig checks failed" % (len(failed), len(rows))
        if unevaluated:
            header += " and %d could not be evaluated" % len(unevaluated)
        emit("fail", [header] + reasons, evidence)
        return 1
    if unevaluated:
        # No check failed, but "we did not check" is not "we checked and it was fine". The
        # envelope has no third status, so this is an error: the gate could not be evaluated.
        emit("error", ["%d of %d rig checks could not be evaluated; an absent input is never a pass"
                       % (len(unevaluated), len(rows))] + reasons, evidence)
        return 2
    emit("pass", [], evidence)
    return 0


if __name__ == "__main__":
    sys.exit(main())
