"""Grader calibration: every task's reference solution must pass every check.

Runs each tasks/*.json through Build123dExecutor using its `reference_solution` code and grades the
measured properties. A known-good part failing a check means the tolerance or extractor heuristic is
wrong — fix that before trusting agent scores (HARNESS.md step 2). Exits nonzero on any failure.

Usage:  .venv/bin/python scripts/calibrate.py [tasks_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.executor import Build123dExecutor
from benchmark.grader import grade
from benchmark.schema import load_suite


def main() -> int:
    tasks_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tasks"
    tasks = load_suite(tasks_dir)
    executor = Build123dExecutor()
    failures = 0

    for task in tasks:
        if not task.reference_solution:
            print(f"SKIP  {task.id}: no reference_solution")
            failures += 1
            continue
        ref = (ROOT / task.reference_solution).resolve()
        if not ref.exists():
            ref = (tasks_dir / task.reference_solution).resolve()
        if not ref.exists():
            print(f"SKIP  {task.id}: missing {ref}")
            failures += 1
            continue
        result = executor.run(ref.read_text())
        if not result.valid:
            print(f"FAIL  {task.id}: executor error: {result.error}")
            failures += 1
            continue
        g = grade(task, result.props)
        status = "ok  " if g.passed else "FAIL"
        print(f"{status}  {task.id}  score={g.score:.2f}")
        for c in g.checks:
            mark = "ok" if c.passed else "XX"
            print(f"        {mark}  {c.id}: {c.reason}")
        if not g.passed:
            failures += 1

    print(f"\n{len(tasks) - failures}/{len(tasks)} reference solutions pass all checks")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
