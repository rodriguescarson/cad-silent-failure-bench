"""Offline tests for the MultiAgent (planner->coder->checker) condition and CDS instrumentation.

Pure python — MockLLM + MockExecutor, no kernel, no keys. Run standalone or via pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.agents import MultiAgent, _cds_round, _dims_disagreement, _parse_dims  # noqa: E402
from benchmark.executor import MockExecutor  # noqa: E402
from benchmark.llm import MockLLM  # noqa: E402
from benchmark.schema import load_task  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

GOOD_PROPS = {
    "valid_solid": True, "watertight": True, "volume": 132000, "bbox": [120, 120, 14],
    "com": [0, 0, 7], "solid_count": 1, "face_count": 10, "edge_count": 48,
    "cylinders": [{"radius": 20, "center": [0, 0, 7], "axis": [0, 0, 1], "height": 14}],
}

PLANNER_REPLY = ("1. Disc.\n2. Bore.\n3. Bolt circle.\n"
                 'DIMS: {"od": 120, "bore": 40, "thickness": 14}')
CODER_REPLY = ("```python\n# TASK-T1 marker\nresult = None\n```\n"
               'DIMS: {"od": 120, "bore": 40, "thickness": 14}')
CHECKER_PASS = ('VERDICT: PASS\nLooks within spec.\n'
                'DIMS: {"od": 120, "bore": 40, "thickness": 14}\nCONFIDENCE: 0.9')
CHECKER_REVISE = ('VERDICT: REVISE\nBore measures 30, spec says 40 - enlarge it.\n'
                  'DIMS: {"od": 120, "bore": 30, "thickness": 14}\nCONFIDENCE: 0.4')


def _agent(checker_reply: str) -> MultiAgent:
    llm = MockLLM({
        "[PLANNER]": PLANNER_REPLY,
        "[CODER]": CODER_REPLY,
        "[CHECKER]": checker_reply,
    })
    return MultiAgent(llm, max_rounds=3)


def test_parse_dims():
    assert _parse_dims('DIMS: {"a": 1, "b": 2.5}') == {"a": 1.0, "b": 2.5}
    assert _parse_dims("no dims here") == {}
    assert _parse_dims('DIMS: {broken json') == {}


def test_dims_disagreement():
    a = {"od": 120.0, "th": 14.0}
    assert _dims_disagreement(a, {"od": 120.0, "th": 14.0}) == 0.0
    assert _dims_disagreement(a, {"od": 100.0, "th": 14.0}) == 0.5   # od off by far
    assert _dims_disagreement(a, {"od": 120.0}) == 0.5               # missing key = disagreement
    assert _dims_disagreement({}, {}) is None


def test_cds_round_aligned_vs_drifted():
    aligned = _cds_round({"od": 120.0}, {"od": 120.0}, {"od": 120.0})
    drifted = _cds_round({"od": 120.0}, {"od": 120.0}, {"od": 90.0})
    assert aligned == 0.0
    assert drifted is not None and drifted > 0.3


def test_pass_verdict_ends_episode_done():
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    ex = MockExecutor(props_by_marker={"TASK-T1": GOOD_PROPS})
    out = _agent(CHECKER_PASS).run(task, ex)
    assert out.reported_done is True
    assert out.steps == 1
    assert out.confidence == 0.9
    assert out.props == GOOD_PROPS
    assert out.cds == [0.0]   # all three agents stated identical DIMS


def test_revise_exhausts_rounds_not_done():
    task = load_task(ROOT / "tasks" / "T1-flange-6bolt.json")
    ex = MockExecutor(props_by_marker={"TASK-T1": GOOD_PROPS})
    out = _agent(CHECKER_REVISE).run(task, ex)
    assert out.reported_done is False     # checker never passed -> system does NOT claim done
    assert out.steps == 3                 # max_rounds exhausted
    assert out.cds is not None and len(out.cds) == 3
    assert all(v > 0 for v in out.cds)    # checker's bore=30 disagrees with planner/coder 40


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
                fails += 1
    print(f"\n{'FAILED' if fails else 'all multi-agent tests passed'}")
    raise SystemExit(1 if fails else 0)
