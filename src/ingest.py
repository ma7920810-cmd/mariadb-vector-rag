"""Fetch Wikipedia articles, chunk them, embed them, and store them in MariaDB.

Usage:
    python -m src.ingest                       # curated corpus in data/corpus.json
    python -m src.ingest --only-category databases
    python -m src.ingest --titles "Vector database" "Okapi BM25" --category information-retrieval
    python -m src.ingest --from-category "Information retrieval" --limit 25 \
                         --category information-retrieval
    python -m src.ingest --dry-run --export chunks.jsonl   # inspect chunks, no DB/embeddings

Re-running is safe and incremental. An article is only re-fetched and
re-embedded when its Wikipedia revision, its cleaned text, or the chunking /
embedding settings changed (use --force to override). Duplicate prevention:
titles are resolved through redirects and deduplicated by Wikipedia page id
(unique in the database), repeated chunks inside an article are dropped, and
chunks whose text already exists under another article are skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.chunking import CHUNKER_VERSION, chunk_sections
from src.config import (CHUNK_OVERLAP, CHUNK_WORDS, EMBEDDING_DIM,
                        EMBEDDING_MODEL, MIN_CHUNK_WORDS)
from src.wikipedia import WikipediaClient

log = logging.getLogger("ingest")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = ROOT / "data" / "corpus.json"
MIGRATION = ROOT / "sql" / "002_ingestion_metadata.sql"

MIN_ARTICLE_BYTES = 2_000   # wikitext length; filters stubs before downloading
MIN_ARTICLE_WORDS = 250     # cleaned prose; filters list-like or empty pages


def ingest_signature() -> str:
    """Changes whenever stored chunks/vectors would come out differently."""
    raw = f"{CHUNKER_VERSION}|{CHUNK_WORDS}|{CHUNK_OVERLAP}|{MIN_CHUNK_WORDS}|{EMBEDDING_MODEL}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- corpus --------------------------------------------------------------------
def load_corpus(path: Path, only_category: str | None = None) -> list[tuple[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs = []
    for category, titles in data["categories"].items():
        if only_category and category != only_category:
            continue
        pairs += [(title, category) for title in titles]
    return pairs


# -- schema --------------------------------------------------------------------
def ensure_schema(conn) -> None:
    """Apply migration 002 to databases created before it existed."""
    cur = conn.cursor()
    cur.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE()
             AND ((TABLE_NAME = 'articles' AND COLUMN_NAME = 'ingest_signature')
               OR (TABLE_NAME = 'chunks' AND COLUMN_NAME = 'content_hash'))""")
    if cur.fetchone()[0] == 2:
        return
    log.info("Applying schema migration %s", MIGRATION.name)
    sql = "\n".join(line for line in MIGRATION.read_text().splitlines()
                    if not line.strip().startswith("--"))
    for statement in filter(None, (s.strip() for s in sql.split(";"))):
        cur.execute(statement)
    conn.commit()


@dataclass
class StoredState:
    article_id: int
    rev_id: int | None
    content_hash: str | None
    signature: str | None
    chunk_count: int


def stored_state(conn, page_ids) -> dict[int, StoredState]:
    if not page_ids:
        return {}
    cur = conn.cursor()
    marks = ",".join("?" * len(page_ids))
    cur.execute(
        f"""SELECT a.wiki_page_id, a.id, a.rev_id, a.content_hash,
                   a.ingest_signature, COUNT(c.id)
            FROM articles a LEFT JOIN chunks c ON c.article_id = a.id
            WHERE a.wiki_page_id IN ({marks})
            GROUP BY a.id""", tuple(page_ids))
    return {row[0]: StoredState(*row[1:]) for row in cur.fetchall()}


def existing_chunk_hashes(conn, hashes, exclude_article_id) -> set[str]:
    """Chunk hashes already stored under a *different* article."""
    if not hashes:
        return set()
    cur = conn.cursor()
    marks = ",".join("?" * len(hashes))
    cur.execute(
        f"""SELECT DISTINCT content_hash FROM chunks
            WHERE content_hash IN ({marks}) AND article_id <> ?""",
        (*hashes, exclude_article_id or 0))
    return {row[0] for row in cur.fetchall()}


