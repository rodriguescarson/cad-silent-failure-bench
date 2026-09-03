"""Regrade every stored attempt under the current (hardened) oracle — offline, no API.

Re-executes each record's stored code through Build123dExecutor, regrades against the current
task JSONs, and writes data/regraded_<original-name>. Original agent-side fields (reported_done,
confidence, steps, tokens, cds) are preserved; passed / valid_solid / score / failed_checks are
recomputed. Records whose code no longer executes identically are graded on the fresh execution
(deterministic geometry — build123d is deterministic given the code).

Usage:  .venv/bin/python scripts/regrade.py [--glob "full_*.jsonl"]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.executor import Build123dExecutor  # noqa: E402
from benchmark.grader import grade  # noqa: E402
from benchmark.schema import load_suite  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="full_*.jsonl")
    args = ap.parse_args()

    tasks = {t.id: t for t in load_suite(ROOT / "tasks")}
    executor = Build123dExecutor()
    cache: dict[str, dict | None] = {}  # identical code strings re-execute once
    changed = 0
    total = 0

    for f in sorted((ROOT / "data").glob(args.glob)):
        if f.name.startswith("regraded_"):
            continue
        out_path = f.parent / f"regraded_{f.name}"
        with open(out_path, "w") as out:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                total += 1
                if (r.get("error") or "").startswith("attempt aborted"):
                    out.write(json.dumps(r) + "\n")
                    continue
                task = tasks[r["task_id"]]
                code = r.get("code") or ""
                if code:
                    if code not in cache:
                        cache[code] = executor.run(code).props
                    props = cache[code]
                else:
                    props = None
                g = grade(task, props)
                old_passed = r.get("passed")
                r["passed"] = g.passed
                r["valid_solid"] = g.valid_solid
                r["score"] = round(g.score, 4)
                r["failed_checks"] = [c.id for c in g.failed_checks()]
                r["regraded"] = True
                r["passed_old_oracle"] = old_passed
                if g.passed != old_passed:
                    changed += 1
                out.write(json.dumps(r) + "\n")
        print(f"regraded {f.name} -> {out_path.name}")
    print(f"\n{total} attempts regraded; verdict changed on {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
