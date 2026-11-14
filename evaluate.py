"""Run the live RAG evaluation and write JSON/CSV results."""
import argparse
import csv
import json
from pathlib import Path

from src.evaluation import run_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/evaluation.json")
    parser.add_argument("--output", default="evaluation-results")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-only", action="store_true",
                        help="skip Ollama generation; evaluate retrieval only")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be at least 1")
    report = run_evaluation(args.dataset, args.k, not args.retrieval_only)
    stem = Path(args.output)
    stem.parent.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = stem.with_suffix(".json"), stem.with_suffix(".csv")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    fields = sorted({key for row in report["results"] for key in row})
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["results"])
    print(json.dumps(report["summary"], indent=2))
    print(f"Detailed results: {json_path} and {csv_path}")
    if report["summary"]["failure_rate"]:
        print("Some cases failed; see the per-question error field in the report.")


if __name__ == "__main__":
    main()
