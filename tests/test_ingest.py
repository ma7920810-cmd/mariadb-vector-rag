import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.ingest import DEFAULT_CORPUS, load_corpus, run
from src.wikipedia import Article, PageInfo, html_to_sections
from tests.fixtures import ARTICLE_HTML


class FakeClient:
    """Stands in for WikipediaClient; returns fixture pages without network."""

    def __init__(self, infos):
        self.infos = infos
        self.fetched = []

    def page_info(self, titles):
        return [self.infos[t] for t in titles]

    def fetch_article(self, page_id, description=None):
        self.fetched.append(page_id)
        info = next(i for i in self.infos.values() if i.page_id == page_id)
        return Article(info.title, page_id, info.rev_id, "https://x/" + info.title,
                       description, html_to_sections(ARTICLE_HTML))


def info(title, page_id, **kw):
    return PageInfo(requested_title=title, title=title, page_id=page_id,
                    rev_id=kw.pop("rev_id", 1), length=kw.pop("length", 50_000), **kw)


@mock.patch("src.ingest.MIN_ARTICLE_WORDS", 50)  # fixture article is short
class IngestDryRunTests(unittest.TestCase):
    def test_filters_and_deduplicates_before_fetching(self):
        client = FakeClient({
            "Database": info("Database", 1),
            "Databases": info("Database", 1),           # redirect to same page
            "Mercury": info("Mercury", 2, disambiguation=True),
            "Stub": info("Stub", 3, length=500),
            "Nope": PageInfo("Nope", missing=True),
        })
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp) / "chunks.jsonl"
            report = run([("Database", "databases"), ("Databases", "databases"),
                          ("Mercury", "x"), ("Stub", "x"), ("Nope", "x")],
                         dry_run=True, export=export, client=client)
            rows = [json.loads(line) for line in export.read_text().splitlines()]
        self.assertEqual(client.fetched, [1])
        self.assertEqual(report.counts, {"dry-run": 1, "duplicate": 1,
                                         "filtered": 2, "missing": 1})
        self.assertTrue(rows)
        self.assertEqual({r["category"] for r in rows}, {"databases"})
        self.assertIn("Terminology", {r["section"] for r in rows})

    def test_corpus_file_is_valid(self):
        pairs = load_corpus(DEFAULT_CORPUS)
        titles = [t for t, _ in pairs]
        self.assertGreaterEqual(len(pairs), 50)
        self.assertEqual(len(titles), len(set(titles)), "duplicate titles in corpus")
        for _, category in pairs:
            self.assertRegex(category, r"^[a-z-]{1,120}$")


if __name__ == "__main__":
    unittest.main()
