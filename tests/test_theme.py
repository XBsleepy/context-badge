import unittest

from context_badge.theme import (
    TRANSPARENT,
    TRANSPARENT_KEY,
    blend_hex,
    bounded_int,
    is_transparent,
    paint_color,
)


class ThemeTests(unittest.TestCase):
    def test_blend_endpoints(self) -> None:
        self.assertEqual(blend_hex("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(blend_hex("#000000", "#ffffff", 1), "#ffffff")

    def test_blend_midpoint(self) -> None:
        self.assertEqual(blend_hex("#000000", "#ffffff", 0.5), "#808080")

    def test_blend_rejects_invalid_amount(self) -> None:
        with self.assertRaises(ValueError):
            blend_hex("#000000", "#ffffff", 1.1)

    def test_bounded_int_coerces_and_clamps(self) -> None:
        self.assertEqual(bounded_int("500", 440, 280, 1000), 500)
        self.assertEqual(bounded_int("bad", 440, 280, 1000), 440)
        self.assertEqual(bounded_int(5000, 440, 280, 1000), 1000)

    def test_transparent_is_a_fill_value(self) -> None:
        self.assertTrue(is_transparent(TRANSPARENT))
        self.assertTrue(is_transparent(TRANSPARENT_KEY))
        self.assertFalse(is_transparent("#263244"))
        self.assertEqual(paint_color(TRANSPARENT), TRANSPARENT_KEY)
        self.assertEqual(paint_color("#263244"), "#263244")


if __name__ == "__main__":
    unittest.main()
