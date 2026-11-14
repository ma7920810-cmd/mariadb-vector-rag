import unittest
from unittest import mock

from src.evaluation import answer_metrics, retrieval_metrics
from src import search as search_module


class EvaluationMetricTests(unittest.TestCase):
    def test_retrieval_scores_expected_ranked_titles(self):
        rows = [{"title": "Noise"}, {"title": "HNSW"}, {"title": "Nearest neighbor search"}]
        scores = retrieval_metrics(rows, ["HNSW", "Nearest neighbor search"], 3)
        self.assertAlmostEqual(scores["precision@3"], 2 / 3)
        self.assertEqual(scores["recall@3"], 1.0)
        self.assertEqual(scores["mrr@3"], 0.5)
        self.assertGreater(scores["ndcg@3"], 0.0)

    def test_retrieval_is_zero_when_no_relevant_title_found(self):
        scores = retrieval_metrics([{"title": "Noise"}], ["HNSW"], 5)
        self.assertEqual(scores["recall@5"], 0.0)
        self.assertEqual(scores["mrr@5"], 0.0)

    def test_duplicate_chunks_from_one_article_do_not_inflate_metrics(self):
        rows = [{"title": "HNSW"}, {"title": "HNSW"},
                {"title": "Nearest neighbor search"}]
        scores = retrieval_metrics(rows, ["HNSW", "Nearest neighbor search"], 3)
        self.assertEqual(scores["precision@3"], 1.0)
        self.assertEqual(scores["recall@3"], 1.0)
        self.assertEqual(scores["ndcg@3"], 1.0)

    def test_answer_key_points_and_citation_indices(self):
        scores = answer_metrics("Vectors encode meaning [Source 1]. See [Source 9].",
                                ["vectors", "meaning", "distance"], 1)
        self.assertAlmostEqual(scores["key_point_coverage"], 2 / 3)
        self.assertEqual(scores["citation_validity"], 0.5)
        self.assertEqual(scores["invalid_citations"], 1)

    def test_no_citations_are_not_counted_as_valid(self):
        scores = answer_metrics("No source references.", ["references"], 0)
        self.assertFalse(scores["has_citation"])
        self.assertEqual(scores["citation_validity"], 0.0)

    @mock.patch("src.search.embed_query", return_value=[0.1, 0.2])
    @mock.patch("src.search.connect")
    def test_metadata_filters_are_bound_in_same_vector_query(self, connect, _embed):
        cursor = mock.Mock()
        cursor.fetchall.return_value = []
        connect.return_value.__enter__.return_value.cursor.return_value = cursor
        search_module.search("question", 3, "databases", 500, "2025-01-01")
        sql, params = cursor.execute.call_args.args
        self.assertIn("VEC_DISTANCE_COSINE", sql)
        self.assertIn("JOIN articles AS a", sql)
        self.assertIn("a.category = ?", sql)
        self.assertIn("a.word_count >= ?", sql)
        self.assertIn("a.fetched_at >= ?", sql)
        self.assertEqual(params[1:4], ("databases", 500, "2025-01-01"))


if __name__ == "__main__":
    unittest.main()
