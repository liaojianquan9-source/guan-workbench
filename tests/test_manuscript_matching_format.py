"""Validate the paste-ready manuscript matching input."""

from pathlib import Path
import unicodedata
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "docs/口播剪辑/9月22日_文稿匹配.txt"


class ManuscriptMatchingFormatTest(unittest.TestCase):
    def test_single_batch_plain_lines_without_punctuation(self) -> None:
        text = MANUSCRIPT.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(len(lines), 52)
        self.assertTrue(all(line and line == line.strip() for line in lines))
        self.assertLessEqual(len("".join(lines)), 5000)
        self.assertFalse(any(unicodedata.category(char).startswith("P") for char in text))

    def test_full_sequence_and_corrected_terms(self) -> None:
        text = MANUSCRIPT.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("为什么大佬的片子你抄都抄不明白\n"))
        self.assertTrue(text.endswith("到时候我分享给大家\n"))
        self.assertIn("这里是A roll的部分", text)
        self.assertIn("这里是B roll的部分", text)
        self.assertIn("开源到GitHub上", text)
        self.assertIn("没有用到一点AI的功能的", text)


if __name__ == "__main__":
    unittest.main()
