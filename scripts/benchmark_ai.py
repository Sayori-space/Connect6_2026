"""Run fixed-position benchmarks for Connect6 AI engines."""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import csv
import io
import json
import os
import sys
from typing import List

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.evaluation import AIPositionResult, evaluate_position, load_position_fixtures
from ai.factory import build_ai
from models.game_config import GameConfig


@dataclass(frozen=True)
class PositionSuiteReport:
    engine: str
    total: int
    passed: int
    failed: int
    avg_elapsed_seconds: float
    results: List[AIPositionResult]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "avg_elapsed_seconds": self.avg_elapsed_seconds,
            "results": [
                {
                    "position_id": result.position_id,
                    "passed": result.passed,
                    "selected_cells": sorted(result.selected_cells),
                    "elapsed_seconds": result.elapsed_seconds,
                    "reason": result.reason,
                    "decision_reason": result.decision_reason,
                    "search_nodes": result.search_nodes,
                    "completed_depth": result.completed_depth,
                }
                for result in self.results
            ],
        }

    def to_csv(self) -> str:
        handle = io.StringIO()
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "engine",
                "position_id",
                "passed",
                "elapsed_seconds",
                "reason",
                "selected_cells",
                "decision_reason",
                "search_nodes",
                "completed_depth",
            ]
        )
        for result in self.results:
            writer.writerow(
                [
                    self.engine,
                    result.position_id,
                    "true" if result.passed else "false",
                    f"{result.elapsed_seconds:.6f}",
                    result.reason,
                    ";".join(
                        f"{row}:{col}"
                        for row, col in sorted(result.selected_cells)
                    ),
                    result.decision_reason,
                    result.search_nodes,
                    result.completed_depth,
                ]
            )
        return handle.getvalue()


def run_position_suite(fixture_dir: str, engine: str) -> PositionSuiteReport:
    positions = load_position_fixtures(fixture_dir)
    ai = build_ai(GameConfig(ai_type=engine))
    results = [evaluate_position(position, ai) for position in positions]
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed
    avg_elapsed = (
        sum(result.elapsed_seconds for result in results) / total
        if total
        else 0.0
    )
    return PositionSuiteReport(
        engine=engine,
        total=total,
        passed=passed,
        failed=failed,
        avg_elapsed_seconds=avg_elapsed,
        results=results,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_dir")
    parser.add_argument("--engine", default="alpha_belta_max")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args()

    report = run_position_suite(args.fixture_dir, args.engine)
    if args.format == "csv":
        print(report.to_csv(), end="")
    else:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
