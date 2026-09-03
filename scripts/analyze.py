"""Analyze sweep results -> aggregate JSON + paper figures (PDF) + LaTeX table rows.

Usage:  .venv/bin/python scripts/analyze.py [--glob "full_*.jsonl"] [--out data/analysis.json]

Reads data/<glob>, computes every metric the paper reports, writes:
  data/analysis.json          all numbers (tables are generated from this, never hand-typed)
  figures/fig1_success_silent.pdf   success + silent-failure by condition x model
  figures/fig2_reliability.pdf      reliability diagram + confidence histogram (all attempts)
  figures/fig3_cds.pdf              multi-agent CDS for passed vs failed episodes
  figures/fig4_tier.pdf             success/silent by tier x condition
  figures/tab_main.tex              main results table body (\\input into the paper)
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "figures"

CONDS = ["single_shot", "tool_use", "multi_agent"]
COND_LABEL = {"single_shot": "single-shot", "tool_use": "tool-use", "multi_agent": "multi-agent"}


def load(glob: str) -> list[dict]:
    recs, dropped = [], 0
    for f in sorted((ROOT / "data").glob(glob)):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if (r.get("error") or "").startswith("attempt aborted"):
                dropped += 1  # infrastructure abort (e.g. credit exhaustion), not agent behaviour
                continue
            recs.append(r)
    if dropped:
        print(f"note: dropped {dropped} infra-aborted attempts")
    return recs


def is_silent(r: dict) -> bool:
    return bool(r.get("reported_done") and r.get("valid_solid") and not r.get("passed"))


def agg(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    confs = [(r["confidence"], 1.0 if r["passed"] else 0.0)
             for r in rows if r.get("confidence") is not None]
    return {
        "n": n,
        "success": sum(r["passed"] for r in rows) / n,
        "silent": sum(is_silent(r) for r in rows) / n,
        "loud": sum((not r["passed"]) and not is_silent(r) for r in rows) / n,
        "done_rate": sum(bool(r.get("reported_done")) for r in rows) / n,
        "mean_conf": float(np.mean([c for c, _ in confs])) if confs else None,
        "mean_steps": float(np.mean([r.get("steps") or 0 for r in rows])),
        "ece": ece(confs), "auroc": auroc(confs), "brier": brier(confs),
    }


def ece(pairs: list[tuple], bins: int = 5) -> float | None:
    """Equal-mass binned ECE."""
    if len(pairs) < bins:
        return None
    arr = sorted(pairs)
    chunks = np.array_split(np.array(arr), bins)
    n = len(arr)
    return float(sum(len(c) / n * abs(c[:, 0].mean() - c[:, 1].mean()) for c in chunks if len(c)))


def brier(pairs: list[tuple]) -> float | None:
    if not pairs:
        return None
    return float(np.mean([(c - y) ** 2 for c, y in pairs]))


def auroc(pairs: list[tuple]) -> float | None:
    pos = [c for c, y in pairs if y == 1.0]
    neg = [c for c, y in pairs if y == 0.0]
    if not pos or not neg:
        return None
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return float(wins / (len(pos) * len(neg)))


def pass_k(rows: list[dict]) -> tuple[float | None, float | None]:
    """(success@k, pass^k) per (task, model, condition) group, averaged."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["task_id"], r["model"], r["condition"])].append(r["passed"])
    anyk = [1.0 if any(g) else 0.0 for g in groups.values()]
    allk = [1.0 if all(g) else 0.0 for g in groups.values()]
    return (float(np.mean(anyk)) if anyk else None, float(np.mean(allk)) if allk else None)


ERROR_MODES = [
    ("no_code", lambda r: not r.get("code")),
    ("execution_error", lambda r: bool(r.get("error")) and not r.get("valid_solid")),
    ("invalid_solid", lambda r: r.get("code") and not r.get("error") and not r.get("valid_solid")),
    ("feature_count", lambda r: any(c in {"bolts", "holes", "seats", "step1", "step2", "step3",
                                          "bore", "new_bore", "old_bore_gone", "hub", "cbore",
                                          "through", "central", "outer", "flange_rim", "disc_rim"}
                                    for c in r.get("failed_checks") or [])),
    ("dimension", lambda r: any(c in {"od", "thickness", "length", "width", "depth", "height",
                                      "max_dia", "side_x", "side_y", "disc_od", "flange_od"}
                                for c in r.get("failed_checks") or [])),
    ("volume_constraint", lambda r: any(c in {"volume", "volume_cap"}
                                        for c in r.get("failed_checks") or [])),
]


