"""Tolerance-band sensitivity of the silent-failure measurand. Offline, no API.

Re-executes every primary-population attempt's stored code once (Build123dExecutor,
cached per unique code string), stores the measured-properties dict in
data/primary_props.json, then regrades every attempt under the published tolerance
bands scaled by a set of factors. Reports, per factor and condition: success, silent
failures, claim precision, and the single-shot minus tool-use silent-rate contrast with
an exact McNemar p over (task, model, repetition) triples.

Band scaling: approx tol, cylinder_count radius/height tol, bolt_circle radius/height/
pcd/center/ang tol are multiplied by the factor; range checks keep their midpoint and
scale the half-width; equal/true checks are unchanged (they carry no band).

Sanity: at factor 1.0 the regrade must reproduce the stored `passed` flag on every
attempt; mismatches are counted and printed.

Usage:  .venv/bin/python scripts/tolerance_sensitivity.py [--factors 0.25,0.5,1,2,4]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.executor import Build123dExecutor  # noqa: E402
from benchmark.grader import grade  # noqa: E402
from benchmark.schema import load_suite  # noqa: E402

CONDS = ("single_shot", "tool_use", "multi_agent")


def silent(valid: bool, done: bool, passed: bool) -> bool:
    return bool(valid) and bool(done) and not passed


def scaled_task(task, f: float):
    t = copy.deepcopy(task)
    for c in t.checks:
        if c.kind == "approx" and c.tol is not None:
            c.tol = c.tol * f
        elif c.kind == "range" and c.lo is not None and c.hi is not None:
            mid = (c.lo + c.hi) / 2.0
            half = (c.hi - c.lo) / 2.0
            c.lo, c.hi = mid - half * f, mid + half * f
        elif c.kind == "cylinder_count":
            c.radius_tol = (c.radius_tol if c.radius_tol is not None else 0.5) * f
            c.height_tol = (c.height_tol if c.height_tol is not None else 1.0) * f
        elif c.kind == "bolt_circle":
            c.radius_tol = (c.radius_tol if c.radius_tol is not None else 0.5) * f
            c.height_tol = (c.height_tol if c.height_tol is not None else 1.0) * f
            c.pcd_tol = (c.pcd_tol if c.pcd_tol is not None else 0.5) * f
            c.center_tol = (c.center_tol if c.center_tol is not None else 1.5) * f
            c.ang_tol = (c.ang_tol if c.ang_tol is not None else 10.0) * f
    return t


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--factors", default="0.25,0.5,1,2,4")
    ap.add_argument("--population", default="primary_population.jsonl")
    args = ap.parse_args()
    factors = [float(x) for x in args.factors.split(",")]

    tasks = {t.id: t for t in load_suite(ROOT / "tasks")}
    rows = [json.loads(l) for l in (ROOT / "data" / args.population).read_text().splitlines() if l.strip()]

    props_path = ROOT / "data" / "primary_props.json"
    props_cache: dict[str, dict | None] = json.loads(props_path.read_text()) if props_path.exists() else {}
    executor = Build123dExecutor()
    n_exec = 0
    for r in rows:
        code = r.get("code") or ""
        if not code or (r.get("error") or "").startswith("attempt aborted"):
            continue
        h = hashlib.sha256(code.encode()).hexdigest()
        if h not in props_cache:
            props_cache[h] = executor.run(code).props
            n_exec += 1
            if n_exec % 25 == 0:
                props_path.write_text(json.dumps(props_cache))
                print(f"executed {n_exec} unique codes", flush=True)
    props_path.write_text(json.dumps(props_cache))
    print(f"executed {n_exec} new unique codes; cache holds {len(props_cache)}", flush=True)

    out: dict = {"population": args.population, "n": len(rows), "factors": {}}
    for f in factors:
        st = {tid: scaled_task(t, f) for tid, t in tasks.items()}
        per = {c: {"n": 0, "success": 0, "silent": 0, "claims": 0, "claim_pass": 0, "valid_claims": 0} for c in CONDS}
        verdict: dict[tuple, dict] = {}
        mismatch = 0
        for r in rows:
            code = r.get("code") or ""
            aborted = (r.get("error") or "").startswith("attempt aborted")
            props = None if (not code or aborted) else props_cache.get(hashlib.sha256(code.encode()).hexdigest())
            g = grade(st[r["task_id"]], props)
            passed, valid = bool(g.passed), bool(g.valid_solid)
            done = bool(r.get("reported_done"))
            if f == 1.0 and passed != bool(r.get("passed")):
                mismatch += 1
            c = r["condition"]
            d = per[c]
            d["n"] += 1
            d["success"] += passed
            d["silent"] += silent(valid, done, passed)
            d["claims"] += done
            d["claim_pass"] += (done and passed)
            d["valid_claims"] += (done and valid)
            verdict[(r["task_id"], r["model"], r.get("seed"), r.get("attempt"), c)] = {
                "passed": passed, "silent": silent(valid, done, passed)}
        # paired SS vs TU on silent
        b = cc = 0
        for (tid, m, seed, att, c), v in verdict.items():
            if c != "single_shot":
                continue
            tu = verdict.get((tid, m, seed, att, "tool_use"))
            if tu is None:
                continue
            if v["silent"] and not tu["silent"]:
                b += 1  # removed by tool-use
            elif (not v["silent"]) and tu["silent"]:
                cc += 1  # created by tool-use
        res = {c: {**d, "success_rate": round(d["success"] / d["n"], 4), "silent_rate": round(d["silent"] / d["n"], 4),
                   "claim_precision": round(d["claim_pass"] / d["claims"], 4) if d["claims"] else None,
                   "silent_given_valid_claim": round(d["silent"] / d["valid_claims"], 4) if d["valid_claims"] else None}
               for c, d in per.items()}
        res["ss_minus_tu_silent_pp"] = round(100 * (per["single_shot"]["silent"] - per["tool_use"]["silent"]) / per["single_shot"]["n"], 2)
        res["mcnemar_silent_ss_vs_tu"] = {"removed": b, "created": cc, "p": mcnemar_exact(b, cc)}
        if f == 1.0:
            res["sanity_mismatch_vs_stored_passed"] = mismatch
        out["factors"][str(f)] = res
        print(f"factor {f}: " + ", ".join(f"{c} silent {per[c]['silent']}/{per[c]['n']} success {per[c]['success']}" for c in CONDS)
              + f" | SS-TU {res['ss_minus_tu_silent_pp']} pp, McNemar p={res['mcnemar_silent_ss_vs_tu']['p']:.2g}"
              + (f" | sanity mismatches {mismatch}" if f == 1.0 else ""), flush=True)

    (ROOT / "data" / "tolerance_sensitivity.json").write_text(json.dumps(out, indent=1))

    # LaTeX table body
    lines = ["\\begin{tabular}{lrrrrrr}", "\\toprule",
             "Band scale & SS silent & TU silent & MA silent & SS success & TU success & SS$-$TU (pp), McNemar $p$ \\\\", "\\midrule"]
    for f in factors:
        r = out["factors"][str(f)]
        ss, tu, ma = r["single_shot"], r["tool_use"], r["multi_agent"]
        label = {0.25: "$\\times$0.25 (tight)", 0.5: "$\\times$0.5", 1.0: "$\\times$1 (published)", 2.0: "$\\times$2", 4.0: "$\\times$4 (loose)"}.get(f, f"$\\times${f:g}")
        p = r["mcnemar_silent_ss_vs_tu"]["p"]
        pstr = "$<$0.001" if p < 0.001 else f"{p:.3f}"
        lines.append(f"{label} & {ss['silent']}/{ss['n']} ({100*ss['silent_rate']:.1f}\\%) & {tu['silent']}/{tu['n']} ({100*tu['silent_rate']:.1f}\\%) & {ma['silent']}/{ma['n']} ({100*ma['silent_rate']:.1f}\\%) & {100*ss['success_rate']:.1f}\\% & {100*tu['success_rate']:.1f}\\% & {r['ss_minus_tu_silent_pp']:.1f}, {pstr} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    (ROOT / "figures" / "tab_tolerance.tex").write_text("\n".join(lines) + "\n")
    print("wrote data/tolerance_sensitivity.json and figures/tab_tolerance.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
