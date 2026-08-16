import unittest

from context_badge.surface import (
    compact_url,
    resolve_context,
    strip_invisibles,
    surface_label,
)
from context_badge.uia import UiaSnapshot


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

    def test_edge_strips_other_pages_profile_and_zwsp(self) -> None:
        raw = (
            "飞书云文档 和另外 11 个页面 - 个人 - Microsoft\u200b Edge"
        )
        self.assertEqual(surface_label("msedge.exe", raw), "飞书云文档")

    def test_edge_strips_notification_prefix(self) -> None:
        raw = "(99+ 封私信 / 9 条消息) 知乎问答 和另外 8 个页面 - 个人 - Microsoft Edge"
        self.assertEqual(surface_label("msedge.exe", raw), "知乎问答")

    def test_cursor_strips_app_suffix(self) -> None:
        self.assertEqual(
            surface_label("Cursor.exe", "AGENTS.md - context-badge - Cursor"),
            "AGENTS.md - context-badge",
        )

    def test_explorer_strips_localized_suffix(self) -> None:
        self.assertEqual(
            surface_label("explorer.exe", "context-badge - 文件资源管理器"),
            "context-badge",
        )

    def test_invisibles_are_dropped(self) -> None:
        self.assertEqual(strip_invisibles("A\u200bB\u200cC"), "ABC")

    def test_compact_url_keeps_host_and_path(self) -> None:
        self.assertEqual(
            compact_url(
                "https://meetchances.feishu.cn/wiki/WgDywGZznig8YDkLNu5clIYknoc?from=nav"
            ),
            "meetchances.feishu.cn/wiki/WgDywGZznig8YDkLNu5clIYknoc",
        )

    def test_compact_url_ignores_vscode_scheme(self) -> None:
        self.assertEqual(compact_url("vscode-file://vscode-app/out/vs"), "")

    def test_editor_list_uses_workspace_dwell_keeps_file(self) -> None:
        resolved = resolve_context(
            "Cursor.exe", "AGENTS.md - context-badge - Cursor"
        )
        self.assertEqual(resolved.display, "AGENTS.md · context-badge")
        self.assertEqual(resolved.dwell_surface, "AGENTS.md - context-badge")
        self.assertEqual(resolved.list_surface, "context-badge")

    def test_browser_uses_tab_and_url_from_uia(self) -> None:
        raw = "飞书云文档 和另外 11 个页面 - 个人 - Microsoft Edge"
        resolved = resolve_context(
            "msedge.exe",
            raw,
            UiaSnapshot(
                tab_name="Benchmark 测试题 - 飞书云文档 - 内存使用率 - 617 MB",
                url="https://meetchances.feishu.cn/wiki/abc",
            ),
        )
        self.assertEqual(resolved.display, "Benchmark 测试题 - 飞书云文档")
        self.assertEqual(resolved.dwell_surface, "Benchmark 测试题 - 飞书云文档")
        self.assertEqual(resolved.list_surface, "meetchances.feishu.cn/wiki/abc")

    def test_cursor_agents_uses_chat_title(self) -> None:
        resolved = resolve_context(
            "Cursor.exe",
            "Cursor Agents",
            UiaSnapshot(chat_title="Chat title. Dynamic font size adjustment"),
        )
        self.assertEqual(resolved.display, "Dynamic font size adjustment")
        self.assertEqual(resolved.list_surface, "Dynamic font size adjustment")


if __name__ == "__main__":
    unittest.main()
