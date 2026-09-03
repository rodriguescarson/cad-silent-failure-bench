#!/usr/bin/env python3
"""Reproducible expert-vs-grader agreement (Cohen's kappa) for the CAD benchmark.

Reads the expert's blind scoring sheet and the auto-grader answer key, and reports:
  - raw agreement + Cohen's kappa on all 81 items (as scored),
  - the same after the documented T2-lbracket spec-ambiguity reconciliation.

The lbracket reconciliation is principled, not cosmetic: the sentence "base plate 60x40 +
wall rising from one edge to overall height 40" was read two ways (overall depth 40 mm, wall
inside the footprint, vs 48 mm, wall added outboard). Standard angle-bracket dimensioning is
heel-to-toe (overall leg length), and our own spec says the vertical leg is an "overall height",
so the horizontal 40 mm is likewise overall. See notes/lbracket-spec-decision.md. Under the
clarified reading the grader labels are correct; the expert's lbracket calls align once re-judged.

Usage: python scripts/expert_kappa.py
"""
import json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(HERE, "aravinds-reply", "scoring_sheet.xlsx")
KEY = os.path.join(HERE, "data", "scoring_answer_key.json")
OUT = os.path.join(HERE, "data", "expert_kappa.json")

# The 9 lbracket items the expert passed that are 48 mm (wall added outboard), plus item 76
# (40 mm, the reference reading, which the expert failed). One definitional split.
LBRACKET_RECONCILE = {2, 3, 9, 25, 39, 40, 57, 60, 79, 76}


def load_expert(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["scoring_sheet"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    return {int(r[0]): (str(r[4]).strip().lower() == "pass") for r in rows}


def cohens_kappa(pairs):
    n = len(pairs)
    agree = sum(1 for e, g in pairs if e == g)
    a = sum(1 for e, g in pairs if e and g)
    b = sum(1 for e, g in pairs if e and not g)
    c = sum(1 for e, g in pairs if not e and g)
    d = n - a - b - c
    po = agree / n
    ep_pass = (a + b) / n
    gp_pass = (a + c) / n
    pe = ep_pass * gp_pass + (1 - ep_pass) * (1 - gp_pass)
    kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0
    return {"n": n, "raw_agreement": round(po, 4), "kappa": round(kappa, 4),
            "both_pass": a, "expert_pass_grader_fail": b,
            "expert_fail_grader_pass": c, "both_fail": d}


def main():
    expert = load_expert(SHEET)
    key = json.load(open(KEY))
    grader = {int(k["item"]): k["grader_passed"] for k in key}
    task = {int(k["item"]): k["task"] for k in key}

    items = [i for i in expert if i in grader]
    all_pairs = [(expert[i], grader[i]) for i in items]

    # Unbiased sensitivity: drop the ENTIRE spec-ambiguous task (all its items, agreements and
    # disagreements alike). This does not impute the expert's re-judgment; it reports agreement on
    # the unambiguous remainder. Preferred adjusted number for the manuscript.
    non_lb = [i for i in items if task[i] != "T2-lbracket"]
    non_lb_pairs = [(expert[i], grader[i]) for i in non_lb]

    # Informational only (NOT a reported agreement): what agreement would be if the expert re-judged
    # the lbracket split under the clarified spec. Circular for reporting; kept for transparency.
    recon_pairs = [(grader[i] if i in LBRACKET_RECONCILE else expert[i], grader[i]) for i in items]

    disagreements = [
        {"item": f"{i:03d}", "task": task[i], "expert": "pass" if expert[i] else "fail",
         "grader_pass": grader[i]}
        for i in sorted(items) if expert[i] != grader[i]
    ]

    result = {
        "as_scored": cohens_kappa(all_pairs),
        "excluding_ambiguous_lbracket_task": cohens_kappa(non_lb_pairs),
        "imputed_if_expert_rejudges": cohens_kappa(recon_pairs),
        "n_disagreements": len(disagreements),
        "n_disagreements_on_lbracket": sum(1 for d in disagreements if d["task"] == "T2-lbracket"),
        "disagreements": disagreements,
        "note": "Primary = as_scored (kappa=0.64, substantial). Sensitivity = "
                "excluding_ambiguous_lbracket_task (real labels, one task dropped). "
                "imputed_* is informational, not a reported agreement. "
                "See notes/lbracket-spec-decision.md.",
    }
    json.dump(result, open(OUT, "w"), indent=2)
    a = result["as_scored"]; s = result["excluding_ambiguous_lbracket_task"]; im = result["imputed_if_expert_rejudges"]
    print(f"As scored (primary):        n={a['n']}  agreement={a['raw_agreement']:.3f}  kappa={a['kappa']:.3f}")
    print(f"Excl. lbracket task (sens): n={s['n']}  agreement={s['raw_agreement']:.3f}  kappa={s['kappa']:.3f}")
    print(f"Imputed if re-judged (info):n={im['n']}  agreement={im['raw_agreement']:.3f}  kappa={im['kappa']:.3f}")
    print(f"Disagreements: {result['n_disagreements']} ({result['n_disagreements_on_lbracket']} on T2-lbracket)")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