def write_article(conn, article, category, chunks, vectors, content_hash,
                  word_count, signature) -> int:
    """Upsert one article and replace its chunks in a single transaction."""
    from src.db import vector_literal
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO articles
                 (title, wiki_url, wiki_page_id, rev_id, category, description,
                  word_count, content_hash, ingest_signature, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'wikipedia_api')
               ON DUPLICATE KEY UPDATE
                 title = VALUES(title), wiki_url = VALUES(wiki_url),
                 wiki_page_id = VALUES(wiki_page_id), rev_id = VALUES(rev_id),
                 category = VALUES(category), description = VALUES(description),
                 word_count = VALUES(word_count), content_hash = VALUES(content_hash),
                 ingest_signature = VALUES(ingest_signature),
                 source = VALUES(source), fetched_at = CURRENT_TIMESTAMP""",
            (article.title[:500], article.url, article.page_id, article.rev_id,
             category[:120], (article.description or None) and article.description[:500],
             word_count, content_hash, signature),
        )
        cur.execute("SELECT id FROM articles WHERE wiki_page_id = ?", (article.page_id,))
        article_id = cur.fetchone()[0]
        cur.execute("DELETE FROM chunks WHERE article_id = ?", (article_id,))
        cur.executemany(
            """INSERT INTO chunks (article_id, chunk_index, section, content,
                                   word_count, content_hash, embedding)
               VALUES (?, ?, ?, ?, ?, ?, VEC_FromText(?))""",
            [(article_id, i, chunk.section[:255], chunk.text, chunk.word_count,
              chunk.content_hash, vector_literal(vector))
             for i, (chunk, vector) in enumerate(zip(chunks, vectors))],
        )
        conn.commit()
        return article_id
    except Exception:
        conn.rollback()
        raise


def touch_revision(conn, article_id, rev_id, category, description) -> None:
    """Article text unchanged: record the new revision without re-embedding."""
    cur = conn.cursor()
    cur.execute("""UPDATE articles SET rev_id = ?, category = ?, description = ?,
                   fetched_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (rev_id, category, description, article_id))
    conn.commit()


# -- orchestration -------------------------------------------------------------
@dataclass
class Report:
    rows: list[tuple[str, str, str]] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    chunks_written: int = 0
    over_limit: int = 0
    token_limit: int | None = None

    def add(self, title, status, detail=""):
        self.rows.append((title, status, detail))
        self.counts[status] += 1
        log.info("%-11s %s%s", status, title, f"  ({detail})" if detail else "")

    def print_summary(self):
        log.info("\nSummary: %s", ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items())))
        log.info("Chunks written: %d", self.chunks_written)
        if self.token_limit and self.over_limit:
            log.warning("%d chunks exceed the model's %d-token input and were truncated "
                        "when embedded; consider lowering CHUNK_WORDS.",
                        self.over_limit, self.token_limit)


def select_pages(client, pairs, report):
    """Resolve titles, drop missing/disambiguation/stub pages and duplicates."""
    infos = client.page_info([title for title, _ in pairs])
    selected, seen = [], {}
    for (requested, category), info in zip(pairs, infos):
        if info.missing:
            report.add(requested, "missing", "no such Wikipedia article")
        elif info.disambiguation:
            report.add(requested, "filtered", "disambiguation page")
        elif info.length < MIN_ARTICLE_BYTES:
            report.add(requested, "filtered", f"stub ({info.length} bytes)")
        elif info.page_id in seen:
            report.add(requested, "duplicate", f"same page as '{seen[info.page_id]}'")
        else:
            seen[info.page_id] = requested
            selected.append((info, category))
    return selected


