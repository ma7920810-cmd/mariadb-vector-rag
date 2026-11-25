"""Sweep HNSW M and search width on an isolated copy of the ingested corpus."""
import argparse
import json
import time
import statistics
from pathlib import Path
from benchmark import questions_from_dataset, run_query, stats
from src.db import connect, vector_literal
from src.embeddings import embed_query

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--m", nargs="+", type=int, default=[6, 12, 24, 48])
    p.add_argument("--width", nargs="+", type=int, default=[20, 50, 100, 200])
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--dataset", default="data/evaluation.json")
    p.add_argument("--output", default="reports/hnsw-sweep.json")
    a = p.parse_args()
    if any(not 3 <= m <= 200 for m in a.m) or min(a.width) < 1 or min(a.k, a.iterations) < 1:
        p.error("Invalid sweep parameters")
    vectors = [vector_literal(embed_query(q)) for q in questions_from_dataset(a.dataset, 0)]
    report = {"configuration": vars(a), "results": []}
    # Dedicated table; never alter the application index.
    import uuid
    table = "hnsw_sweep_" + uuid.uuid4().hex
    with connect() as conn:
        c = conn.cursor()
        c.execute("SELECT VERSION()")
        report["version"] = c.fetchone()[0]
        c.execute(f"CREATE TABLE {table} (id BIGINT UNSIGNED PRIMARY KEY, embedding VECTOR(384) NOT NULL) ENGINE=InnoDB")
        try:
            c.execute(f"INSERT INTO {table} SELECT id, embedding FROM chunks")
            conn.commit()
            c.execute(f"SELECT COUNT(*) FROM {table}")
            report["chunks"] = c.fetchone()[0]
            if report["chunks"] < a.k:
                raise RuntimeError("Ingest corpus first")
            sql = f"SELECT id, VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) AS distance FROM {table} ORDER BY distance LIMIT ?"
            exact = [run_query(c, sql, v, a.k) for v in vectors]
            report["exact_latency"] = stats([ms for _, ms in exact])
            for m in a.m:
                start = time.perf_counter()
                c.execute(f"ALTER TABLE {table} ADD VECTOR INDEX sweep_embedding (embedding) M={m} DISTANCE=cosine")
                build = time.perf_counter() - start
                for width in a.width:
                    c.execute(f"SET SESSION mhnsw_ef_search = {width}")
                    c.execute("EXPLAIN " + sql, (vectors[0], a.k))
                    plan = [list(map(str, row)) for row in c.fetchall()]
                    recalls, times = [], []
                    for v, (truth, _) in zip(vectors, exact):
                        run_query(c, sql, v, a.k)
                        for _ in range(a.iterations):
                            ids, ms = run_query(c, sql, v, a.k)
                            recalls.append(len(set(ids) & set(truth)) / len(truth))
                            times.append(ms)
                    row = {"m": m, "ef_search": width, "build_seconds": build,
                           "recall_vs_exact": statistics.mean(recalls), "latency": stats(times),
                           "explain": plan}
                    report["results"].append(row)
                    print(json.dumps(row), flush=True)
                c.execute(f"ALTER TABLE {table} DROP INDEX sweep_embedding")
        finally:
            c.execute(f"DROP TABLE {table}")
    dest = Path(a.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
