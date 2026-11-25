"""Compare retrieval configurations without changing production defaults."""
import json
import os
from pathlib import Path
from src.evaluation import run_evaluation

def main():
    reports = Path("reports")
    reports.mkdir(exist_ok=True)
    summary = {}
    for name, pool, cap in [("baseline", 5, 2), ("diverse", 10, 1), ("wide", 10, 2)]:
        os.environ["RAG_POOL_FACTOR"] = str(pool)
        os.environ["RAG_ARTICLE_CAP"] = str(cap)
        result = run_evaluation("data/evaluation-expanded.json", 5, False)
        result["configuration"] = {"pool_factor": pool, "article_cap": cap}
        (reports / f"retrieval-comparison-{name}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        summary[name] = result["summary"]
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
