"""Pure benchmark helper tests; no database or model download required."""
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from benchmark import percentile, stats, questions_from_dataset


class BenchmarkHelperTests(unittest.TestCase):
    def test_nearest_rank_percentile(self):
        self.assertEqual(percentile([5, 1, 4, 2, 3], .95), 5)
        self.assertEqual(percentile([5, 1, 4, 2, 3], .5), 3)
        self.assertIsNone(percentile([], .95))

    def test_stats_empty_and_nonempty(self):
        self.assertIsNone(stats([])["mean_ms"])
        self.assertEqual(stats([1, 2, 3])["median_ms"], 2)
        self.assertEqual(stats([1, 2, 3])["p95_ms"], 3)

    def test_unique_questions_and_limit(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "questions.json"
            path.write_text(json.dumps([
                {"question": "alpha"}, {"question": "alpha"},
                {"question": "beta"}, {"question": "  "},
            ]), encoding="utf-8")
            self.assertEqual(questions_from_dataset(path, 0), ["alpha", "beta"])
            self.assertEqual(questions_from_dataset(path, 1), ["alpha"])


if __name__ == "__main__":
    unittest.main()
