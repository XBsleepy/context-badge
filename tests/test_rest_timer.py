import unittest

from context_badge.menu_popup import normalize_hide_target
from context_badge.rest_timer import (
    DEFAULT_REST_MINUTES,
    DEFAULT_REST_SECONDS,
    PRESET_REST_MINUTES,
    format_countdown,
    format_rest_interval,
    minutes_from_seconds,
    normalize_custom_minutes,
    normalize_custom_slot,
    normalize_rest_minutes,
    normalize_rest_seconds,
    seed_custom_minutes,
    custom_slot_is_selected,
    normalize_rest_message,
    DEFAULT_REST_MESSAGE,
)


class RestTimerTests(unittest.TestCase):
    def test_minutes_clamp_without_snapping_to_presets(self) -> None:
        self.assertEqual(normalize_rest_minutes(None), DEFAULT_REST_MINUTES)
        self.assertEqual(normalize_rest_minutes(1), 1)
        self.assertEqual(normalize_rest_minutes(45), 45)
        self.assertEqual(normalize_rest_minutes(0), 1)
        self.assertEqual(normalize_rest_minutes(999), 180)
        self.assertEqual(PRESET_REST_MINUTES, (15, 30, 60))

    def test_seconds_round_to_whole_minutes(self) -> None:
        self.assertEqual(normalize_rest_seconds(None), DEFAULT_REST_SECONDS)
        self.assertEqual(minutes_from_seconds(10), 1)
        self.assertEqual(normalize_rest_seconds(10), 60)
        self.assertEqual(normalize_rest_seconds(45 * 60), 45 * 60)
        self.assertEqual(format_rest_interval(3600), "60m")
        self.assertEqual(format_rest_interval(45 * 60), "45m")

    def test_custom_slots_normalize_and_seed(self) -> None:
        self.assertEqual(
            normalize_custom_minutes([45, None, "90"]),
            [45, None, 90],
        )
        self.assertEqual(
            normalize_custom_minutes(None),
            [None, None, None],
        )
        self.assertEqual(
            seed_custom_minutes([None, None, None], 60),
            [None, None, None],
        )
        self.assertEqual(
            seed_custom_minutes([None, None, None], 45),
            [45, None, None],
        )
        self.assertEqual(
            seed_custom_minutes([45, None, None], 90),
            [45, 90, None],
        )

    def test_custom_slot_selection_lights_the_slot(self) -> None:
        customs = [45, None, 60]
        self.assertEqual(normalize_custom_slot(0, customs, 45), 0)
        self.assertEqual(normalize_custom_slot(None, customs, 60), None)
        self.assertEqual(normalize_custom_slot(2, customs, 60), 2)
        self.assertTrue(
            custom_slot_is_selected(
                0, minutes=45, customs=customs, selected_slot=0
            )
        )
        self.assertFalse(
            custom_slot_is_selected(
                2, minutes=60, customs=customs, selected_slot=0
            )
        )
        self.assertFalse(
            custom_slot_is_selected(
                2, minutes=60, customs=customs, selected_slot=None
            )
        )

    def test_rest_message_normalizes(self) -> None:
        self.assertEqual(normalize_rest_message(None), DEFAULT_REST_MESSAGE)
        self.assertEqual(normalize_rest_message("  "), DEFAULT_REST_MESSAGE)
        self.assertEqual(normalize_rest_message("stand up\nnow"), "stand up now")
        self.assertEqual(len(normalize_rest_message("x" * 200)), 80)

    def test_alert_style_normalizes(self) -> None:
        from context_badge.rest_timer import normalize_rest_alert_style

        self.assertEqual(normalize_rest_alert_style(None), "pet")
        self.assertEqual(normalize_rest_alert_style("bubble"), "pet")
        self.assertEqual(normalize_rest_alert_style("window"), "window")
        self.assertEqual(normalize_rest_alert_style("dialog"), "window")
        self.assertEqual(normalize_rest_alert_style("nope"), "pet")

    def test_countdown_format(self) -> None:
        self.assertEqual(format_countdown(0), "00:00")
        self.assertEqual(format_countdown(10_000), "00:10")
        self.assertEqual(format_countdown(65_000), "01:05")


class FakeTk:
    def __init__(self) -> None:
        self.jobs: dict[str, tuple[int, object]] = {}
        self._n = 0

    def after(self, ms: int, func):  # noqa: ANN001
        self._n += 1
        job = str(self._n)
        self.jobs[job] = (ms, func)
        return job

    def after_cancel(self, job: str) -> None:
        self.jobs.pop(job, None)


class RestTimerHoldTests(unittest.TestCase):
    def test_fire_waits_for_ack_before_next_interval(self) -> None:
        from context_badge.rest_timer import RestTimer

        root = FakeTk()
        fired: list[bool] = []
        timer = RestTimer(root, on_fire=lambda: fired.append(True))
        timer.configure(enabled=True, seconds=60)
        self.assertIsNotNone(timer._job)
        timer._fire()
        self.assertEqual(fired, [True])
        self.assertTrue(timer.awaiting)
        self.assertEqual(timer.remaining_ms(), 0)
        self.assertIsNone(timer._job)
        timer.acknowledge()
        self.assertFalse(timer.awaiting)
        self.assertIsNotNone(timer._job)


class HideTargetTests(unittest.TestCase):
    def test_hide_target_normalize(self) -> None:
        self.assertEqual(normalize_hide_target(None), "all")
        self.assertEqual(normalize_hide_target("badge"), "badge")
        self.assertEqual(normalize_hide_target("PET"), "pet")
        self.assertEqual(normalize_hide_target("weird"), "all")


if __name__ == "__main__":
    unittest.main()
