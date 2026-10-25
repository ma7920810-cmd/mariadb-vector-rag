"""Fetch Wikipedia pages, chunk them, embed them, and insert into MariaDB.

Usage: python -m src.ingest
The first run intentionally ingests five seed pages so the pipeline can be checked
before the corpus is expanded.
"""
import time
import requests
from bs4 import BeautifulSoup
from src.chunking import chunk_text
from src.db import connect, vector_literal
from src.embeddings import embed_texts

SEED_PAGES = [
    "Computer science", "Database", "Information retrieval",
    "Machine learning", "Wikipedia",
]
API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "ConstructorUniversityVectorRAG/0.1 (student project)"}


def fetch_page(title):
    response = requests.get(
        API,
        params={"action": "parse", "page": title, "prop": "text|pageid",
                "format": "json", "redirects": 1},
        headers=HEADERS, timeout=30,
    )
    response.raise_for_status()
    data = response.json()["parse"]
    soup = BeautifulSoup(data["text"]["*"], "html.parser")
    for tag in soup(["script", "style", "sup", "table", "nav", "figure"]):
        tag.decompose()
    text = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
    canonical_title = data["title"]
    page_id = int(data["pageid"])
    url = "https://en.wikipedia.org/wiki/" + requests.utils.quote(
        canonical_title.replace(" ", "_"), safe="()_,-"
    )
    return canonical_title, page_id, url, text


def ingest_page(conn, title):
    canonical_title, page_id, url, text = fetch_page(title)
    pieces = chunk_text(text)
    if not pieces:
        print(f"Skipped {title}: no sufficiently long text.")
        return 0
    vectors = embed_texts(pieces)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO articles (title, wiki_url, wiki_page_id, category)
           VALUES (?, ?, ?, 'general')
           ON DUPLICATE KEY UPDATE title=VALUES(title),
             wiki_page_id=VALUES(wiki_page_id), id=LAST_INSERT_ID(id)""",
        (canonical_title, url, page_id),
    )
    cur.execute("SELECT id FROM articles WHERE wiki_url = ?", (url,))
    article_id = cur.fetchone()[0]
    cur.execute("DELETE FROM chunks WHERE article_id = ?", (article_id,))
    for index, (piece, vector) in enumerate(zip(pieces, vectors)):
        cur.execute(
            """INSERT INTO chunks
               (article_id, chunk_index, content, word_count, embedding)
               VALUES (?, ?, ?, ?, VEC_FromText(?))""",
            (article_id, index, piece, len(piece.split()), vector_literal(vector)),
        )
    conn.commit()
    print(f"Ingested {canonical_title}: {len(pieces)} chunks")
    return len(pieces)


def main():
    total = 0
    with connect() as conn:
        for title in SEED_PAGES:
            try:
                total += ingest_page(conn, title)
                time.sleep(0.5)  # be polite to Wikipedia
            except Exception as exc:
                conn.rollback()
                print(f"ERROR ingesting {title}: {exc}")
    print(f"Done. Total chunks inserted: {total}")


if __name__ == "__main__":
    main()
