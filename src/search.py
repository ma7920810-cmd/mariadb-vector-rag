"""Semantic retrieval with MariaDB vector distance and relational joins."""
import time
from src.db import connect, vector_literal
from src.embeddings import embed_query
from src.config import TOP_K


def search(question, top_k=TOP_K, category=None):
    query_vector = vector_literal(embed_query(question))
    where = ""
    params = [query_vector]
    if category:
        where = "WHERE a.category = ?"
        params.append(category)
    params.append(int(top_k))
    sql = f"""
        SELECT c.id AS chunk_id, a.id AS article_id, a.title, a.wiki_url,
               a.category, c.content,
               VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(?)) AS distance
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
    for row in rows:
        row["score"] = 1.0 - float(row["distance"])
    return rows, elapsed_ms


if __name__ == "__main__":
    question = input("Ask a question: ").strip()
    results, elapsed = search(question)
    print(f"Retrieved {len(results)} chunks in {elapsed:.1f} ms")
    for i, item in enumerate(results, 1):
        print(f"\n{i}. {item['title']} (cosine similarity {item['score']:.3f})")
        print(item["content"][:900])
        print(item["wiki_url"])
