"""Inferential statistics for the paper (review round 1 requirements) -> data/stats.json.

Populations:
  PRIMARY  = 2 complete-coverage models with fixed-protocol reruns (haiku, sonnet):
             single_shot + multi_agent from regraded_full_*.jsonl (hardened oracle),
             tool_use from rerun_tu_*.jsonl (fixed protocol + info-matched feedback,
             graded under the hardened oracle at run time).
  EXPLORATORY = gpt-5.5 / qwen partial coverage (regraded), reported per-model only.
  SENSITIVITY = old tool_use (regraded) vs new tool_use: protocol-bug delta.
  ABLATION = tool_use_legacy runs (legacy claim contract, current feedback) vs fixed reruns.
  ORACLE DELTA = passed_old_oracle vs passed across all regraded records.

Everything the manuscript cites numerically must come from this file or analysis.json.

Usage:  .venv/bin/python scripts/stats.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps
from statsmodels.stats.proportion import proportion_confint
from statsmodels.stats.contingency_tables import mcnemar

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(42)
# PRIMARY: complete coverage AND fixed-protocol tool-use rerun (credit cap stopped the
# deepseek/qwen reruns; their complete old-protocol data is reported as SECONDARY).
COMPLETE = {"claude-haiku-4-5", "claude-sonnet-4-6", "deepseek/deepseek-v3.2",
            "qwen/qwen3.7-max"}  # all four: complete coverage + fixed-protocol tool-use reruns
SECONDARY = set()
CONDS = ["single_shot", "tool_use", "multi_agent"]


def load(glob: str) -> list[dict]:
    recs = []
    for f in sorted((ROOT / "data").glob(glob)):
        if f.name.endswith(".transcripts.jsonl"):
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if not (r.get("error") or "").startswith("attempt aborted"):
                    recs.append(r)
    return recs


def silent(r: dict) -> bool:
    return bool(r.get("reported_done") and r.get("valid_solid") and not r.get("passed"))


def wilson(k: int, n: int) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    lo, hi = proportion_confint(k, n, method="wilson")
    return [round(float(lo), 4), round(float(hi), 4)]


def cluster_boot(rows: list[dict], fn, n_boot: int = 4000) -> list[float]:
    """Bootstrap over task clusters."""
    by_task = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)
    tasks = list(by_task)
    vals = []
    for _ in range(n_boot):
        sample = [r for t in RNG.choice(tasks, len(tasks), replace=True) for r in by_task[t]]
        v = fn(sample)
        if v is not None:
            vals.append(v)
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def rate(rows, pred) -> float | None:
    return sum(pred(r) for r in rows) / len(rows) if rows else None


def auroc(pairs) -> float | None:
    pos = [c for c, y in pairs if y]
    neg = [c for c, y in pairs if not y]
    if not pos or not neg:
        return None
    return float(sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg)))


def paired_mcnemar(a_rows, b_rows, pred):
    """Pair on (task, model, seed); return (b01, b10, p)."""
    a = {(r["task_id"], r["model"], r["seed"]): pred(r) for r in a_rows}
    b = {(r["task_id"], r["model"], r["seed"]): pred(r) for r in b_rows}
    keys = sorted(set(a) & set(b))
    n01 = sum(1 for k in keys if not a[k] and b[k])
    n10 = sum(1 for k in keys if a[k] and not b[k])
    if n01 + n10 == 0:
        return n01, n10, 1.0
    table = [[0, n01], [n10, 0]]
    return n01, n10, float(mcnemar(table, exact=True).pvalue)


def main() -> int:
    regraded = load("regraded_full_*.jsonl")
    rerun_tu = load("rerun_tu_*.jsonl")
    if not regraded or not rerun_tu:
        print("missing inputs: regraded:", len(regraded), "rerun_tu:", len(rerun_tu))
        return 1

    primary = ([r for r in regraded if r["model"] in COMPLETE
                and r["condition"] in {"single_shot", "multi_agent"}]
               + [r for r in rerun_tu if r["model"] in COMPLETE])
    old_tu = [r for r in regraded if r["model"] in COMPLETE and r["condition"] == "tool_use"]
    secondary = [r for r in regraded if r["model"] in SECONDARY]
    expl = [r for r in regraded if r["model"] not in COMPLETE | SECONDARY]

    out: dict = {"n_primary": len(primary), "n_exploratory": len(expl)}

    # per-condition rates with Wilson + cluster-bootstrap CIs
    bc = {}
    for c in CONDS:
        rows = [r for r in primary if r["condition"] == c]
        n = len(rows)
        ks = sum(r["passed"] for r in rows)
        ksil = sum(silent(r) for r in rows)
        claims = [r for r in rows if r.get("reported_done")]
        valid_claims = [r for r in claims if r.get("valid_solid")]
        pairs = [(r["confidence"], bool(r["passed"])) for r in rows
                 if r.get("confidence") is not None]
        bc[c] = {
            "n": n,
            "success": round(ks / n, 4), "success_wilson": wilson(ks, n),
            "success_cluster_ci": cluster_boot(rows, lambda s: rate(s, lambda r: r["passed"])),
            "silent": round(ksil / n, 4), "silent_count": ksil, "silent_wilson": wilson(ksil, n),
            "silent_cluster_ci": cluster_boot(rows, lambda s: rate(s, silent)),
            "claim_rate": round(len(claims) / n, 4),
            "claim_precision": round(rate(claims, lambda r: r["passed"]) or 0, 4) if claims else None,
            "silent_given_valid_claim": round(rate(valid_claims, lambda r: not r["passed"]) or 0, 4)
                                        if valid_claims else None,
            "n_valid_claims": len(valid_claims),
            "auroc_pooled": round(auroc(pairs), 3) if auroc(pairs) is not None else None,
            "mean_in_tokens": round(float(np.mean([r.get("input_tokens") or 0 for r in rows]))),
            "mean_out_tokens": round(float(np.mean([r.get("output_tokens") or 0 for r in rows]))),
        }
    out["by_condition_primary"] = bc

    # per-model AUROC (the Simpson's-paradox fix)
    pm_auroc = {}
    for m in sorted({r["model"] for r in primary}):
        pm_auroc[m] = {}
        for c in CONDS:
            pairs = [(r["confidence"], bool(r["passed"])) for r in primary
                     if r["model"] == m and r["condition"] == c
                     and r.get("confidence") is not None]
            a = auroc(pairs)
            pm_auroc[m][c] = round(a, 3) if a is not None else None
    out["auroc_per_model"] = pm_auroc

    # paired tests SS vs TU and SS vs MA
    ss = [r for r in primary if r["condition"] == "single_shot"]
    tu = [r for r in primary if r["condition"] == "tool_use"]
    ma = [r for r in primary if r["condition"] == "multi_agent"]
    for name, b_rows in (("tool_use", tu), ("multi_agent", ma)):
        n01, n10, p = paired_mcnemar(ss, b_rows, lambda r: bool(r["passed"]))
        out[f"mcnemar_success_ss_vs_{name}"] = {"fixed_by": n01, "broken_by": n10, "p": round(p, 6)}
        n01, n10, p = paired_mcnemar(ss, b_rows, silent)
        out[f"mcnemar_silent_ss_vs_{name}"] = {"created": n01, "removed": n10, "p": round(p, 6)}
    # silent-rate difference CI (cluster bootstrap, paired by task)
    def sil_diff(sample_tasks_rows):
        s = rate([r for r in sample_tasks_rows if r["condition"] == "single_shot"], silent)
        t = rate([r for r in sample_tasks_rows if r["condition"] == "tool_use"], silent)
        return None if s is None or t is None else s - t
    out["silent_diff_ss_minus_tu_ci"] = cluster_boot(ss + tu, sil_diff)

    # multi-agent failure decomposition + checker analysis
    ma_fail = [r for r in ma if not r["passed"]]
    out["ma_decomposition"] = {
        "n_episodes": len(ma), "n_failed": len(ma_fail),
        "crash": sum(1 for r in ma_fail if not r.get("valid_solid")),
        "silent": sum(1 for r in ma_fail if silent(r)),
        "withheld_wrong_valid": sum(1 for r in ma_fail
                                    if r.get("valid_solid") and not r.get("reported_done")),
        "false_rejection": sum(1 for r in ma if r["passed"] and not r.get("reported_done")),
    }
    vs_pairs = [(r["confidence"], bool(r["passed"])) for r in ma
                if r.get("valid_solid") and r.get("confidence") is not None]
    out["checker_auroc_valid_solid_only"] = (round(auroc(vs_pairs), 3)
                                             if auroc(vs_pairs) is not None else None)
    out["checker_auroc_valid_n"] = {"n": len(vs_pairs),
                                    "neg": sum(1 for _, y in vs_pairs if not y)}

    # CDS stratified by validity + predictive value
    cds_rows = [r for r in ma if r.get("cds")]
    def mcds(rows):
        return [float(np.mean(r["cds"])) for r in rows]
    c_pass = mcds([r for r in cds_rows if r["passed"]])
    c_fail_inv = mcds([r for r in cds_rows if not r["passed"] and not r.get("valid_solid")])
    c_fail_val = mcds([r for r in cds_rows if not r["passed"] and r.get("valid_solid")])
    cds_pairs = [(float(np.mean(r["cds"])), bool(not r["passed"])) for r in cds_rows]
    mw = (sps.mannwhitneyu(c_pass, c_fail_inv + c_fail_val).pvalue
          if c_pass and (c_fail_inv + c_fail_val) else None)
    out["cds"] = {
        "mean_pass": round(float(np.mean(c_pass)), 4) if c_pass else None,
        "mean_fail_invalid": round(float(np.mean(c_fail_inv)), 4) if c_fail_inv else None,
        "mean_fail_valid": round(float(np.mean(c_fail_val)), 4) if c_fail_val else None,
        "n_pass": len(c_pass), "n_fail_invalid": len(c_fail_inv), "n_fail_valid": len(c_fail_val),
        "mannwhitney_p": float(mw) if mw is not None else None,
        "auroc_as_failure_predictor": round(auroc(cds_pairs), 3) if auroc(cds_pairs) else None,
    }

    # per-task silent concentration (primary)
    pt = {}
    for t in sorted({r["task_id"] for r in primary}):
        rows = [r for r in primary if r["task_id"] == t]
        pt[t] = {"n": len(rows), "silent": sum(silent(r) for r in rows)}
    out["silent_by_task"] = pt

    # GEE logistic: pass ~ condition, silent ~ condition (task clusters)
    try:
        import pandas as pd
        import statsmodels.formula.api as smf
        import statsmodels.api as sm
        df = pd.DataFrame([{"pass_": int(r["passed"]), "silent": int(silent(r)),
                            "condition": r["condition"], "task": r["task_id"],
                            "model": r["model"]} for r in primary])
        for dv in ("pass_", "silent"):
            m = smf.gee(f"{dv} ~ C(condition, Treatment('single_shot')) + C(model)",
                        groups="task", data=df, family=sm.families.Binomial()).fit()
            out[f"gee_{dv}"] = {k: {"coef": round(float(v), 3),
                                    "p": round(float(m.pvalues[k]), 5)}
                                for k, v in m.params.items() if "condition" in k}
    except Exception as e:
        out["gee_error"] = str(e)[:200]

    # loophole ABLATION: legacy claim contract vs fixed, IDENTICAL feedback, all four models
    # (sonnet's legacy arm was run through OpenRouter, so its model id carries a vendor prefix)
    norm = lambda m: m.replace("anthropic/", "")
    abl = load("ablation_legacy_*.jsonl")
    abl = [r for r in abl if norm(r["model"]) in COMPLETE]
    abl_models = {norm(r["model"]) for r in abl}
    abl_fixed = [r for r in rerun_tu if norm(r["model"]) in abl_models]
    if abl:
        ls, ln = sum(silent(r) for r in abl), len(abl)
        fs, fn = sum(silent(r) for r in abl_fixed), len(abl_fixed)
        lc = [r for r in abl if r.get("reported_done")]
        fc = [r for r in abl_fixed if r.get("reported_done")]
        lcp, fcp = sum(r["passed"] for r in lc), sum(r["passed"] for r in fc)
        per_model = {}
        for m in sorted(abl_models):
            L = [r for r in abl if norm(r["model"]) == m]
            F = [r for r in abl_fixed if norm(r["model"]) == m]
            per_model[m] = {"legacy_silent": sum(silent(r) for r in L), "fixed_silent": sum(silent(r) for r in F),
                            "legacy_success": sum(r["passed"] for r in L), "fixed_success": sum(r["passed"] for r in F),
                            "n": len(L)}
        out["ablation_claim_contract"] = {
            "models": sorted(abl_models),
            "legacy_silent": ls, "legacy_n": ln, "fixed_silent": fs, "fixed_n": fn,
            "fisher_p_silent": round(float(sps.fisher_exact([[ls, ln - ls], [fs, fn - fs]]).pvalue), 5),
            "legacy_claim_precision": round(lcp / len(lc), 4) if lc else None,
            "fixed_claim_precision": round(fcp / len(fc), 4) if fc else None,
            "fisher_p_claim_precision": round(float(sps.fisher_exact([[lcp, len(lc) - lcp], [fcp, len(fc) - fcp]]).pvalue), 12),
            "legacy_success": round(rate(abl, lambda r: r["passed"]), 4),
            "fixed_success": round(rate(abl_fixed, lambda r: r["passed"]), 4),
            "fisher_p_success": round(float(sps.fisher_exact([[sum(r["passed"] for r in abl), ln - sum(r["passed"] for r in abl)], [sum(r["passed"] for r in abl_fixed), fn - sum(r["passed"] for r in abl_fixed)]]).pvalue), 5),
            "per_model": per_model,
        }

    # sensitivity: old (buggy-protocol) vs new tool-use
    out["tool_use_protocol_sensitivity"] = {
        "old": {"n": len(old_tu), "success": round(rate(old_tu, lambda r: r["passed"]) or 0, 4),
                "silent": sum(silent(r) for r in old_tu)},
        "new": {"n": len(tu), "success": round(rate(tu, lambda r: r["passed"]) or 0, 4),
                "silent": sum(silent(r) for r in tu)},
    }

    # oracle-hardening delta over all regraded records
    flips = [r for r in regraded if r.get("passed_old_oracle") is not None
             and r["passed"] != r["passed_old_oracle"]]
    out["oracle_hardening"] = {
        "n_regraded": len(regraded),
        "pass_to_fail": sum(1 for r in flips if r["passed_old_oracle"] and not r["passed"]),
        "fail_to_pass": sum(1 for r in flips if not r["passed_old_oracle"] and r["passed"]),
        "new_silent_exposed": sum(1 for r in flips
                                  if r["passed_old_oracle"] and not r["passed"] and silent(r)),
    }

    # secondary (complete coverage, OLD-protocol tool-use) + exploratory (partial) per-model rows
    for label, pool in (("secondary_old_protocol", secondary), ("exploratory_partial", expl)):
        em = {}
        for m in sorted({r["model"] for r in pool}):
            em[m] = {}
            for c in CONDS:
                rows = [r for r in pool if r["model"] == m and r["condition"] == c]
                if rows:
                    em[m][c] = {"n": len(rows),
                                "success": round(rate(rows, lambda r: r["passed"]), 4),
                                "silent": sum(silent(r) for r in rows),
                                "claim_rate": round(rate(rows, lambda r: bool(r.get("reported_done"))), 4)}
        out[label] = em

    (ROOT / "data" / "stats.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items()
                      if k in ("by_condition_primary", "silent_diff_ss_minus_tu_ci",
                               "ma_decomposition", "oracle_hardening",
                               "tool_use_protocol_sensitivity")}, indent=1)[:2400])
    print("\nwrote data/stats.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
