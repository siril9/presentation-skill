from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sync_plugin_snapshot, validate_distribution


class PluginSnapshotTests(unittest.TestCase):
    def test_historical_host_builders_are_excluded_from_both_distributions(self) -> None:
        builders = {"build_native_vs_latest_random_topic_decks.py", "build_release_showcase.py"}
        manifest = json.loads((validate_distribution.ROOT / "package.json").read_text())
        for name in builders:
            self.assertIn(f"!scripts/{name}", manifest["files"])
        self.assertTrue(builders <= sync_plugin_snapshot._ignore("scripts", sorted(builders)))

    def test_distribution_detects_host_scripts_without_banning_source_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "references").mkdir()
            for name, content in {
                "scripts/mac.py": 'NODE = "/Users/maintainer/runtime/node"',
                "scripts/linux.js": 'const node = "/home/maintainer/runtime/node";',
                "scripts/windows.py": 'NODE = r"C:\\Users\\maintainer\\runtime\\node"',
                "scripts/portable.py": 'NODE = shutil.which("node")',
                "references/history.md": "Proof once ran at /Users/maintainer/runtime/node",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            paths = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]
            issues = validate_distribution._surface_issues(root, paths)
            self.assertEqual(issues["host_specific_scripts"],
                             ["scripts/linux.js", "scripts/mac.py", "scripts/windows.py"])
            self.assertEqual(issues["development"], [])
            self.assertEqual(issues["private"], [])

    def test_distribution_detects_private_material(self) -> None:
        paths = ["references/.env.local", "references/private.key", "node_modules/module/package.json"]
        issues = validate_distribution._surface_issues(Path("unused"), paths)
        self.assertEqual(issues["private"], sorted(paths))

    def test_check_detects_drift_without_writing_actual_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "expected"
            actual = root / "actual"
            expected.mkdir()
            actual.mkdir()
            (expected / "SKILL.md").write_text("current\n", encoding="utf-8")
            (actual / "SKILL.md").write_text("stale\n", encoding="utf-8")
            before = (actual / "SKILL.md").read_bytes()

            with (
                patch.object(sync_plugin_snapshot, "PLUGIN_SKILL_ROOT", actual),
                patch.object(sync_plugin_snapshot, "PLUGIN_ASSETS", root / "assets"),
                patch.object(sync_plugin_snapshot, "SCREENSHOTS", {}),
                patch.object(sync_plugin_snapshot, "_sync_skill", side_effect=lambda target: _copy_expected(expected, target)),
            ):
                self.assertEqual(sync_plugin_snapshot._check_snapshot(), 1)

            self.assertEqual((actual / "SKILL.md").read_bytes(), before)


def _copy_expected(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())


if __name__ == "__main__":
    unittest.main()
