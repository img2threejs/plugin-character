#!/usr/bin/env python3
"""The evidence collection this plugin contributes, and the corpus it carries to serve it.

A contributed collection's paths resolve against the PLUGIN directory, never the project's
(`spec_search.py:_installed_collection_profiles`). So a plugin cannot reference the base's
`docs/specs/vocabulary/core_3d.jsonl`: it carries its own copy or it loses those records.

That matters here because `specCollection` REPLACES the collection searched, it does not add one
(`new_pre_spec_assessment.py:_choose_collection` returns a single name). Before this change the
character profile declared no collection and searched `core_3d`. Declaring `character` without
carrying core_3d's records would therefore have made the character run search LESS than it did —
a silent quality loss, invisible from the checklist. The copies are pinned byte-identical below,
and `plugin-cs2` carries the same two files for the same reason.

What the collection adds over `core_3d` is `grimoire/character/`, which was never in any collection:
`core_3d` declares no source roots at all, so those pages were readable only by the step that names
them. Searchable is new; losing the records would have been a regression.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "spec_search_profile.json"
BASE_RELATIVE_SEARCH = Path("forge/_shared/spec_search.py")
BASE_VOCABULARY = Path("docs/specs/vocabulary")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _base_checkout import on_base_path, require_base  # noqa: E402

# Collection names the BASE declares. Claiming one is refused by the merge, not silently preferred.
BASE_COLLECTIONS = ("core_3d",)


def _require_base(what: str) -> Path:
    return require_base(BASE_RELATIVE_SEARCH, what, "this run did NOT check it.")


class ProfileShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(PROFILE.read_text(encoding="utf-8"))
        cls.collections = cls.raw["collections"]

    def test_it_declares_the_one_collection_the_domain_names(self) -> None:
        self.assertEqual(sorted(self.collections), ["character"])

    def test_it_claims_no_collection_the_base_already_defines(self) -> None:
        # `load_profiles` raises "already defined; refusing to override it" rather than picking one,
        # so this would break every run, not just a character one.
        self.assertEqual(set(self.collections) & set(BASE_COLLECTIONS), set())

    def test_every_declared_path_exists_inside_this_plugin(self) -> None:
        entry = self.collections["character"]
        for key in ("source_roots", "optional_source_roots", "distilled_records"):
            for relative in entry[key]:
                self.assertTrue((ROOT / relative).exists(), f"{key}: {relative} does not exist")
        self.assertTrue((ROOT / entry["documentation"]).is_file())

    def test_the_grimoire_pages_are_what_this_plugin_actually_contributes(self) -> None:
        pages = sorted(p.name for p in (ROOT / "grimoire" / "character").glob("*.md"))
        self.assertEqual(pages, ["head_construction.md", "likeness_maximization.md",
                                 "reconstruction.md", "structure_decomposition.md"])

    def test_the_cache_path_is_scoped_to_this_collection(self) -> None:
        # A cache shared with core_3d would serve a character index to a generic run.
        self.assertEqual(self.collections["character"]["cache"], ".cache/spec-search/character.json")


class CorpusMatchesTheBase(unittest.TestCase):
    """The carried records are the base's, unmodified — the only thing that makes them a copy."""

    def test_the_distilled_records_are_byte_identical_to_the_base_s(self) -> None:
        base = _require_base("the corpus copy pin")
        entry = json.loads(PROFILE.read_text(encoding="utf-8"))["collections"]["character"]
        checked = 0
        for relative in [*entry["distilled_records"], entry["documentation"]]:
            name = Path(relative).name
            theirs = base / BASE_VOCABULARY / name
            if not theirs.is_file():
                continue   # a record this plugin authored itself has no base counterpart
            self.assertEqual((ROOT / relative).read_bytes(), theirs.read_bytes(),
                             f"{name} has drifted from {theirs}")
            checked += 1
        self.assertEqual(checked, 3, "expected all three carried files to have a base counterpart")


class TheBaseCanReadIt(unittest.TestCase):
    """Parsed by the base's real loader, through the registry, as an installed plugin would be."""

    def test_load_profiles_resolves_the_collection_against_this_plugin(self) -> None:
        base = _require_base("the profile-loading pin")
        import tempfile  # noqa: PLC0415
        on_base_path(base, "forge", "forge/_shared")
        import spec_search  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "plugins").mkdir()
            (Path(home) / "plugins" / "character").symlink_to(ROOT, target_is_directory=True)
            (Path(home) / "plugins.json").write_text(json.dumps({"plugins": [{"id": "character"}]}))
            previous = os.environ.get("IMG2_HOME")
            os.environ["IMG2_HOME"] = home
            try:
                profiles = spec_search.load_profiles()
                # Resolved INSIDE the block: the symlink is what points back here, and it dies
                # with the temporary directory. Outside, `resolve()` is non-strict and would hand
                # back the dead path unfollowed — which is how this assertion first "failed".
                character_root = Path(profiles["character"]["content_root"]).resolve()
            finally:
                if previous is None:
                    os.environ.pop("IMG2_HOME", None)
                else:
                    os.environ["IMG2_HOME"] = previous

        self.assertIn("character", profiles)
        self.assertIn("core_3d", profiles, "contributing a collection must not displace the base's")
        self.assertEqual(character_root, ROOT.resolve())
        self.assertEqual(profiles["core_3d"]["content_root"], "")


if __name__ == "__main__":
    unittest.main()
