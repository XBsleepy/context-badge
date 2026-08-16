import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from context_badge.paths import config_path, dwell_active_path, dwell_log_path


class PathTests(unittest.TestCase):
    def test_source_config_is_repo_json(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            path = config_path()
        expected = Path(__file__).resolve().parents[1] / ".context-badge.json"
        self.assertEqual(path, expected)

    def test_frozen_config_uses_localappdata(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            with patch.dict(
                os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}
            ):
                path = config_path()
        self.assertEqual(
            path,
            Path(r"C:\Users\Test\AppData\Local")
            / "Context Badge"
            / "preferences.json",
        )

    def test_source_dwell_files_sit_beside_the_repo(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            log_path = dwell_log_path()
            active_path = dwell_active_path()
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(log_path, root / ".context-badge-dwell.jsonl")
        self.assertEqual(active_path, root / ".context-badge-dwell-active.json")

    def test_frozen_dwell_files_use_localappdata(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            with patch.dict(
                os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}
            ):
                log_path = dwell_log_path()
                active_path = dwell_active_path()
        base = Path(r"C:\Users\Test\AppData\Local") / "Context Badge"
        self.assertEqual(log_path, base / "dwell.jsonl")
        self.assertEqual(active_path, base / "dwell-active.json")


if __name__ == "__main__":
    unittest.main()