def code_errors(rows: list[dict]) -> dict:
    """Provisional auto-coding of failure modes (multi-label; Clive's validated taxonomy replaces
    this with human coding + kappa). Counts over FAILED attempts only."""
    failed = [r for r in rows if not r["passed"]]
    out = {name: sum(1 for r in failed if fn(r)) for name, fn in ERROR_MODES}
    out["n_failed"] = len(failed)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="full_*.jsonl")
    ap.add_argument("--out", default="data/analysis.json")
    args = ap.parse_args()

    rows = load(args.glob)
    if not rows:
        print("no records matched", args.glob)
        return 1
    FIGS.mkdir(exist_ok=True)
    models = sorted({r["model"] for r in rows})

    by_cond = {c: agg([r for r in rows if r["condition"] == c]) for c in CONDS}
    by_model_cond = {m: {c: agg([r for r in rows if r["model"] == m and r["condition"] == c])
                         for c in CONDS} for m in models}
    by_tier_cond = {t: {c: agg([r for r in rows if r.get("tier") == t and r["condition"] == c])
                        for c in CONDS} for t in sorted({r.get("tier") for r in rows})}
    s_at_k, p_hat_k = pass_k(rows)

    ma = [r for r in rows if r["condition"] == "multi_agent" and r.get("cds")]
    cds_pass = [float(np.mean(r["cds"])) for r in ma if r["passed"]]
    cds_fail = [float(np.mean(r["cds"])) for r in ma if not r["passed"]]

    silent_conf = [r["confidence"] for r in rows if is_silent(r) and r.get("confidence") is not None]

    analysis = {
        "glob": args.glob, "n": len(rows), "models": models,
        "by_condition": by_cond, "by_model_condition": by_model_cond,
        "by_tier_condition": {str(k): v for k, v in by_tier_cond.items()},
        "success_at_k": s_at_k, "pass_hat_k": p_hat_k,
        "cds": {"n_episodes": len(ma),
                "mean_pass": float(np.mean(cds_pass)) if cds_pass else None,
                "mean_fail": float(np.mean(cds_fail)) if cds_fail else None,
                "n_pass": len(cds_pass), "n_fail": len(cds_fail)},
        "silent_failures": {"n": sum(is_silent(r) for r in rows),
                            "mean_conf": float(np.mean(silent_conf)) if silent_conf else None,
                            "min_conf": min(silent_conf) if silent_conf else None},
        "error_modes_failed_attempts": code_errors(rows),
        "error_modes_by_condition": {c: code_errors([r for r in rows if r["condition"] == c])
                                     for c in CONDS},
    }
    (ROOT / args.out).write_text(json.dumps(analysis, indent=1))
    print(f"wrote {args.out}  (n={len(rows)}, models={len(models)})")

    # ---- fig 1: success + silent by condition x model ----
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    x = np.arange(len(models))
    w = 0.26
    for i, c in enumerate(CONDS):
        succ = [by_model_cond[m][c].get("success", 0) or 0 for m in models]
        sil = [by_model_cond[m][c].get("silent", 0) or 0 for m in models]
        axes[0].bar(x + (i - 1) * w, succ, w, label=COND_LABEL[c])
        axes[1].bar(x + (i - 1) * w, sil, w, label=COND_LABEL[c])
    for ax, title in zip(axes, ["Success rate", "Silent-failure rate"]):
        ax.set_xticks(x)
        ax.set_xticklabels([m.split("/")[-1].replace("claude-", "") for m in models],
                           rotation=18, ha="right", fontsize=8)
        ax.set_ylim(0, 1.02)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGS / "fig1_success_silent.pdf")

    # ---- fig 2: reliability diagram ----
    pairs = [(r["confidence"], 1.0 if r["passed"] else 0.0)
             for r in rows if r.get("confidence") is not None]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.4))
    if len(pairs) >= 5:
        chunks = np.array_split(np.array(sorted(pairs)), 5)
        confs = [c[:, 0].mean() for c in chunks if len(c)]
        accs = [c[:, 1].mean() for c in chunks if len(c)]
        axes[0].plot([0, 1], [0, 1], "--", color="gray", lw=1)
        axes[0].plot(confs, accs, "o-", color="#d62728")
        axes[0].set_xlabel("claimed confidence")
        axes[0].set_ylabel("empirical success")
        axes[0].set_title(f"Reliability (equal-mass bins), ECE={ece(pairs):.3f}", fontsize=10)
        axes[0].set_xlim(0, 1.02), axes[0].set_ylim(0, 1.02)
    axes[1].hist([c for c, _ in pairs], bins=20, range=(0, 1), color="#1f77b4", alpha=0.85)
    axes[1].set_xlabel("claimed confidence")
    axes[1].set_title("Confidence distribution (all attempts)", fontsize=10)
    for ax in axes:
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGS / "fig2_reliability.pdf")

    # ---- fig 3: CDS pass vs fail ----
    if cds_pass or cds_fail:
        fig, ax = plt.subplots(figsize=(4.6, 3.3))
        parts = [v for v in (cds_pass, cds_fail) if v]
        labels = [l for l, v in zip(["passed", "failed"], (cds_pass, cds_fail)) if v]
        bp = ax.boxplot(parts, labels=labels, widths=0.5, patch_artist=True)
        for patch, col in zip(bp["boxes"], ["#3ecf8e", "#ff5470"]):
            patch.set_facecolor(col), patch.set_alpha(0.6)
        for i, v in enumerate(parts):
            ax.scatter(np.random.normal(i + 1, 0.05, len(v)), v, s=14, color="#333", alpha=0.6, zorder=3)
        ax.set_ylabel("mean episode CDS")
        ax.set_title("Context divergence vs outcome (multi-agent)", fontsize=10)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(FIGS / "fig3_cds.pdf")

    # ---- fig 4: tier breakdown ----
    tiers = sorted(by_tier_cond)
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.3))
    x = np.arange(len(tiers))
    for i, c in enumerate(CONDS):
        succ = [by_tier_cond[t][c].get("success", 0) or 0 for t in tiers]
        sil = [by_tier_cond[t][c].get("silent", 0) or 0 for t in tiers]
        axes[0].bar(x + (i - 1) * w, succ, w, label=COND_LABEL[c])
        axes[1].bar(x + (i - 1) * w, sil, w, label=COND_LABEL[c])
    for ax, title in zip(axes, ["Success rate by tier", "Silent-failure rate by tier"]):
        ax.set_xticks(x), ax.set_xticklabels([f"T{t}" for t in tiers])
        ax.set_ylim(0, 1.02), ax.set_title(title, fontsize=10), ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGS / "fig4_tier.pdf")

    # ---- main results table (complete tabular env; \input it outside any tabular) ----
    lines = ["\\begin{tabular}{llrrrrrr}", "\\toprule",
             "Model & Condition & $n$ & Success & Silent & Conf. & ECE & Steps \\\\",
             "\\midrule"]
    for m in models:
        short = m.split("/")[-1]
        for c in CONDS:
            a = by_model_cond[m][c]
            if not a.get("n"):
                continue
            ece_s = f"{a['ece']:.3f}" if a.get("ece") is not None else "--"
            conf_s = f"{a['mean_conf']:.2f}" if a.get("mean_conf") is not None else "--"
            lines.append(f"{short} & {COND_LABEL[c]} & {a['n']} & {a['success']*100:.0f}\\% & "
                         f"{a['silent']*100:.0f}\\% & {conf_s} & {ece_s} & "
                         f"{a['mean_steps']:.1f} \\\\")
        lines.append("\\addlinespace")
    if lines and lines[-1] == "\\addlinespace":
        lines.pop()
    lines += ["\\bottomrule", "\\end{tabular}"]
    (FIGS / "tab_main.tex").write_text("\n".join(lines) + "\n")
    print("wrote figures/fig1..fig4 + figures/tab_main.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
