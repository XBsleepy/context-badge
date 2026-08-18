import unittest

from context_badge.list_bar import BASE_HINT, ITEM_HINT, NOTE_HINT


class ListBarHintTests(unittest.TestCase):
    def test_hints_are_here_you_can_prompts(self) -> None:
        for hint in (BASE_HINT, NOTE_HINT, ITEM_HINT):
            self.assertTrue(hint.startswith("Here you can"))
            self.assertNotEqual(hint.lower(), "base")


if __name__ == "__main__":
    unittest.main()
