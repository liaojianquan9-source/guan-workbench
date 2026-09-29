"""Check that both generated cover drafts are usable PNGs at the requested ratios."""

from pathlib import Path
import struct
import unittest


ASSETS = Path(__file__).resolve().parents[1] / "outputs/260922-ai-lapian-cover"


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as file:
        header = file.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


class DouyinCoverAssetsTest(unittest.TestCase):
    def test_requested_ratios_and_resolution(self) -> None:
        for name, ratio in (("cover-3x4-v1.png", (3, 4)), ("cover-4x3-v1.png", (4, 3))):
            with self.subTest(name=name):
                path = ASSETS / name
                self.assertTrue(path.is_file())
                width, height = png_size(path)
                self.assertGreaterEqual(min(width, height), 1000)
                self.assertEqual(width * ratio[1], height * ratio[0])


if __name__ == "__main__":
    unittest.main()
