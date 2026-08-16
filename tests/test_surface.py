import unittest

from context_badge.surface import surface_label


class SurfaceTests(unittest.TestCase):
    def test_chrome_tab_strips_browser_suffix(self) -> None:
        self.assertEqual(
            surface_label("chrome.exe", "Dwell tracking · GitHub - Google Chrome"),
            "Dwell tracking · GitHub",
        )

    def test_edge_profile_is_removed(self) -> None:
        self.assertEqual(
            surface_label(
                "msedge.exe",
                "Python documentation - Profile 1 - Microsoft Edge",
            ),
            "Python documentation",
        )

    def test_vscode_strips_editor_suffix(self) -> None:
        self.assertEqual(
            surface_label("code.exe", "app.py - context-badge - Visual Studio Code"),
            "app.py - context-badge",
        )

    def test_plain_window_title_is_unchanged(self) -> None:
        self.assertEqual(
            surface_label("notepad.exe", "notes.txt - Notepad"),
            "notes.txt",
        )


if __name__ == "__main__":
    unittest.main()
