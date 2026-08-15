"""Measured text wrapping helpers for the badge canvas."""

from __future__ import annotations

from typing import Protocol


class MeasurableFont(Protocol):
    def measure(self, text: str) -> int: ...


def fit_text(text: str, font: MeasurableFont, max_width: int, max_lines: int) -> str:
    """Wrap by measured pixels and ellipsize to the requested region."""
    if max_width <= 0 or max_lines <= 0:
        return ""

    lines: list[str] = []
    current = ""
    overflowed = False
    characters = text.replace("\r", "")

    for index, character in enumerate(characters):
        if character == "\n":
            lines.append(current.rstrip())
            current = ""
        elif not current or font.measure(current + character) <= max_width:
            current += character
        else:
            lines.append(current.rstrip())
            current = character.lstrip()

        if len(lines) >= max_lines:
            overflowed = bool(current) or index < len(characters) - 1
            break
    else:
        if current or not lines:
            lines.append(current.rstrip())

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        overflowed = True
    if overflowed:
        last = lines[-1] if lines else ""
        while last and font.measure(last + "…") > max_width:
            last = last[:-1]
        if not last and font.measure("…") > max_width:
            return ""
        if lines:
            lines[-1] = last.rstrip() + "…"
        else:
            lines = ["…"]
    return "\n".join(lines)
