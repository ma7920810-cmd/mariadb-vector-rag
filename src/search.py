"""Semantic retrieval with MariaDB vector distance and relational joins."""

import time

from src.db import connect, vector_literal
from src.embeddings import embed_query
from src.config import TOP_K


def search(question, top_k=TOP_K, category=None, min_article_words=None,
           fetched_after=None):
    query_vector = vector_literal(embed_query(question))

    predicates = []
    params = [query_vector]

    if category:
        predicates.append("a.category = ?")
        params.append(category)
    if min_article_words is not None:
        predicates.append("a.word_count >= ?")
        params.append(max(0, int(min_article_words)))
    if fetched_after:
        predicates.append("a.fetched_at >= ?")
        params.append(fetched_after)
    where = "WHERE " + " AND ".join(predicates) if predicates else ""

    params.append(int(top_k) * 5)
    sql = f"""
        SELECT
            c.id AS chunk_id,
            a.id AS article_id,
            a.title,
            a.wiki_url,
            a.category,
            a.word_count AS article_word_count,
            a.fetched_at,
            c.content,
            VEC_DISTANCE_COSINE(
                c.embedding,
                VEC_FromText(?)
            ) AS distance
        FROM chunks AS c
        JOIN articles AS a ON a.id = c.article_id
        {where}
        ORDER BY distance ASC
        LIMIT ?
    """

    started = time.perf_counter()

    with connect() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

    elapsed_ms = (time.perf_counter() - started) * 1000

    # Convert cosine distance into similarity score.
    for row in rows:
        row["score"] = 1.0 - float(row["distance"])

    # Allow up to two relevant chunks from each article.
    selected_rows = []
    article_counts = {}

    for row in rows:
        article_id = row["article_id"]
        count = article_counts.get(article_id, 0)

        if count < 2:
           selected_rows.append(row)
           article_counts[article_id] = count + 1

        if len(selected_rows) >= int(top_k):
           break

    return selected_rows, elapsed_ms
if __name__ == "__main__":
    question = input("Ask a question: ").strip()

    results, elapsed = search(question)

    print(
        f"Retrieved {len(results)} results "
        f"in {elapsed:.1f} ms"
    )

    for i, item in enumerate(results, 1):
        print(
            f"\n{i}. {item['title']} "
            f"(cosine similarity {item['score']:.3f})"
        )
        print(item["content"][:900])
        print(item["wiki_url"])
