import unittest

from context_badge.pet_place import (
    ATTACH_LEFT,
    ATTACH_RIGHT,
    BadgeAnchor,
    PERCH_TOP,
    PetSize,
    keep_sit_offset,
    normalize_placement,
    normalize_scale_percent,
    place_pet,
    relative_offset,
)


class PetPlaceTests(unittest.TestCase):
    def test_unknown_placement_becomes_perch(self) -> None:
        self.assertEqual(normalize_placement("sideways"), PERCH_TOP)
        self.assertEqual(normalize_placement(ATTACH_LEFT), ATTACH_LEFT)

    def test_perch_sits_on_the_badge_body(self) -> None:
        badge = BadgeAnchor(x=100, y=200, width=440, height=72, body_width=394)
        pet = PetSize(width=96, height=104)
        x, y = place_pet(PERCH_TOP, badge, pet, overlap=20)
        self.assertEqual(x, 100 + (394 - 96) // 2)
        self.assertEqual(y, 200 - 104 + 20)

    def test_attach_left_keeps_a_chat_bubble_gap(self) -> None:
        badge = BadgeAnchor(x=200, y=80, width=440, height=72)
        pet = PetSize(width=96, height=104)
        x, y = place_pet(ATTACH_LEFT, badge, pet, overlap=10)
        self.assertEqual(x, 200 - 96 + 10)
        self.assertEqual(y, 80 + 72 - 104)

    def test_attach_right_sits_past_the_tabs(self) -> None:
        badge = BadgeAnchor(x=200, y=80, width=440, height=72)
        pet = PetSize(width=96, height=104)
        x, y = place_pet(ATTACH_RIGHT, badge, pet, overlap=10)
        self.assertEqual(x, 200 + 440 - 10)
        self.assertEqual(y, 80 + 72 - 104)

    def test_placement_choices_cover_the_named_layouts(self) -> None:
        from context_badge.pet_place import PLACEMENT_CHOICES, PLACEMENTS

        self.assertEqual(tuple(value for value, _label in PLACEMENT_CHOICES), PLACEMENTS)

    def test_scale_clamps_without_snapping(self) -> None:
        self.assertEqual(normalize_scale_percent(None), 50)
        self.assertEqual(normalize_scale_percent("bad"), 50)
        self.assertEqual(normalize_scale_percent(10), 25)
        self.assertEqual(normalize_scale_percent(40), 40)
        self.assertEqual(normalize_scale_percent(70), 70)
        self.assertEqual(normalize_scale_percent(1000), 100)

    def test_relative_offset_is_from_the_badge_origin(self) -> None:
        badge = BadgeAnchor(x=100, y=200, width=440, height=72, body_width=394)
        pet = PetSize(width=96, height=104)
        x, y = place_pet(PERCH_TOP, badge, pet, overlap=20)
        self.assertEqual(relative_offset(PERCH_TOP, badge, pet, overlap=20), (x - 100, y - 200))

    def test_keep_sit_holds_the_bottom_centre(self) -> None:
        old = PetSize(width=96, height=104)
        new = PetSize(width=192, height=208)
        self.assertEqual(keep_sit_offset(old, new, (10, 20)), (-38, -84))


if __name__ == "__main__":
    unittest.main()
