"""Pure-python grader/metrics tests. Run with `pytest`, or standalone: `python tests/test_grader.py`."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.schema import load_task                         # noqa: E402
from benchmark.grader import grade                             # noqa: E402
from benchmark.metrics import silent_failure_rate, success_rate, success_at_k  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _bolts(pcd=95.0, r=5.5, n=6, z=7.0, h=14.0):
    return [{"radius": r, "height": h,
             "center": [pcd / 2 * math.cos(2 * math.pi * i / n),
                        pcd / 2 * math.sin(2 * math.pi * i / n), z], "axis": [0, 0, 1]}
            for i in range(n)]


GOOD_FLANGE = {
    "valid_solid": True, "watertight": True, "volume": 132000, "bbox": [120, 120, 14],
    "bbox_center": [0, 0, 7], "com": [0, 0, 7], "solid_count": 1,
    "face_count": 30, "edge_count": 60,
    "cylinders": [{"radius": 60, "height": 14, "center": [0, 0, 7], "axis": [0, 0, 1]},
                  {"radius": 20, "height": 14, "center": [0, 0, 7], "axis": [0, 0, 1]}, *_bolts()],
}


def test_good_flange_passes():
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    g = grade(task, GOOD_FLANGE)
    assert g.passed, [c.reason for c in g.failed_checks()]
    assert g.score == 1.0


def test_wrong_thickness_fails_only_thickness():
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    g = grade(task, {**GOOD_FLANGE, "bbox": [120, 120, 10]})
    assert not g.passed
    assert {c.id for c in g.failed_checks()} == {"thickness"}
    assert g.valid_solid  # still a renderable solid -> a *silent* failure if reported done


def test_missing_bore_fails_bore():
    props = {**GOOD_FLANGE, "cylinders": [c for c in GOOD_FLANGE["cylinders"] if c["radius"] != 20]}
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    g = grade(task, props)
    assert "bore" in {c.id for c in g.failed_checks()}


def test_bolt_circle_wrong_pcd_fails():
    bad = {**GOOD_FLANGE, "cylinders": [{"radius": 60, "center": [0, 0, 7], "axis": [0, 0, 1]},
                                        {"radius": 20, "center": [0, 0, 7], "axis": [0, 0, 1]},
                                        *_bolts(pcd=70)]}
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    g = grade(task, bad)
    assert "bolts" in {c.id for c in g.failed_checks()}


def test_no_props_fails_all():
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    g = grade(task, None)
    assert not g.passed and not g.valid_solid and g.score == 0.0


def test_metrics_silent_failure():
    recs = [
        {"task_id": "T1", "model": "m", "condition": "single_shot", "passed": True,
         "valid_solid": True, "reported_done": True},
        {"task_id": "T1", "model": "m", "condition": "single_shot", "passed": False,
         "valid_solid": True, "reported_done": True},   # silent failure
        {"task_id": "T1", "model": "m", "condition": "single_shot", "passed": False,
         "valid_solid": False, "reported_done": True},  # not silent (didn't render)
    ]
    assert math.isclose(success_rate(recs), 1 / 3)
    assert math.isclose(silent_failure_rate(recs), 1 / 3)
    assert math.isclose(success_at_k(recs), 1.0)  # one of the attempts passed


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
