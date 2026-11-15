"""Runnable MariaDB-native vector SQL walkthrough with bound query parameters.

Usage:
    python -m src.sql_demo
    python -m src.sql_demo --question "What is vector search?" --category databases

Requires an ingested MariaDB database and the configured embedding model.
"""
import argparse
import json

from src.db import connect, vector_literal
from src.embeddings import embed_query

SQL = """
SELECT c.id AS chunk_id, a.title, a.category, a.word_count,
       c.section,
       VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(?)) AS distance
FROM chunks AS c
JOIN articles AS a ON a.id = c.article_id
WHERE (? IS NULL OR a.category = ?)
  AND (? IS NULL OR a.word_count >= ?)
ORDER BY distance ASC
LIMIT ?
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="How does vector search work?")
    parser.add_argument("--category", default=None)
    parser.add_argument("--min-words", type=int, default=None)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if args.k < 1 or (args.min_words is not None and args.min_words < 0):
        parser.error("--k must be >= 1 and --min-words must be >= 0")

    vector = vector_literal(embed_query(args.question))
    params = (vector, args.category, args.category,
              args.min_words, args.min_words, args.k)

    with connect() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS articles FROM articles")
        print("Articles:", cur.fetchone()["articles"])
        cur.execute("SELECT COUNT(*) AS chunks FROM chunks")
        print("Chunks:", cur.fetchone()["chunks"])
        cur.execute("SHOW INDEX FROM chunks WHERE Key_name = 'embedding'")
        print("Vector index rows:", len(cur.fetchall()))
        cur.execute("EXPLAIN " + SQL, params)
        plan = cur.fetchall()
        print("EXPLAIN:", json.dumps(plan, default=str, indent=2))
        cur.execute(SQL, params)
        rows = cur.fetchall()

    print("Results:")
    for row in rows:
        print(f"  {row['title']} [{row['category']}] "
              f"distance={float(row['distance']):.4f} "
              f"chunk={row['chunk_id']}")
    if not rows:
        print("  No matches. Try omitting filters.")
    print("Note: SQL filters may change optimizer index selection; inspect EXPLAIN.")


if __name__ == "__main__":
    main()
