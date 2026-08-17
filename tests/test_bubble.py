import unittest

from context_badge.bubble import (
    bubble_outline,
    content_box,
    rounded_rect_points,
    unfold_ease,
)


class BubbleTests(unittest.TestCase):
    def test_unfold_ease_stays_in_unit_interval(self) -> None:
        self.assertEqual(unfold_ease(0), 0.0)
        self.assertEqual(unfold_ease(1), 1.0)
        self.assertGreater(unfold_ease(0.5), 0.5)
        self.assertLess(unfold_ease(0.5), 1.0)
        self.assertEqual(unfold_ease(-1), 0.0)
        self.assertEqual(unfold_ease(2), 1.0)

    def test_outline_stays_inside_the_window(self) -> None:
        width, height = 440, 220
        points = bubble_outline(width, height, radius=18, tail_height=11)
        xs = points[0::2]
        ys = points[1::2]
        self.assertGreaterEqual(min(xs), 1)
        self.assertLessEqual(max(xs), width - 1)
        self.assertGreaterEqual(min(ys), 1)
        self.assertLessEqual(max(ys), height - 1)
        self.assertLess(min(ys), 12)
        self.assertGreater(max(ys), height - 12)

    def test_tail_points_up_from_the_body(self) -> None:
        points = bubble_outline(400, 200, tail_height=12, tail_width=20, inset=2)
        xs = points[0::2]
        ys = points[1::2]
        apex = ys.index(min(ys))
        self.assertLess(xs[apex], 400 * 0.5)
        self.assertLess(ys[apex], 6)

    def test_content_box_sits_inside_the_body(self) -> None:
        x, y, w, h = content_box(
            440, 240, tail_height=11, radius=18, rod_height=8, pad=10
        )
        self.assertGreaterEqual(x, 8)
        self.assertGreater(y, 11)
        self.assertLess(x + w, 440)
        self.assertLess(y + h, 240)
        self.assertGreater(w, 300)
        self.assertGreater(h, 150)

    def test_square_outline_keeps_a_top_tail(self) -> None:
        points = bubble_outline(400, 200, radius=0, tail_height=12, inset=2)
        xs = points[0::2]
        ys = points[1::2]
        self.assertEqual(len(xs), 7)
        self.assertEqual(min(xs), 2)
        self.assertEqual(max(xs), 398)
        self.assertLess(min(ys), 6)
        self.assertEqual(max(ys), 198)

    def test_rounded_rect_points_can_be_sharp(self) -> None:
        points = rounded_rect_points(0, 0, 100, 40, radius=0)
        self.assertEqual(points, [0.0, 0.0, 100.0, 0.0, 100.0, 40.0, 0.0, 40.0])

    def test_rounded_rect_can_leave_one_corner_square(self) -> None:
        sharp = rounded_rect_points(0, 0, 80, 40, radius=10)
        mixed = rounded_rect_points(0, 0, 80, 40, radius=10, ne=False)
        self.assertGreater(len(sharp), 8)
        self.assertLess(len(mixed), len(sharp))
        xs = mixed[0::2]
        ys = mixed[1::2]
        self.assertIn(80.0, xs)
        self.assertEqual(ys[xs.index(80.0)], 0.0)


if __name__ == "__main__":
    unittest.main()
