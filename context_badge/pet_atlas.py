"""Crop, scale, and cache Codex pet atlas cells."""

from __future__ import annotations

import json
from pathlib import Path

from .pet_spec import (
    ATLAS_HEIGHT_V1,
    ATLAS_HEIGHT_V2,
    ATLAS_WIDTH,
    CELL_HEIGHT,
    CELL_WIDTH,
    CellRef,
    cell_origin,
)


def crop_bgra(
    pixels: bytes, width: int, height: int, x: int, y: int, w: int, h: int
) -> bytes:
    """Copy a rectangle from a packed BGRA buffer."""
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError("crop is outside the bitmap")
    row_bytes = w * 4
    out = bytearray(row_bytes * h)
    src = memoryview(pixels)
    for row in range(h):
        start = ((y + row) * width + x) * 4
        dest = row * row_bytes
        out[dest : dest + row_bytes] = src[start : start + row_bytes]
    return bytes(out)


def scale_bgra(pixels: bytes, width: int, height: int, dest_w: int, dest_h: int) -> bytes:
    """Scale BGRA with a box filter when halving, otherwise nearest neighbour."""
    dest_w = max(1, int(dest_w))
    dest_h = max(1, int(dest_h))
    if dest_w == width and dest_h == height:
        return bytes(pixels)
    if dest_w * 2 == width and dest_h * 2 == height:
        return _scale_half(pixels, width, height)
    out = bytearray(dest_w * dest_h * 4)
    src = memoryview(pixels)
    for y in range(dest_h):
        sy = min(height - 1, y * height // dest_h)
        for x in range(dest_w):
            sx = min(width - 1, x * width // dest_w)
            si = (sy * width + sx) * 4
            di = (y * dest_w + x) * 4
            out[di : di + 4] = src[si : si + 4]
    return bytes(out)


def _scale_half(pixels: bytes, width: int, height: int) -> bytes:
    dest_w = width // 2
    dest_h = height // 2
    out = bytearray(dest_w * dest_h * 4)
    src = memoryview(pixels)
    for y in range(dest_h):
        for x in range(dest_w):
            i00 = ((y * 2) * width + (x * 2)) * 4
            i10 = i00 + 4
            i01 = (((y * 2) + 1) * width + (x * 2)) * 4
            i11 = i01 + 4
            di = (y * dest_w + x) * 4
            for c in range(4):
                out[di + c] = (
                    src[i00 + c] + src[i10 + c] + src[i01 + c] + src[i11 + c]
                ) // 4
    return bytes(out)


def premultiply_bgra(pixels: bytes) -> bytes:
    """Convert straight BGRA into premultiplied BGRA for UpdateLayeredWindow."""
    out = bytearray(pixels)
    for i in range(0, len(out), 4):
        alpha = out[i + 3]
        if alpha == 255:
            continue
        if alpha == 0:
            out[i] = 0
            out[i + 1] = 0
            out[i + 2] = 0
            continue
        out[i] = out[i] * alpha // 255
        out[i + 1] = out[i + 1] * alpha // 255
        out[i + 2] = out[i + 2] * alpha // 255
    return bytes(out)


class PetAtlas:
    """A decoded v1/v2 spritesheet that yields premultiplied display cells."""

    def __init__(
        self,
        pixels: bytes,
        width: int,
        height: int,
        *,
        scale: float = 0.5,
        display_name: str = "",
        pet_id: str = "",
    ) -> None:
        if width != ATLAS_WIDTH or height not in (ATLAS_HEIGHT_V1, ATLAS_HEIGHT_V2):
            raise ValueError(f"unsupported pet atlas size {width}x{height}")
        self.pixels = pixels
        self.width = width
        self.height = height
        self.version = 2 if height == ATLAS_HEIGHT_V2 else 1
        self.display_name = display_name
        self.pet_id = pet_id
        self.scale = max(0.25, min(1.0, float(scale)))
        self.cell_width = max(1, round(CELL_WIDTH * self.scale))
        self.cell_height = max(1, round(CELL_HEIGHT * self.scale))
        self._frames: dict[tuple[int, int], bytes] = {}

    def set_scale(self, scale: float) -> None:
        """Rebuild display cells at a new scale without decoding the atlas again."""
        next_scale = max(0.25, min(1.0, float(scale)))
        cell_w = max(1, round(CELL_WIDTH * next_scale))
        cell_h = max(1, round(CELL_HEIGHT * next_scale))
        if (
            abs(next_scale - self.scale) < 1e-6
            and cell_w == self.cell_width
            and cell_h == self.cell_height
        ):
            return
        self.scale = next_scale
        self.cell_width = cell_w
        self.cell_height = cell_h
        self._frames.clear()

    def frame(self, cell: CellRef) -> bytes:
        key = (int(cell.row), int(cell.column))
        cached = self._frames.get(key)
        if cached is not None:
            return cached
        x, y = cell_origin(*key)
        cropped = crop_bgra(
            self.pixels, self.width, self.height, x, y, CELL_WIDTH, CELL_HEIGHT
        )
        scaled = scale_bgra(
            cropped, CELL_WIDTH, CELL_HEIGHT, self.cell_width, self.cell_height
        )
        premul = premultiply_bgra(scaled)
        self._frames[key] = premul
        return premul


def parse_pet_manifest(folder: Path) -> dict[str, object]:
    data = json.loads((folder / "pet.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pet.json must be an object")
    sheet = str(data.get("spritesheetPath") or "spritesheet.webp")
    pet_id = str(data.get("id") or folder.name)
    name = str(data.get("displayName") or pet_id)
    version = data.get("spriteVersionNumber")
    try:
        sprite_version = int(version) if version is not None else 1
    except (TypeError, ValueError):
        sprite_version = 1
    return {
        "id": pet_id,
        "display_name": name,
        "sheet": folder / sheet,
        "version": sprite_version,
    }


def load_pet_atlas(folder: Path, *, scale: float = 0.5) -> PetAtlas:
    from .wic_image import decode_bgra

    info = parse_pet_manifest(folder)
    sheet = Path(str(info["sheet"]))
    pixels, width, height = decode_bgra(sheet)
    return PetAtlas(
        pixels,
        width,
        height,
        scale=scale,
        display_name=str(info["display_name"]),
        pet_id=str(info["id"]),
    )
