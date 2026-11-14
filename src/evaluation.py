"""Metrics and live runner for the end-to-end RAG evaluation."""
from __future__ import annotations

import json
import math
import re
import statistics
import time
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+")
CITATION_RE = re.compile(r"\[Source\s+(\d+)\]", re.IGNORECASE)


def _norm(value):
    return " ".join(TOKEN_RE.findall(value.lower()))


def retrieval_metrics(results, expected_titles, k=5):
    """Article-level metrics; repeated chunks from one article count once."""
    expected = {_norm(title) for title in expected_titles}
    ranked = []
    seen = set()
    for row in results:
        title = _norm(row.get("title", ""))
        if title and title not in seen:
            ranked.append(title)
            seen.add(title)
        if len(ranked) >= k:
            break
    hits = [title in expected for title in ranked]
    found = sum(hits)
    dcg = sum(1 / math.log2(rank + 2) for rank, hit in enumerate(hits) if hit)
    ideal = sum(1 / math.log2(rank + 2)
                for rank in range(min(len(expected), len(ranked), k)))
    reciprocal_rank = next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0.0)
    return {
        f"precision@{k}": found / len(ranked) if ranked else 0.0,
        f"recall@{k}": found / len(expected) if expected else 0.0,
        f"mrr@{k}": reciprocal_rank,
        f"ndcg@{k}": dcg / ideal if ideal else 0.0,
        "relevant_retrieved": found,
    }


def answer_metrics(answer, key_points, retrieved_count):
    """Simple transparent proxy metrics; semantic correctness still needs review."""
    normalized = _norm(answer)
    points = [_norm(point) for point in key_points]
    covered = [p for p in points if p and p in normalized]
    citations = [int(n) for n in CITATION_RE.findall(answer)]
    valid = [n for n in citations if 1 <= n <= retrieved_count]
    return {
        "key_point_coverage": len(covered) / len(points) if points else 0.0,
        "key_points_covered": len(covered),
        "citation_count": len(citations),
        "citation_validity": len(valid) / len(citations) if citations else 0.0,
        "has_citation": bool(citations),
        "invalid_citations": sum(n < 1 or n > retrieved_count for n in citations),
    }


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _summary(values):
    return {
        "mean_ms": round(statistics.mean(values), 2) if values else None,
        "median_ms": round(statistics.median(values), 2) if values else None,
        "p95_ms": round(_percentile(values, .95), 2) if values else None,
    }


def run_evaluation(dataset_path, k=5, include_generation=True):
    """Run dataset against real MariaDB retrieval and optionally local Ollama."""
    from src.search import search
    from src.generation import generate_answer

    cases = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        row = {"id": case["id"], "question": case["question"], "ok": False}
        started = time.perf_counter()
        try:
            results, search_reported_ms = search(case["question"], k, case.get("category"))
            row.update(retrieval_metrics(results, case["expected_titles"], k))
            row["retrieval_ms"] = round(search_reported_ms, 2)
            row["retrieved_titles"] = [r.get("title") for r in results]
            if include_generation:
                gen_start = time.perf_counter()
                answer = generate_answer(case["question"], results)
                row["generation_ms"] = round((time.perf_counter() - gen_start) * 1000, 2)
                row["answer"] = answer
                row.update(answer_metrics(answer, case.get("key_points", []), len(results)))
            row["ok"] = True
        except Exception as exc:  # retain failures in reliability metrics
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)

    successful = [r for r in rows if r["ok"]]
    metric_names = [f"precision@{k}", f"recall@{k}", f"mrr@{k}", f"ndcg@{k}"]
    summary = {
        "cases": len(rows),
        "successful": len(successful),
        "failure_rate": (len(rows) - len(successful)) / len(rows) if rows else 0.0,
        "retrieval_metrics": {name: round(statistics.mean(r[name] for r in successful if name in r), 4)
                              if any(name in r for r in successful) else None for name in metric_names},
        "retrieval_latency": _summary([r["retrieval_ms"] for r in successful if "retrieval_ms" in r]),
        "total_latency": _summary([r["total_ms"] for r in rows]),
    }
    if include_generation:
        summary["answer_key_point_coverage"] = round(statistics.mean(
            r["key_point_coverage"] for r in successful if "key_point_coverage" in r), 4) if successful else None
        all_citations = [r for r in successful if "citation_validity" in r]
        summary["citation_validity"] = round(statistics.mean(r["citation_validity"] for r in all_citations), 4) if all_citations else None
        summary["citation_presence"] = round(statistics.mean(float(r["has_citation"]) for r in all_citations), 4) if all_citations else None
        summary["generation_latency"] = _summary([r["generation_ms"] for r in successful if "generation_ms" in r])
    return {"summary": summary, "results": rows}
