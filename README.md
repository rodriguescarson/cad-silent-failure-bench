# cad-silent-failure-bench

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22286324.svg)](https://doi.org/10.5281/zenodo.22286324)

Versions on Zenodo: v1.0 = 10.5281/zenodo.22286324 (the DOI cited in the paper); v1.1 = 10.5281/zenodo.22312792 (four-model ablation, tolerance sensitivity; four archives, unzip all into one directory).

Benchmark, harness, and full attempt corpus for

> **Done Is Not Correct: Measuring Silent Failures and Self-Verification Calibration When LLM
> Agents Take CAD Actions.** Carson Rodrigues, Clive Rodrigues, Aravind Reddy G. 2026.

When an LLM agent writes parametric CAD code from a specification in words, the code can run and
the geometry can render while the part is wrong. This repository measures how often agents ship
such a part *while claiming the task is complete* (the **silent-failure rate**), and how well
their stated confidence tracks correctness, under an exact kernel oracle that is itself audited.

Suite **v1.0** is the version the paper reports. It is frozen; corrections go to `ERRATA.md` and
later versions ship as tagged releases.

## What is here

| Path | Contents | Licence |
|---|---|---|
| `tasks/*.json` | 13 specification tasks in three tiers, 122 machine-checkable requirements with published tolerance bands | CC BY 4.0 |
| `tasks/ref_solutions/` | reference build123d solutions (calibration gate; never shown to agents) | CC BY 4.0 |
| `benchmark/` | schema, grader, kernel executor and property extractor, single-shot / tool-use / multi-agent harnesses, runner | MIT |
| `scripts/` | `regrade.py`, `stats.py`, `analyze.py`, `tolerance_sensitivity.py`, `expert_kappa.py`, `build_site.py`, `calibrate.py` | MIT |
| `data/*.jsonl` | every graded attempt: 519 full-population attempts (`regraded_full_*`), 156 fixed-protocol tool-use attempts (`rerun_tu_*`), 156 ablation attempts (`ablation_legacy_*`, all four models), 60 pilot attempts; `primary_population.jsonl` is the 468-attempt primary population | CC BY 4.0 |
| `data/*.transcripts.jsonl` | full multi-turn transcripts for the 234 fixed-protocol tool-use and ablation attempts | CC BY 4.0 |
| `data/primary_props.json` | measured-properties dictionary for every unique primary-population code (lets you regrade without the kernel) | CC BY 4.0 |
| `data/stats.json`, `data/analysis.json`, `data/tolerance_sensitivity.json`, `data/expert_kappa.json` | every number in the paper | CC BY 4.0 |
| `aravinds-reply/scoring_sheet.xlsx` | the blind expert scoring sheet behind the kappa analysis | CC BY 4.0 |
| `site/` | static 3D viewer of every attempt against its reference (`python -m http.server -d site`) | CC BY 4.0 |
| `docs/` | the pre-registered study plan (`PLAN.md`, predictions P1 to P3 fixed before any run), harness notes, the L-bracket specification decision | CC BY 4.0 |
| `paper/` | the manuscript and the supplementary datasheet | CC BY 4.0 |

Each attempt record carries: task, tier, model, condition, repetition, final code, pass/fail
under the hardened oracle and under the original oracle (`passed_old_oracle`), the failed
checks, `valid_solid`, the agent's completion claim (`reported_done`) and stated `confidence`,
steps, token counts, error text, and per-round context-divergence scores (`cds`) for multi-agent
episodes. A **silent failure** is `valid_solid and reported_done and not passed`.

## Reproduce the paper without any API call

```bash
python3 tests/test_grader.py              # pure-python grader tests, no dependencies
python3 scripts/dry_run.py                # end-to-end plumbing with a mock kernel and mock LLM
python3 scripts/stats.py                  # every statistic in the paper -> data/stats.json
```

To re-execute the stored code through the real kernel (regrade, tolerance sweep, viewer):

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # build123d 0.11 / OCP
.venv/bin/python scripts/calibrate.py                 # every reference solution passes its checks
.venv/bin/python scripts/regrade.py                   # regrade all stored attempts (about 20 min)
.venv/bin/python scripts/tolerance_sensitivity.py     # band scaling x0.25 .. x4 -> tab_tolerance.tex
.venv/bin/python scripts/build_site.py                # rebuild the 3D viewer
```

To run new agents you need API keys (`ANTHROPIC_API_KEY`, or `OPENROUTER_API_KEY` /
`OPENAI_API_KEY`); see `docs/HARNESS.md`.

## Headline numbers (primary population, four vendors, n = 156 per condition)

| Condition | Success | Silent failures | Claim precision |
|---|---|---|---|
| single-shot | 64.1% | 22/156 (14.1%) | 64.0% |
| tool-use, measure-then-claim | 77.6% | 5/156 (3.2%) | 96.0% |
| planner-coder-checker | 61.5% | 4/156 (2.6%) | 95.5% |

Hardening our own oracle flipped 18 of 519 verdicts from pass to fail and none in reverse, so
these rates are lower bounds. Scaling every tolerance band from x0.25 to x4 does not change the
single-shot to tool-use contrast (`data/tolerance_sensitivity.json`).

## Datasheet, hosting, maintenance

`paper/supplement.pdf` is the datasheet (Gebru et al., 2021) with the author statement, licence
confirmation, and the hosting and maintenance plan. In short: GitHub hosts the living suite, a
Zenodo record holds the immutable v1.0 archive, corrections are logged not silently applied, and
the first author keeps the release runnable against the pinned kernel for at least three years.
Issues here, or carson@celabe.com.

## Citation

See `CITATION.cff`. Please cite the paper and state the suite version.
