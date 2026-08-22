import unittest

from context_badge.win32 import RECT, clamp_into


class ClampIntoTests(unittest.TestCase):
    def test_primary_monitor_keeps_a_box_on_screen(self) -> None:
        bounds = RECT(0, 0, 1920, 1080)
        x, y = clamp_into(100, 80, 200, 80, bounds)
        self.assertEqual((x, y), (100, 80))
        x, y = clamp_into(1900, 1070, 200, 80, bounds)
        self.assertEqual((x, y), (1720, 1000))

    def test_virtual_screen_allows_a_left_monitor(self) -> None:
        bounds = RECT(-1920, 0, 1920, 1080)
        x, y = clamp_into(-400, 40, 120, 80, bounds)
        self.assertEqual((x, y), (-400, 40))
        x, y = clamp_into(-2000, 40, 120, 80, bounds)
        self.assertEqual((x, y), (-1920, 40))

    def test_crossing_from_primary_into_right_monitor(self) -> None:
        bounds = RECT(0, 0, 3840, 1080)
        x, y = clamp_into(2000, 50, 160, 90, bounds)
        self.assertEqual((x, y), (2000, 50))


if __name__ == "__main__":
    unittest.main()
