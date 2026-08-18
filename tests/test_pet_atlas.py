import unittest

from context_badge.pet_atlas import PetAtlas, crop_bgra, premultiply_bgra, scale_bgra
from context_badge.pet_spec import (
    ATLAS_HEIGHT_V2,
    ATLAS_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    look_cell,
    look_index_from_angle,
)


class PetAtlasHelperTests(unittest.TestCase):
    def test_crop_copies_the_requested_pixel(self) -> None:
        pixels = bytes(
            [
                1, 2, 3, 255,
                4, 5, 6, 255,
                7, 8, 9, 255,
                10, 11, 12, 255,
            ]
        )
        cropped = crop_bgra(pixels, 2, 2, 1, 0, 1, 1)
        self.assertEqual(cropped, bytes([4, 5, 6, 255]))

    def test_half_scale_averages_a_2x2_block(self) -> None:
        pixels = bytes(
            [
                0, 0, 0, 0,
                40, 0, 0, 0,
                0, 80, 0, 0,
                0, 0, 120, 0,
            ]
        )
        scaled = scale_bgra(pixels, 2, 2, 1, 1)
        self.assertEqual(scaled, bytes([10, 20, 30, 0]))

    def test_premultiply_scales_colour_by_alpha(self) -> None:
        pixels = bytes([100, 50, 0, 128])
        self.assertEqual(premultiply_bgra(pixels), bytes([50, 25, 0, 128]))

    def test_look_cells_follow_the_v2_clock(self) -> None:
        self.assertEqual(look_cell(0).row, 9)
        self.assertEqual(look_cell(0).column, 0)
        self.assertEqual(look_cell(8).row, 10)
        self.assertEqual(look_cell(8).column, 0)
        self.assertEqual(look_index_from_angle(90), 4)
        self.assertEqual(ATLAS_WIDTH, 1536)
        self.assertEqual(ATLAS_HEIGHT_V2, 2288)

    def test_set_scale_resizes_cells_and_drops_cached_frames(self) -> None:
        pixels = bytes(ATLAS_WIDTH * ATLAS_HEIGHT_V2 * 4)
        atlas = PetAtlas(pixels, ATLAS_WIDTH, ATLAS_HEIGHT_V2, scale=0.5)
        self.assertEqual(atlas.cell_width, CELL_WIDTH // 2)
        self.assertEqual(atlas.cell_height, CELL_HEIGHT // 2)
        atlas._frames[(0, 0)] = b"cached"
        atlas.set_scale(0.25)
        self.assertEqual(atlas.cell_width, round(CELL_WIDTH * 0.25))
        self.assertEqual(atlas.cell_height, round(CELL_HEIGHT * 0.25))
        self.assertEqual(atlas._frames, {})
        atlas.set_scale(0.25)
        self.assertEqual(atlas.scale, 0.25)


if __name__ == "__main__":
    unittest.main()
