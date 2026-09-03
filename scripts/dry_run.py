"""End-to-end dry run with NO external deps (no build123d, no API keys).

Wires MockLLM + MockExecutor so the full path — schema -> agent -> executor -> grader -> metrics —
runs offline. It includes a "good" model (passes) and a "sloppy" model that reports DONE on a valid
but dimensionally wrong solid, so the silent-failure metric lights up. Proves the plumbing before any
real model or kernel is involved.

    cd 10-agentic-cad-reliability && python scripts/dry_run.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.schema import load_suite                       # noqa: E402
from benchmark.llm import MockLLM                             # noqa: E402
from benchmark.executor import MockExecutor                   # noqa: E402
from benchmark.agents import SingleShotAgent, ToolUseAgent    # noqa: E402
from benchmark.runner import run_suite, AgentSpec             # noqa: E402
from benchmark.metrics import summarize                       # noqa: E402


def _bolts(pcd=95.0, r=5.5, n=6, z=7.0):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        out.append({"radius": r, "height": 14,
                    "center": [round(pcd / 2 * math.cos(a), 3), round(pcd / 2 * math.sin(a), 3), z],
                    "axis": [0, 0, 1]})
    return out


FLANGE_CYL = [{"radius": 60, "height": 14, "center": [0, 0, 7], "axis": [0, 0, 1]},
              {"radius": 20, "height": 14, "center": [0, 0, 7], "axis": [0, 0, 1]}, *_bolts()]
SHAFT_CYL = [{"radius": 20, "height": 80, "center": [0, 0, 60], "axis": [0, 0, 1]},
             {"radius": 15, "height": 20, "center": [0, 0, 10], "axis": [0, 0, 1]},
             {"radius": 15, "height": 20, "center": [0, 0, 110], "axis": [0, 0, 1]}]

PASS_T1 = {"valid_solid": True, "watertight": True, "volume": 132000, "bbox": [120, 120, 14],
           "bbox_center": [0, 0, 7], "com": [0, 0, 7], "solid_count": 1,
           "face_count": 30, "edge_count": 60, "cylinders": FLANGE_CYL}
SILENT_T1 = {**PASS_T1, "bbox": [120, 120, 10]}          # thickness 10≠14 -> fails, but reported DONE
PASS_T2 = {"valid_solid": True, "watertight": True, "volume": 128000, "bbox": [40, 40, 120],
           "bbox_center": [0, 0, 60], "com": [0, 0, 60], "solid_count": 1,
           "face_count": 12, "edge_count": 18, "cylinders": SHAFT_CYL}
SILENT_T2 = {**PASS_T2, "bbox": [40, 40, 100]}           # length 100≠120 -> fails, but reported DONE


def reply(marker: str, conf: float) -> str:
    return f"DONE\nCONFIDENCE: {conf}\n```python\n# {marker}\nresult = object()\n```"


def main() -> None:
    tasks = load_suite(ROOT / "tasks")
    executor = MockExecutor(props_by_marker={
        "PASS-T1": PASS_T1, "SILENT-T1": SILENT_T1, "PASS-T2": PASS_T2, "SILENT-T2": SILENT_T2,
    })
    good = MockLLM(name="good-model", replies={
        "T1-flange-6bolt": reply("PASS-T1", 0.92), "T2-stepped-shaft": reply("PASS-T2", 0.88)})
    sloppy = MockLLM(name="sloppy-model", replies={
        "T1-flange-6bolt": reply("SILENT-T1", 0.80), "T2-stepped-shaft": reply("SILENT-T2", 0.75)})

    specs = [
        AgentSpec(SingleShotAgent(good), good.name),
        AgentSpec(SingleShotAgent(sloppy), sloppy.name),
        AgentSpec(ToolUseAgent(good), good.name),
    ]
    out = ROOT / "data" / "dry_run_results.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    records = run_suite(tasks, specs, executor, seeds=1, out_path=out)

    print(f"Ran {len(records)} attempts over {len(tasks)} tasks.\n")
    print(json.dumps(summarize(records), indent=2))
    print(f"\nPer-attempt log -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
