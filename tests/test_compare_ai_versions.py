import contextlib
import io
import os
import unittest

from scripts.compare_ai_versions import compare_reports, main

FIXTURE_DIR = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "compare_ai_versions",
)


def _report(
    engine,
    passed,
    total,
    avg_elapsed_seconds,
    nodes,
    completed_depth,
):
    return {
        "engine": engine,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total,
        "avg_elapsed_seconds": avg_elapsed_seconds,
        "results": [
            {
                "position_id": f"position_{index}",
                "passed": index < passed,
                "elapsed_seconds": avg_elapsed_seconds,
                "reason": "passed",
                "decision_reason": "alpha_beta_search",
                "search_nodes": nodes,
                "completed_depth": completed_depth,
            }
            for index in range(total)
        ],
    }


class CompareAIVersionsTests(unittest.TestCase):
    def test_compares_benchmark_report_metrics(self):
        old_report = _report(
            engine="alpha_belta_max_old",
            passed=1,
            total=2,
            avg_elapsed_seconds=0.2,
            nodes=100,
            completed_depth=2,
        )
        new_report = _report(
            engine="alpha_belta_max_new",
            passed=2,
            total=2,
            avg_elapsed_seconds=0.3,
            nodes=120,
            completed_depth=3,
        )

        comparison = compare_reports(old_report, new_report)

        self.assertEqual(comparison["old_engine"], "alpha_belta_max_old")
        self.assertEqual(comparison["new_engine"], "alpha_belta_max_new")
        self.assertEqual(comparison["pass_rate_delta"], 0.5)
        self.assertEqual(comparison["avg_elapsed_seconds_delta"], 0.1)
        self.assertEqual(comparison["avg_search_nodes_delta"], 20.0)
        self.assertEqual(comparison["avg_completed_depth_delta"], 1.0)
        self.assertFalse(comparison["pass_rate_regressed"])

    def test_cli_returns_nonzero_when_pass_rate_regresses(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    os.path.join(FIXTURE_DIR, "old_full_pass.json"),
                    os.path.join(FIXTURE_DIR, "new_regressed.json"),
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn('"pass_rate_regressed": true', output.getvalue())


if __name__ == "__main__":
    unittest.main()
