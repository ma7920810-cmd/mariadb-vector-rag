import unittest
from unittest import mock

import requests

from src.wikipedia import (WikipediaClient, WikipediaError, article_url,
                           html_to_sections)
from tests.fixtures import ARTICLE_HTML, QUERY_RESPONSE, parse_response


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def client_with(responses):
    session = mock.Mock()
    session.headers = {}
    session.get.side_effect = responses
    sleeps = []
    client = WikipediaClient(session=session, delay=0, sleep=sleeps.append)
    return client, session, sleeps


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.sections = html_to_sections(ARTICLE_HTML)
        self.text = "\n".join(s.text for s in self.sections)

    def test_sections_and_hierarchy(self):
        self.assertEqual([s.heading for s in self.sections],
                         ["Introduction", "Terminology", "Terminology > Models"])

    def test_noise_removed(self):
        for noise in ("Infobox noise", "Navbox noise", "Reference text",
                      "Stray paragraph", "Comparison of database tools",
                      "For other uses", "[1]", "citation needed",
                      "Organized collection of data\n"):
            self.assertNotIn(noise, self.text)

    def test_inline_text_is_clean(self):
        self.assertIn("an organized collection of data managed by a database "
                      "management system (DBMS).", self.text)

    def test_math_and_exponents(self):
        self.assertIn("grows as O(n^{2}) in the worst case", self.text)
        self.assertIn("10^6 records", self.text)

    def test_lists_are_kept_in_content_sections(self):
        self.assertIn("Relational model; Document model.", self.sections[-1].text)

    def test_url_matches_original_encoding(self):
        self.assertEqual(article_url("Join (SQL)"), "https://en.wikipedia.org/wiki/Join_(SQL)")
        self.assertEqual(article_url("Entity–relationship model"),
                         "https://en.wikipedia.org/wiki/Entity%E2%80%93relationship_model")


class ClientTests(unittest.TestCase):
    def test_page_info_resolves_redirects_and_flags(self):
        client, session, _ = client_with([FakeResponse(payload=QUERY_RESPONSE)])
        infos = client.page_info(["database", "DBMS", "Mercury", "No such article xyz"])
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual((infos[0].title, infos[0].page_id, infos[0].rev_id),
                         ("Database", 8377, 1001))
        self.assertEqual(infos[0].description, "Organized collection of data")
        self.assertEqual(infos[1].page_id, 18933632)
        self.assertTrue(infos[2].disambiguation)
        self.assertTrue(infos[3].missing)

    def test_every_request_sends_maxlag_and_user_agent(self):
        client, session, _ = client_with([FakeResponse(payload=QUERY_RESPONSE)])
        client.page_info(["database"])
        params = session.get.call_args.kwargs["params"]
        self.assertEqual(params["maxlag"], 5)
        self.assertIn("(", client.session.headers["User-Agent"])  # contact info

    def test_retries_429_honouring_retry_after(self):
        client, session, sleeps = client_with([
            FakeResponse(429, headers={"Retry-After": "7"}),
            requests.ConnectionError("reset"),
            FakeResponse(payload=parse_response(8377, "Database", 1001)),
        ])
        article = client.fetch_article(8377)
        self.assertEqual(article.rev_id, 1001)
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual(sleeps[0], 7.0)

    def test_retries_maxlag_api_error(self):
        lag = {"error": {"code": "maxlag", "info": "Waiting for db: 7 seconds lagged"}}
        client, session, _ = client_with([
            FakeResponse(payload=lag),
            FakeResponse(payload=parse_response(8377, "Database", 1001)),
        ])
        self.assertEqual(client.fetch_article(8377).title, "Database")

    def test_non_retryable_error_raises(self):
        err = {"error": {"code": "missingtitle", "info": "The page doesn't exist."}}
        client, session, _ = client_with([FakeResponse(payload=err)])
        with self.assertRaises(WikipediaError):
            client.fetch_article(1)
        self.assertEqual(session.get.call_count, 1)

    def test_gives_up_after_max_retries(self):
        client, session, _ = client_with([FakeResponse(503)] * 10)
        client.max_retries = 3
        with self.assertRaises(WikipediaError):
            client.fetch_article(1)
        self.assertEqual(session.get.call_count, 4)


if __name__ == "__main__":
    unittest.main()
