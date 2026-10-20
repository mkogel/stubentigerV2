"""Tests for scripts/all_jobs_passed.py, the gate behind the final `ci` job.

Run: python -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import all_jobs_passed  # noqa: E402


def needs(**results: str) -> str:
    """The `needs` context as `toJSON(needs)` renders it."""
    return json.dumps({job: {"result": r, "outputs": {}} for job, r in results.items()})


class AllJobsPassedTest(unittest.TestCase):
    def test_every_job_succeeded_passes(self) -> None:
        self.assertEqual(
            all_jobs_passed.problems(needs(lint="success", **{"build-test": "success"})), []
        )

    def test_failed_cancelled_or_skipped_job_fails(self) -> None:
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(result=result):
                self.assertEqual(
                    all_jobs_passed.problems(needs(lint="success", sim=result)),
                    [f"sim: {result}"],
                )

    def test_no_needed_jobs_fails(self) -> None:
        self.assertEqual(all_jobs_passed.problems("{}"), ["the ci job needs no jobs"])


if __name__ == "__main__":
    unittest.main()
