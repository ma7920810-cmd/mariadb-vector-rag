"""Reproducible MariaDB HNSW vs exact-scan benchmark.

Measures database-query time only (embedding generation is excluded).
The exact scan is a reference for nearest-neighbor overlap, not a claim
that the reference results are human-judged relevant.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL
from src.db import connect

INDEXED_SQL = """
SELECT c.id, VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(?)) AS distance
FROM chunks AS c
ORDER BY distance ASC LIMIT ?
"""
EXACT_SQL = """
SELECT c.id, VEC_DISTANCE_COSINE(c.embedding, VEC_FromText(?)) AS distance
FROM chunks AS c IGNORE INDEX (embedding)
ORDER BY distance ASC LIMIT ?
"""


def percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(len(ordered) * p) - 1)]


def stats(values):
    return {
        "mean_ms": round(statistics.mean(values), 3) if values else None,
        "median_ms": round(statistics.median(values), 3) if values else None,
        "p95_ms": round(percentile(values, .95), 3) if values else None,
        "min_ms": round(min(values), 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
    }


def run_query(cursor, sql, vector, k):
    start = time.perf_counter()
    cursor.execute(sql, (vector, k))
    ids = [int(row[0]) for row in cursor.fetchall()]
    return ids, (time.perf_counter() - start) * 1000


def questions_from_dataset(path, limit):
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    questions = list(dict.fromkeys(
        str(case["question"]).strip() for case in cases if str(case.get("question", "")).strip()
    ))
    if not questions:
        raise ValueError("No questions found in evaluation dataset")
    return questions[:limit] if limit else questions


def benchmark(dataset="data/evaluation.json", iterations=10, warmup=2, k=5,
              limit=0, seed=42, output="reports/hnsw-benchmark.json"):
    if iterations < 1 or warmup < 0 or k < 1 or limit < 0:
        raise ValueError("iterations and k must be >=1; warmup and limit must be >=0")
    questions = questions_from_dataset(dataset, limit)
    print(f"Encoding {len(questions)} unique questions with {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    vectors = model.encode(questions)
    vector_texts = [json.dumps([float(v) for v in vector]) for vector in vectors]
    rng = random.Random(seed)
    timings = {"indexed": [], "exact": []}
    per_question = []
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunks = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM articles")
        articles = int(cursor.fetchone()[0])
        if chunks == 0:
            raise RuntimeError("No chunks in database. Run python -m src.ingest first.")
        cursor.execute("EXPLAIN " + INDEXED_SQL, (vector_texts[0], k))
        indexed_plan = [list(map(str, row)) for row in cursor.fetchall()]
        cursor.execute("EXPLAIN " + EXACT_SQL, (vector_texts[0], k))
        exact_plan = [list(map(str, row)) for row in cursor.fetchall()]
        for question, vector in zip(questions, vector_texts):
            for _ in range(warmup):
                run_query(cursor, INDEXED_SQL, vector, k)
                run_query(cursor, EXACT_SQL, vector, k)
            samples = {"indexed": [], "exact": []}
            # Interleave and shuffle method order to reduce systematic drift.
            for _ in range(iterations):
                methods = ["indexed", "exact"]
                rng.shuffle(methods)
                for method in methods:
                    sql = INDEXED_SQL if method == "indexed" else EXACT_SQL
                    _, ms = run_query(cursor, sql, vector, k)
                    samples[method].append(ms)
                    timings[method].append(ms)
            indexed_ids, _ = run_query(cursor, INDEXED_SQL, vector, k)
            exact_ids, _ = run_query(cursor, EXACT_SQL, vector, k)
            # Recall denominator uses available exact neighbors, at most k.
            recall = len(set(indexed_ids) & set(exact_ids)) / len(set(exact_ids)) if exact_ids else None
            per_question.append({
                "question": question,
                "recall_at_k_vs_exact": round(recall, 4) if recall is not None else None,
                "indexed": stats(samples["indexed"]),
                "exact": stats(samples["exact"]),
                "indexed_ids": indexed_ids,
                "exact_ids": exact_ids,
            })
            print(f"[{len(per_question)}/{len(questions)}] recall@{k}={recall:.3f}" if recall is not None else "No exact results")
    indexed_mean = statistics.mean(timings["indexed"])
    exact_mean = statistics.mean(timings["exact"])
    recalls = [r["recall_at_k_vs_exact"] for r in per_question if r["recall_at_k_vs_exact"] is not None]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "dataset": dataset, "question_count": len(questions),
            "iterations_per_question_per_method": iterations,
            "warmup_per_question_per_method": warmup,
            "k": k, "random_seed": seed,
            "embedding_model": EMBEDDING_MODEL, "mariadb_version": version,
            "article_count": articles, "chunk_count": chunks,
            "timing_scope": "database SQL execute and fetchall; excludes embedding generation",
            "reference": "full scan with IGNORE INDEX (embedding)",
        },
        "summary": {
            "indexed": stats(timings["indexed"]),
            "exact": stats(timings["exact"]),
            "speedup_mean": round(exact_mean / indexed_mean, 3) if indexed_mean else None,
            "mean_recall_at_k_vs_exact": round(statistics.mean(recalls), 4) if recalls else None,
        },
        "explain": {"indexed": indexed_plan, "exact": exact_plan},
        "per_question": per_question,
    }
    dest = Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Full report and EXPLAIN plans: {dest}")
    print("Inspect EXPLAIN: an indexed SQL formulation does not guarantee the optimizer chose HNSW.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/evaluation.json")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="Max unique questions; 0 means all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="reports/hnsw-benchmark.json")
    args = parser.parse_args()
    benchmark(args.dataset, args.iterations, args.warmup, args.k,
              args.limit, args.seed, args.output)


if __name__ == "__main__":
    main()