def run(pairs, *, force=False, dry_run=False, export=None, prune=False,
        client=None, conn=None) -> Report:
    client = client or WikipediaClient()
    report = Report()
    signature = ingest_signature()
    selected = select_pages(client, pairs, report)

    state = {}
    if not dry_run:
        ensure_schema(conn)
        state = stored_state(conn, [info.page_id for info, _ in selected])
    export_file = open(export, "w", encoding="utf-8") if export else None

    try:
        for info, category in selected:
            title = info.title
            try:
                previous = state.get(info.page_id)
                current = (previous and previous.chunk_count > 0
                           and previous.signature == signature and not force)
                if current and previous.rev_id == info.rev_id:
                    report.add(title, "unchanged", f"rev {info.rev_id}")
                    continue

                article = client.fetch_article(info.page_id, info.description)
                body = article.text
                digest = text_hash(body)
                words = len(body.split())
                if current and previous.content_hash == digest:
                    touch_revision(conn, previous.article_id, article.rev_id,
                                   category, article.description)
                    report.add(title, "unchanged", "new revision, same text")
                    continue
                if words < MIN_ARTICLE_WORDS:
                    report.add(title, "filtered", f"only {words} words of prose")
                    continue

                chunks = chunk_sections(article.sections, article.title)
                dupes = set() if dry_run else existing_chunk_hashes(
                    conn, [c.content_hash for c in chunks],
                    previous.article_id if previous else None)
                kept = [c for c in chunks if c.content_hash not in dupes]
                if not kept:
                    report.add(title, "filtered", "no usable chunks")
                    continue
                if export_file:
                    for c in kept:
                        export_file.write(json.dumps(
                            {"title": article.title, "category": category,
                             "section": c.section, "words": c.word_count,
                             "text": c.text}, ensure_ascii=False) + "\n")

                detail = f"{len(kept)} chunks, {len(article.sections)} sections"
                if dupes:
                    detail += f", {len(chunks) - len(kept)} duplicate chunks skipped"
                if dry_run:
                    report.add(title, "dry-run", detail)
                    continue

                from src.embeddings import count_over_limit, embed_texts
                texts = [c.embed_text for c in kept]
                vectors = embed_texts(texts)
                if vectors.shape[1] != EMBEDDING_DIM:
                    raise RuntimeError(
                        f"Embedding model produced {vectors.shape[1]} dimensions, "
                        f"but the chunks.embedding column is VECTOR({EMBEDDING_DIM}).")
                over, report.token_limit = count_over_limit(texts)
                report.over_limit += over

                write_article(conn, article, category, kept, vectors, digest,
                              words, signature)
                report.chunks_written += len(kept)
                report.add(title, "updated" if previous else "added", detail)
            except Exception as exc:  # one bad page must not stop the run
                report.add(title, "failed", f"{type(exc).__name__}: {exc}")
                if not dry_run:
                    _recover_connection(conn)

        if prune and not dry_run:
            prune_articles(conn, {info.page_id for info, _ in selected}, report)
    finally:
        if export_file:
            export_file.close()
    return report


def _recover_connection(conn) -> None:
    """Reconnect if the failure dropped the database connection."""
    try:
        conn.ping()
    except Exception:
        log.warning("Database connection lost; reconnecting")
        conn.reconnect()


def prune_articles(conn, keep_page_ids, report) -> None:
    """Delete API-ingested articles that are no longer part of the corpus."""
    cur = conn.cursor()
    cur.execute("SELECT id, title, wiki_page_id FROM articles")
    for article_id, title, page_id in cur.fetchall():
        if page_id not in keep_page_ids:
            cur.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            report.add(title, "pruned", "not in corpus")
    conn.commit()


def ingest_page(conn, title, category="general"):
    """Backwards-compatible single-article entry point. Returns chunks written."""
    return run([(title, category)], conn=conn).chunks_written


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                        help="JSON corpus file (default: data/corpus.json)")
    source.add_argument("--titles", nargs="+", metavar="TITLE",
                        help="ingest these article titles")
    source.add_argument("--from-category", metavar="WIKI_CATEGORY",
                        help="ingest articles from a Wikipedia category")
    parser.add_argument("--category", default="general",
                        help="category label stored for --titles/--from-category")
    parser.add_argument("--only-category", help="only this category of the corpus file")
    parser.add_argument("--limit", type=int, default=25,
                        help="max articles for --from-category (default 25)")
    parser.add_argument("--force", action="store_true",
                        help="re-chunk and re-embed even if nothing changed")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and chunk only; no embeddings, no database")
    parser.add_argument("--export", metavar="FILE.jsonl",
                        help="write the produced chunks to a JSONL file for review")
    parser.add_argument("--prune", action="store_true",
                        help="delete stored articles that are not in this corpus run")
    return parser.parse_args(argv)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    client = WikipediaClient()
    if args.titles:
        pairs = [(t, args.category) for t in args.titles]
    elif args.from_category:
        titles = client.category_members(args.from_category, limit=args.limit * 2)
        titles = [t for t in titles if not t.startswith(("List of", "Outline of",
                                                          "Index of", "Glossary of"))]
        pairs = [(t, args.category) for t in titles[:args.limit]]
    else:
        pairs = load_corpus(args.corpus, args.only_category)
    if args.prune and (args.titles or args.from_category or args.only_category):
        sys.exit("--prune is only allowed with a full corpus file run.")

    if args.dry_run:
        report = run(pairs, dry_run=True, export=args.export, client=client)
    else:
        from src.db import connect
        with connect() as conn:
            report = run(pairs, force=args.force, export=args.export,
                         prune=args.prune, client=client, conn=conn)
    report.print_summary()
    return 1 if report.counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
