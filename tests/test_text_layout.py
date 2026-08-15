import unittest

from context_badge.text_layout import fit_text


class FixedWidthFont:
    def measure(self, text: str) -> int:
        return len(text) * 10


class TextLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.font = FixedWidthFont()

    def test_text_that_fits_is_unchanged(self) -> None:
        self.assertEqual(fit_text("hello", self.font, 50, 1), "hello")

    def test_long_single_line_is_ellipsized(self) -> None:
        rendered = fit_text("abcdefghij", self.font, 50, 1)
        self.assertEqual(rendered, "abcd…")

    def test_multiple_lines_stay_within_limit(self) -> None:
        rendered = fit_text("abcdefghijkl", self.font, 40, 2)
        self.assertEqual(len(rendered.splitlines()), 2)
        self.assertTrue(rendered.endswith("…"))

    def test_invalid_region_is_empty(self) -> None:
        self.assertEqual(fit_text("hello", self.font, 0, 1), "")


if __name__ == "__main__":
    unittest.main()
