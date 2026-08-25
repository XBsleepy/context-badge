import unittest

from context_badge.theme import (
    APP_COLOURS,
    COLOUR_PALETTE,
    COLOUR_THEMES,
    DEFAULT_BACKGROUND,
    DEFAULT_BORDER,
    DEFAULT_CORNER_RADIUS,
    DEFAULT_LIST_BACKGROUND,
    DEFAULT_TEXT,
    IDLE_BLEND,
    LOCK_COLOUR,
    RADIUS_CHOICES,
    TRANSPARENT,
    TRANSPARENT_KEY,
    blend_hex,
    bounded_int,
    idle_fill,
    is_hex_color,
    is_transparent,
    matching_theme_id,
    paint_color,
    theme_by_id,
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

    def test_hex_colour_shape(self) -> None:
        self.assertTrue(is_hex_color("#16181d"))
        self.assertFalse(is_hex_color("16181d"))
        self.assertFalse(is_hex_color("#fff"))

    def test_ink_is_the_default_theme(self) -> None:
        ink = theme_by_id("ink")
        assert ink is not None
        self.assertEqual(ink.background, DEFAULT_BACKGROUND)
        self.assertEqual(ink.list_background, DEFAULT_LIST_BACKGROUND)
        self.assertEqual(ink.text, DEFAULT_TEXT)
        self.assertEqual(ink.border, DEFAULT_BORDER)
        self.assertEqual(DEFAULT_CORNER_RADIUS, 12)

    def test_matching_theme_id_finds_presets(self) -> None:
        parchment = theme_by_id("parchment")
        assert parchment is not None
        self.assertEqual(
            matching_theme_id(
                parchment.background,
                parchment.list_background,
                parchment.text,
                parchment.border,
            ),
            "parchment",
        )
        self.assertIsNone(
            matching_theme_id("#16181d", "#101218", "#f4f1ea", "#ffffff")
        )

    def test_named_themes_are_unique(self) -> None:
        ids = [theme.id for theme in COLOUR_THEMES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("ink", ids)
        self.assertIsNone(theme_by_id("missing"))

    def test_app_and_lock_colours_are_palette_swatches(self) -> None:
        self.assertTrue(set(APP_COLOURS).issubset(COLOUR_PALETTE))
        self.assertEqual(LOCK_COLOUR, "#94a3b8")
        self.assertIn(LOCK_COLOUR, COLOUR_PALETTE)
        self.assertNotIn(LOCK_COLOUR, APP_COLOURS)

    def test_idle_fill_sits_near_the_background(self) -> None:
        ink = idle_fill("#16181d", "#f4f1ea")
        parchment = idle_fill("#f3ead9", "#3d2f1f")
        self.assertEqual(ink, blend_hex("#16181d", "#f4f1ea", IDLE_BLEND))
        self.assertEqual(parchment, blend_hex("#f3ead9", "#3d2f1f", IDLE_BLEND))
        self.assertNotEqual(ink, LOCK_COLOUR)


class MenuPopupModuleTests(unittest.TestCase):
    def test_popup_binds_theme_tables(self) -> None:
        from context_badge import menu_popup

        self.assertEqual(menu_popup.COLOUR_THEMES, COLOUR_THEMES)
        self.assertEqual(menu_popup.RADIUS_CHOICES, RADIUS_CHOICES)
        self.assertEqual(menu_popup.PET_WIDTH, menu_popup.MAIN_WIDTH)


if __name__ == "__main__":
    unittest.main()
