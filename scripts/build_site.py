"""Build the static results-viewer site: STL assets + site/data.js.

Offline — no API keys. Re-executes the per-attempt code stored in data/*.jsonl (and each task's
reference solution) through benchmark._extract to export STLs, then writes site/data.js with the
attempt records and leaderboard aggregates. Serve with:  python -m http.server -d site

Usage:  .venv/bin/python scripts/build_site.py [--no-stl]
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.schema import load_suite  # noqa: E402

SITE = ROOT / "site"
MODELS = SITE / "models"
DATA_GLOBS = ["primary_population.jsonl", "regraded_full_gpt55.jsonl", "ablation_legacy_haiku.jsonl", "ablation_legacy_deepseek.jsonl"]  # paper populations; pilot_* for the old pilot view


def export_stl(code: str, out: Path) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "benchmark._extract", tmp, str(out)],
            capture_output=True, text=True, timeout=90, cwd=str(ROOT),
        )
        return out.exists() and proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    do_stl = "--no-stl" not in sys.argv
    MODELS.mkdir(parents=True, exist_ok=True)

    tasks = load_suite(ROOT / "tasks")
    task_meta = {}
    for t in tasks:
        ref_rel = None
        if do_stl and t.reference_solution:
            ref_path = ROOT / t.reference_solution
            out = MODELS / f"ref_{t.id}.stl"
            if ref_path.exists() and (out.exists() or export_stl(ref_path.read_text(), out)):
                ref_rel = f"models/{out.name}"
                print(f"ref   {t.id}: {out.name}")
        task_meta[t.id] = {"id": t.id, "tier": t.tier, "title": t.title,
                           "nl_spec": t.nl_spec, "ref_stl": ref_rel,
                           "n_checks": len(t.checks)}

    records = []
    for pattern in DATA_GLOBS:
        for f in sorted((ROOT / "data").glob(pattern)):
            for line in f.read_text().splitlines():
                if line.strip():
                    records.append(json.loads(line))

    attempts = []
    for i, r in enumerate(records):
        silent = bool(r.get("reported_done") and r.get("valid_solid") and not r.get("passed"))
        stl_rel = None
        if do_stl and r.get("code"):
            out = MODELS / f"a{i:03d}.stl"
            if out.exists() or export_stl(r["code"], out):
                stl_rel = f"models/{out.name}"
        status = "pass" if r.get("passed") else ("silent" if silent else "fail")
        attempts.append({
            "id": f"a{i:03d}", "task": r["task_id"], "tier": r.get("tier"),
            "model": r["model"], "condition": r["condition"], "seed": r.get("seed"),
            "status": status, "passed": bool(r.get("passed")), "silent": silent,
            "reported_done": bool(r.get("reported_done")),
            "confidence": r.get("confidence"), "steps": r.get("steps"),
            "failed_checks": r.get("failed_checks") or [],
            "error": (r.get("error") or "")[:300] or None,
            "cds": r.get("cds"), "code": r.get("code") or "",
            "stl": stl_rel, "ref_stl": task_meta.get(r["task_id"], {}).get("ref_stl"),
        })
        if stl_rel:
            print(f"stl   {attempts[-1]['id']} {r['model']} {r['condition']} {r['task_id']}")

    groups = defaultdict(list)
    for a in attempts:
        groups[(a["model"], a["condition"])].append(a)
    leaderboard = []
    for (model, cond), rows in sorted(groups.items()):
        n = len(rows)
        confs = [a["confidence"] for a in rows if a["confidence"] is not None]
        leaderboard.append({
            "model": model, "condition": cond, "n": n,
            "success": round(sum(a["passed"] for a in rows) / n, 4),
            "silent": round(sum(a["silent"] for a in rows) / n, 4),
            "mean_conf": round(sum(confs) / len(confs), 3) if confs else None,
            "mean_steps": round(sum(a["steps"] or 0 for a in rows) / n, 2),
        })

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "note": "Suite v1.0: primary population (468 attempts, hardened oracle, fixed-protocol tool-use) + exploratory gpt-5.5 (64) + legacy-contract ablation (78).",
        "tasks": list(task_meta.values()),
        "leaderboard": leaderboard,
        "attempts": attempts,
    }
    out = SITE / "data.js"
    out.write_text("window.BENCH = " + json.dumps(payload, indent=1) + ";\n")
    n_stl = sum(1 for a in attempts if a["stl"])
    print(f"\nwrote {out}  ({len(attempts)} attempts, {n_stl} attempt STLs, "
          f"{sum(1 for t in task_meta.values() if t['ref_stl'])} reference STLs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
