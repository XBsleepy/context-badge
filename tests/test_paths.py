import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from context_badge.paths import config_path


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


if __name__ == "__main__":
    unittest.main()
