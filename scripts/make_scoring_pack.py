"""Build Clive's hand-scoring pack: stratified sample + STLs + CSV sheets.

Grader-validation sample (kappa study): valid-solid attempts from the primary population,
stratified — ALL silent failures, all valid-but-wrong non-claims, and a random draw of
grader-passes. Clive scores each part pass/fail against the spec, blind to the grader verdict.

Also emits the taxonomy coding sheet: every failed attempt with its code + failure signature,
for the C2 error-mode labeling.

Output: notes/clive-pack/{scoring_sheet.csv, taxonomy_sheet.csv, stl/*.stl, specs.md}
Usage:  .venv/bin/python scripts/make_scoring_pack.py
"""

from __future__ import annotations

import csv
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark.schema import load_suite  # noqa: E402

PACK = ROOT / "notes" / "clive-pack"
STL = PACK / "stl"
rng = random.Random(42)


def export_stl(code: str, out: Path) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        proc = subprocess.run([sys.executable, "-m", "benchmark._extract", tmp, str(out)],
                              capture_output=True, text=True, timeout=90, cwd=str(ROOT))
        return out.exists()
    finally:
        Path(tmp).unlink(missing_ok=True)


def main() -> int:
    STL.mkdir(parents=True, exist_ok=True)
    tasks = {t.id: t for t in load_suite(ROOT / "tasks")}
    rows = [json.loads(l) for l in (ROOT / "data" / "primary_population.jsonl").read_text().splitlines() if l.strip()]

    valid = [r for r in rows if r.get("valid_solid") and r.get("code")]
    silent = [r for r in valid if r.get("reported_done") and not r["passed"]]
    withheld_wrong = [r for r in valid if not r.get("reported_done") and not r["passed"]]
    passes = [r for r in valid if r["passed"]]
    sample = silent + withheld_wrong + rng.sample(passes, min(25, len(passes)))
    rng.shuffle(sample)  # blind ordering

    with open(PACK / "scoring_sheet.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "task_id", "stl_file", "spec_see_specs_md",
                    "CLIVE_verdict_pass_or_fail", "CLIVE_which_requirement_violated", "CLIVE_notes"])
        for i, r in enumerate(sample, 1):
            name = f"part_{i:03d}.stl"
            if export_stl(r["code"], STL / name):
                w.writerow([f"{i:03d}", r["task_id"], f"stl/{name}", "see specs.md", "", "", ""])
        # answer key kept separately, NOT in the pack
    key = [{"item": f"{i:03d}", "task": r["task_id"], "model": r["model"],
            "condition": r["condition"], "seed": r["seed"], "grader_passed": r["passed"],
            "silent": bool(r.get("reported_done") and not r["passed"]),
            "failed_checks": r.get("failed_checks")} for i, r in enumerate(sample, 1)]
    (ROOT / "data" / "scoring_answer_key.json").write_text(json.dumps(key, indent=1))

    failed = [r for r in rows if not r["passed"]]
    with open(PACK / "taxonomy_sheet.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "task_id", "model", "condition", "valid_solid", "failed_checks",
                    "error", "code_excerpt",
                    "CLIVE_error_mode", "CLIVE_secondary_mode", "CLIVE_notes"])
        for i, r in enumerate(failed, 1):
            w.writerow([i, r["task_id"], r["model"], r["condition"], r.get("valid_solid"),
                        ";".join(r.get("failed_checks") or []), (r.get("error") or "")[:200],
                        (r.get("code") or "")[:500], "", "", ""])

    with open(PACK / "specs.md", "w") as f:
        f.write("# Task specifications (score each part against its task's spec)\n\n")
        for tid, t in sorted(tasks.items()):
            f.write(f"## {tid} — {t.title}\n\n{t.nl_spec}\n\n")

    print(f"pack: {len(sample)} scoring items ({len(silent)} silent, {len(withheld_wrong)} "
          f"withheld-wrong, rest passes), {len(failed)} taxonomy rows -> {PACK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
