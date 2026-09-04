# Errata

Corrections to any task, check, record, or reported number are logged here with the date and
the effect on the paper's numbers. Nothing is changed silently. Suite v1.0 is the version the
paper reports and is frozen; changes ship as new tagged versions with their own Zenodo DOIs.

| Date | Item | Change | Effect on reported numbers |
|---|---|---|---|
| (none yet) | | | |

## v1.1 (2026-09-04)

- Claim-contract ablation extended from two models (haiku, deepseek; n = 78) to all four
  (`data/ablation_legacy_sonnet.jsonl`, `data/ablation_legacy_qwen.jsonl`; n = 156). Sonnet's
  legacy arm was called through OpenRouter as `anthropic/claude-sonnet-4-6`; `scripts/stats.py`
  normalises the prefix. Four-model result: silent failures 14/156 legacy vs 5/156 fixed
  (Fisher p = 0.056), claim precision 67.6% vs 96.0% (p = 4.5e-10), success 64.1% vs 77.6%
  (p = 0.013). Per model (legacy vs fixed): haiku 6 vs 1, sonnet 4 vs 0, deepseek 4 vs 2,
  qwen 0 vs 2.
- `data/tolerance_sensitivity.json` + `figures/tab_tolerance.tex`: tolerance-band sensitivity
  (x0.25 to x4) from `scripts/tolerance_sensitivity.py`.
- `paper/paper.pdf` and `paper/supplement.pdf` refreshed to the revision-ready text (verbatim
  prompts appendix, two-sided bound on silent-failure rates, exclusion sensitivity for the
  L-bracket task, GEE small-cluster caveat, exact model identifiers).
