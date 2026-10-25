import unittest
from src.chunking import chunk_text


class ChunkingTests(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(chunk_text(""), [])

    def test_overlap_and_size(self):
        text = " ".join(f"w{i}" for i in range(700))
        chunks = chunk_text(text, size=100, overlap=20)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.split()) <= 100 for chunk in chunks))
        self.assertEqual(chunks[0].split()[-20:], chunks[1].split()[:20])

    def test_invalid_overlap(self):
        with self.assertRaises(ValueError):
            chunk_text("some words", size=10, overlap=10)


if __name__ == "__main__":
    unittest.main()
