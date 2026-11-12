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


from src.chunking import chunk_sections, normalized_hash, split_sentences


def sentences(n, prefix="Fact"):
    return " ".join(f"{prefix} number {i} describes one property of the system." for i in range(n))


class SentenceSplitTests(unittest.TestCase):
    def test_abbreviations_and_initials_do_not_split(self):
        text = 'Indexes help, e.g. B-trees. Dr. Codd wrote "A Relational Model." The U.S. Army used it. E. F. Codd agreed.'
        self.assertEqual(split_sentences(text), [
            "Indexes help, e.g. B-trees.", 'Dr. Codd wrote "A Relational Model."',
            "The U.S. Army used it.", "E. F. Codd agreed."])

    def test_paragraph_breaks_are_boundaries(self):
        self.assertEqual(split_sentences("first part\n\nsecond part"),
                         ["first part", "second part"])


class SectionChunkingTests(unittest.TestCase):
    def test_respects_max_words_and_sentence_boundaries(self):
        chunks = chunk_sections([("Introduction", sentences(80))], "Database",
                                max_words=100, overlap_words=20, min_words=10)
        self.assertGreater(len(chunks), 3)
        for chunk in chunks:
            self.assertLessEqual(chunk.word_count, 100)
            self.assertTrue(chunk.text.startswith("Fact number"))
            self.assertTrue(chunk.text.endswith("."))

    def test_overlap_is_whole_sentences(self):
        chunks = chunk_sections([("Introduction", sentences(40))], "T",
                                max_words=50, overlap_words=20, min_words=5)
        last_two = chunks[0].text.split(". ")[-2:]
        self.assertTrue(chunks[1].text.startswith(last_two[0]))

    def test_chunks_never_cross_sections_and_carry_context(self):
        chunks = chunk_sections([("History", sentences(10, "Old")),
                                 ("Design > Storage", sentences(10, "New"))],
                                "Database", max_words=200, overlap_words=20, min_words=10)
        self.assertEqual([c.section for c in chunks], ["History", "Design > Storage"])
        self.assertNotIn("New", chunks[0].text)
        self.assertTrue(chunks[1].embed_text.startswith("Database — Design > Storage: New"))

    def test_lead_section_uses_title_only(self):
        chunk = chunk_sections([("Introduction", sentences(5))], "SQL", min_words=5)[0]
        self.assertTrue(chunk.embed_text.startswith("SQL: Fact"))

    def test_short_section_merged_not_dropped(self):
        chunks = chunk_sections([("History", "Founded in 1970."),
                                 ("History > Later", sentences(10))],
                                "T", max_words=200, overlap_words=20, min_words=30)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Founded in 1970.", chunks[0].text)

    def test_overlong_sentence_is_split(self):
        long_sentence = " ".join(f"w{i}" for i in range(250)) + "."
        chunks = chunk_sections([("Introduction", long_sentence)], "T",
                                max_words=100, overlap_words=10, min_words=10)
        self.assertTrue(all(c.word_count <= 100 for c in chunks))

    def test_duplicate_chunks_removed(self):
        block = sentences(8)
        chunks = chunk_sections([("A", block), ("B", block)], "T",
                                max_words=200, overlap_words=10, min_words=10)
        self.assertEqual(len(chunks), 1)

    def test_hash_ignores_whitespace_and_case(self):
        self.assertEqual(normalized_hash("Hello,  World"), normalized_hash("hello world"))

    def test_invalid_settings(self):
        with self.assertRaises(ValueError):
            chunk_sections([("A", "x")], "T", max_words=10, overlap_words=10)


if __name__ == "__main__":
    unittest.main()
