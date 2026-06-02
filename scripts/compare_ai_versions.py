"""Compare two fixed-position AI benchmark reports."""

from __future__ import annotations

import argparse
import json
from typing import Iterable, Mapping, Sequence


def _pass_rate(report: Mapping[str, object]) -> float:
    if "pass_rate" in report:
        return float(report["pass_rate"])
    total = int(report.get("total", 0))
    return float(report.get("passed", 0)) / total if total else 0.0


def _average_result_field(
    results: Iterable[Mapping[str, object]],
    field: str,
) -> float:
    values = [float(result.get(field, 0)) for result in results]
    return sum(values) / len(values) if values else 0.0


def _rounded_delta(new_value: float, old_value: float) -> float:
    return round(new_value - old_value, 6)


def load_report(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compare_reports(
    old_report: Mapping[str, object],
    new_report: Mapping[str, object],
) -> dict:
    old_results = list(old_report.get("results", []))
    new_results = list(new_report.get("results", []))

    old_pass_rate = _pass_rate(old_report)
    new_pass_rate = _pass_rate(new_report)
    old_elapsed = float(old_report.get("avg_elapsed_seconds", 0.0))
    new_elapsed = float(new_report.get("avg_elapsed_seconds", 0.0))
    old_nodes = _average_result_field(old_results, "search_nodes")
    new_nodes = _average_result_field(new_results, "search_nodes")
    old_depth = _average_result_field(old_results, "completed_depth")
    new_depth = _average_result_field(new_results, "completed_depth")

    return {
        "old_engine": str(old_report.get("engine", "")),
        "new_engine": str(new_report.get("engine", "")),
        "old_pass_rate": old_pass_rate,
        "new_pass_rate": new_pass_rate,
        "pass_rate_delta": _rounded_delta(new_pass_rate, old_pass_rate),
        "avg_elapsed_seconds_delta": _rounded_delta(new_elapsed, old_elapsed),
        "avg_search_nodes_delta": _rounded_delta(new_nodes, old_nodes),
        "avg_completed_depth_delta": _rounded_delta(new_depth, old_depth),
        "pass_rate_regressed": new_pass_rate < old_pass_rate,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("old_report")
    parser.add_argument("new_report")
    args = parser.parse_args(argv)

    comparison = compare_reports(
        load_report(args.old_report),
        load_report(args.new_report),
    )
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 1 if comparison["pass_rate_regressed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
