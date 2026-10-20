#!/usr/bin/env python3
"""Gate for the final `ci` job: pass only when every job it needs succeeded.

Reads the `needs` context as JSON from the NEEDS environment variable
(`NEEDS: ${{ toJSON(needs) }}`). A failed, cancelled or skipped job fails the
gate, and so does an empty `needs`. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys


def problems(needs_json: str) -> list[str]:
    """Return one line per needed job that did not succeed (empty when all passed)."""
    needs = json.loads(needs_json)
    if not needs:
        return ["the ci job needs no jobs"]
    return [
        f"{job}: {need['result']}" for job, need in needs.items() if need["result"] != "success"
    ]


def main() -> int:
    found = problems(os.environ["NEEDS"])
    for line in found:
        print(f"Not passed: {line}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
