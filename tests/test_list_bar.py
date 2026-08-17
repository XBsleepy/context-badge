import unittest
from types import SimpleNamespace

from context_badge.list_bar import (
    BASE_HINT,
    ITEM_HINT,
    NOTE_HINT,
    _is_typing_key,
)


class ListBarHintTests(unittest.TestCase):
    def test_hints_are_here_you_can_prompts(self) -> None:
        for hint in (BASE_HINT, NOTE_HINT, ITEM_HINT):
            self.assertTrue(hint.startswith("Here you can"))
            self.assertNotEqual(hint.lower(), "base")

    def test_typing_key_replaces_a_placeholder(self) -> None:
        self.assertTrue(_is_typing_key(SimpleNamespace(keysym="a", char="a")))
        self.assertTrue(_is_typing_key(SimpleNamespace(keysym="space", char=" ")))
        self.assertFalse(_is_typing_key(SimpleNamespace(keysym="Return", char="\r")))
        self.assertFalse(_is_typing_key(SimpleNamespace(keysym="BackSpace", char="")))
        self.assertFalse(_is_typing_key(SimpleNamespace(keysym="Shift_L", char="")))


if __name__ == "__main__":
    unittest.main()
