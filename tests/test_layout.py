import unittest

from context_badge.layout import badge_metrics


class LayoutTests(unittest.TestCase):
    def test_default_size_keeps_base_type(self) -> None:
        metrics = badge_metrics(440, 72)
        self.assertEqual(metrics.app_font_size, 10)
        self.assertEqual(metrics.title_font_size, 13)
        self.assertEqual(metrics.padding_x, 22)
        self.assertEqual(metrics.app_y, 19)
        self.assertEqual(metrics.title_y, 38)
        self.assertEqual(metrics.list_font_size, metrics.title_font_size)
        self.assertEqual(metrics.list_font_size, 13)
        self.assertEqual(metrics.list_count_font_size, metrics.app_font_size)
        self.assertEqual(metrics.list_count_font_size, 10)
        self.assertEqual(metrics.list_header_height, 40)
        self.assertEqual(metrics.list_row_height, 44)
        self.assertEqual(metrics.list_section_height, 26)
        self.assertEqual(metrics.list_radius, 18)
        self.assertEqual(metrics.list_tail_height, 11)

    def test_taller_badge_uses_larger_type(self) -> None:
        default = badge_metrics(440, 72)
        tall = badge_metrics(440, 144)
        self.assertGreater(tall.app_font_size, default.app_font_size)
        self.assertGreater(tall.title_font_size, default.title_font_size)
        self.assertGreater(tall.title_y, default.title_y)
        self.assertGreater(tall.list_font_size, default.list_font_size)
        self.assertEqual(tall.list_font_size, tall.title_font_size)
        self.assertGreater(tall.list_row_height, default.list_row_height)

    def test_extra_height_grows_title_slot_faster_than_type(self) -> None:
        default = badge_metrics(440, 72)
        tall = badge_metrics(440, 144)
        default_slot = 72 - default.title_y - default.text_bottom_gap
        tall_slot = 144 - tall.title_y - tall.text_bottom_gap
        self.assertGreater(tall_slot, default_slot)
        self.assertGreater(
            tall_slot / default_slot,
            tall.title_font_size / default.title_font_size,
        )

    def test_shorter_badge_uses_smaller_type(self) -> None:
        default = badge_metrics(440, 72)
        short = badge_metrics(440, 64)
        self.assertLessEqual(short.title_font_size, default.title_font_size)
        self.assertGreaterEqual(short.app_font_size, 7)
        self.assertGreaterEqual(short.title_font_size, 9)

    def test_wider_badge_keeps_the_same_type(self) -> None:
        default = badge_metrics(440, 72)
        wide = badge_metrics(880, 72)
        self.assertEqual(wide.app_font_size, default.app_font_size)
        self.assertEqual(wide.title_font_size, default.title_font_size)
        self.assertGreaterEqual(wide.padding_x, default.padding_x)

    def test_layout_stays_inside_the_badge(self) -> None:
        sizes = ((280, 64), (440, 72), (1000, 260), (280, 260), (1000, 64))
        for width, height in sizes:
            with self.subTest(width=width, height=height):
                metrics = badge_metrics(width, height)
                self.assertLess(metrics.app_y, metrics.title_y)
                self.assertLess(metrics.title_y, height)
                self.assertLess(metrics.title_y + metrics.text_bottom_gap, height)


if __name__ == "__main__":
    unittest.main()
