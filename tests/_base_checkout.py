"""Finding the base checkout, once, for the few tests whose property genuinely spans both repos.

Most of this suite runs from a bare clone. A handful of properties cannot: "the derived rig passes
the base's gate", "the artifact merges into the frozen spec", "the registry accepts this
declaration". Those need an `img2threejs` checkout, and when there is none they must SKIP WITH A
REASON -- never pass quietly, which would report a two-repo agreement that was never checked.

This module existed as three near-copies before a cleanup review found them. They had already
drifted: three different return shapes, three different message wordings, and a change to the
env-var name or the require-base rule would have needed three edits with nothing to catch the one
that got missed.

    IMG2THREEJS_BASE          where the base checkout is (default: the sibling `img2threejs/`)
    IMG2THREEJS_REQUIRE_BASE  set to 1 to turn every skip below into a hard failure, for a CI lane
                              that must not silently stop checking the cross-repo half
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT.parent / "img2threejs"


def base_root(marker: str | Path) -> Path | None:
    """The base checkout if it is there and carries `marker`, else None."""
    configured = os.environ.get("IMG2THREEJS_BASE")
    root = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
    return root if (root / marker).is_file() else None


def require_base(marker: str | Path, what: str, still_checked: str) -> Path:
    """The base checkout, or a skip whose reason says what this run did NOT verify.

    `what` names the property that needs the checkout; `still_checked` says what remains pinned
    without it, so a reader of the skip can tell how much coverage the run actually lost.
    """
    root = base_root(marker)
    if root is not None:
        return root
    configured = os.environ.get("IMG2THREEJS_BASE")
    where = "from IMG2THREEJS_BASE" if configured else "the default; IMG2THREEJS_BASE is unset"
    attempted = Path(configured).expanduser().resolve() if configured else DEFAULT_BASE
    message = (f"{what} needs the base checkout: set IMG2THREEJS_BASE to an img2threejs checkout "
               f"containing {marker}. Looked in {attempted} ({where}).")
    if os.environ.get("IMG2THREEJS_REQUIRE_BASE") == "1":
        raise RuntimeError(message + " IMG2THREEJS_REQUIRE_BASE=1 forbids skipping this check.")
    raise unittest.SkipTest(f"{message} Skipping: {still_checked}")


def on_base_path(root: Path, *subdirectories: str) -> None:
    """Put base packages on sys.path so a cross-repo test can import the real thing.

    Deliberately NOT done at module import: an import of base code that happened whether or not the
    test ran would make the plugin depend on the base, which PLUGIN_CONTRACT.md section 8 forbids
    and `img2 doctor` fails on.
    """
    sys.path[:0] = [str(root / part) for part in subdirectories]
