"""The subtitle adapter keeps model evidence and drops noise-only emissions."""

import unittest

from tools.transcribe import meaningful_text


class TranscriptFilterTest(unittest.TestCase):
    def test_punctuation_only_output_is_not_presented_as_speech(self):
        for text in (".", "……", "!?", " "):
            self.assertFalse(meaningful_text(text))

    def test_real_words_and_numbers_are_retained(self):
        for text in ("你好", "hello", "2026", "第 3 镜"):
            self.assertTrue(meaningful_text(text))


if __name__ == "__main__":
    unittest.main()
