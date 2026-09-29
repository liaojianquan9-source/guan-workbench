"""Check that the cut script uses only words present in its cited source clips."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/口播剪辑/260922_12W小组作业_AI拉片工作台_剪辑稿.md"
SOURCE = Path("/Users/liaojianquan/Downloads/260922_12W小组作业_AI拉片工作台.txt")


def normalized(text: str) -> str:
    text = text.lower().replace("a肉", "aroll")
    return "".join(re.findall(r"[\u4e00-\u9fff\da-z]", text))


def is_subsequence(edited: str, original: str) -> bool:
    iterator = iter(original)
    return all(character in iterator for character in edited)


class OralEditSourceFidelityTest(unittest.TestCase):
    def test_every_spoken_character_follows_cited_source_order(self) -> None:
        source_lines = SOURCE.read_text(encoding="utf-8").splitlines()
        manuscript = SCRIPT.read_text(encoding="utf-8")
        blocks = re.findall(r"<!-- lines: ([\d,\-]+) -->\n> ([^\n]+)", manuscript)
        self.assertEqual(len(blocks), 8)

        for index, (reference, spoken) in enumerate(blocks, start=1):
            selected = []
            for part in reference.split(","):
                limits = [int(value) for value in part.split("-")]
                first, last = (limits[0], limits[-1])
                selected.extend(source_lines[first - 1:last])
            with self.subTest(segment=index):
                self.assertTrue(is_subsequence(normalized(spoken), normalized("".join(selected))))

    def test_current_state_and_future_plan_are_explicit(self) -> None:
        manuscript = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("没有用到一点 AI 的功能的", manuscript)
        self.assertIn("之后我会结合 AI 的能力", manuscript)
        self.assertIn("我想去做的就是做 AI 复刻", manuscript)
        self.assertIn("到时候开源到 GitHub 上", manuscript)


if __name__ == "__main__":
    unittest.main()
