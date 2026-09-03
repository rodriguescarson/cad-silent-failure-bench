"""Aggregate run records into the paper's headline metrics.

A *record* (one attempt) is a dict:
    {task_id, model, condition, seed, attempt,
     reported_done: bool, confidence: float|None,
     passed: bool, valid_solid: bool, score: float,
     tokens: int, tool_calls: int, steps: int, error: str|None}

Headline metrics:
    success_rate         fraction of attempts that pass all checks
    success_at_k         per (task,model,condition): pass if ANY of k attempts passes; averaged
    silent_failure_rate  fraction of attempts where the agent reported "done" on a *valid, renderable*
                         solid that nonetheless fails >=1 check  <-- the paper's headline hazard
    calibration_gap      mean |reported-correct| ... reliability-diagram inputs (ECE) when confidence present
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean


def success_rate(records: list[dict]) -> float:
    return mean([1.0 if r["passed"] else 0.0 for r in records]) if records else 0.0


def silent_failure_rate(records: list[dict]) -> float:
    """Reported done + valid renderable solid + fails the spec. The dangerous, over-delegation case."""
    if not records:
        return 0.0
    flags = [
        1.0 if (r.get("reported_done") and r.get("valid_solid") and not r["passed"]) else 0.0
        for r in records
    ]
    return mean(flags)


def success_at_k(records: list[dict]) -> float:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        groups[(r["task_id"], r["model"], r["condition"])].append(r)
    per_group = [1.0 if any(r["passed"] for r in g) else 0.0 for g in groups.values()]
    return mean(per_group) if per_group else 0.0


def expected_calibration_error(records: list[dict], bins: int = 5) -> float | None:
    """Equal-mass binned ECE (same definition as scripts/analyze.py and the paper)."""
    pts = [(float(r["confidence"]), 1.0 if r["passed"] else 0.0)
           for r in records if r.get("confidence") is not None]
    if len(pts) < bins:
        return None
    pts.sort()
    size = len(pts) / bins
    buckets = [pts[round(i * size):round((i + 1) * size)] for i in range(bins)]
    n = len(pts)
    ece = 0.0
    for b in buckets:
        if not b:
            continue
        avg_conf = mean(c for c, _ in b)
        acc = mean(y for _, y in b)
        ece += (len(b) / n) * abs(avg_conf - acc)
    return ece


def summarize(records: list[dict]) -> dict:
    by_cond: dict[str, list[dict]] = defaultdict(list)
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_cond[r["condition"]].append(r)
        by_model[r["model"]].append(r)
    return {
        "n": len(records),
        "overall": {
            "success_rate": round(success_rate(records), 4),
            "success_at_k": round(success_at_k(records), 4),
            "silent_failure_rate": round(silent_failure_rate(records), 4),
            "ece": expected_calibration_error(records),
        },
        "by_condition": {
            c: {
                "success_rate": round(success_rate(rs), 4),
                "silent_failure_rate": round(silent_failure_rate(rs), 4),
                "mean_steps": round(mean([r.get("steps", 1) for r in rs]), 2),
            }
            for c, rs in sorted(by_cond.items())
        },
        "by_model": {
            m: {
                "success_rate": round(success_rate(rs), 4),
                "silent_failure_rate": round(silent_failure_rate(rs), 4),
            }
            for m, rs in sorted(by_model.items())
        },
    }
