import unittest
from pathlib import Path

from context_badge.paths import find_pet_folder
from context_badge.pet_spec import ATLAS_HEIGHT_V2, ATLAS_WIDTH


class WicImageTests(unittest.TestCase):
    def test_qiuli_atlas_decodes_as_v2(self) -> None:
        folder = find_pet_folder("qiuli")
        if folder is None:
            self.skipTest("qiuli is not installed under ~/.codex/pets")
        from context_badge.wic_image import decode_bgra

        sheet = folder / "spritesheet.webp"
        pixels, width, height = decode_bgra(sheet)
        self.assertEqual(width, ATLAS_WIDTH)
        self.assertEqual(height, ATLAS_HEIGHT_V2)
        self.assertEqual(len(pixels), width * height * 4)
        self.assertTrue(Path(sheet).is_file())

    def test_qiuli_idle_cell_scales_to_half_size(self) -> None:
        folder = find_pet_folder("qiuli")
        if folder is None:
            self.skipTest("qiuli is not installed under ~/.codex/pets")
        from context_badge.pet_atlas import load_pet_atlas
        from context_badge.pet_spec import CELL_HEIGHT, CELL_WIDTH, CellRef

        atlas = load_pet_atlas(folder, scale=0.5)
        self.assertEqual(atlas.version, 2)
        self.assertEqual(atlas.cell_width, CELL_WIDTH // 2)
        self.assertEqual(atlas.cell_height, CELL_HEIGHT // 2)
        frame = atlas.frame(CellRef(0, 0))
        self.assertEqual(len(frame), atlas.cell_width * atlas.cell_height * 4)
        self.assertTrue(any(frame[i + 3] for i in range(0, len(frame), 4)))


if __name__ == "__main__":
    unittest.main()
