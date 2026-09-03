# Harness — agentic-CAD benchmark v1

A small, decoupled eval framework. The core (schema → grader → metrics → runner → agents) is pure
standard library; only **real geometry** (build123d/OCP) and **real models** (Anthropic/OpenAI) need
external packages, and both are isolated behind interfaces so the rest is testable offline.

```
benchmark/
  schema.py     Task + Check dataclasses, JSON load/validate, property vocabulary
  grader.py     evaluate checks vs a measured-properties dict (pure python)
  metrics.py    success_rate, success@k, silent_failure_rate, ECE calibration
  llm.py        LLMClient: MockLLM | AnthropicLLM | OpenAILLM
  executor.py   MockExecutor | Build123dExecutor (runs agent code in a subprocess)
  _extract.py   subprocess: exec agent code -> build123d solid -> properties JSON (only OCP dep)
  agents.py     SingleShotAgent | ToolUseAgent (ReAct + kernel feedback) | MultiAgent (stub)
  runner.py     sweep tasks × agents × seeds -> JSONL + summary
tasks/          *.json task specs  +  ref_solutions/*.py (grader calibration; never shown to agent)
tests/          pure-python grader/metrics tests
scripts/dry_run.py   end-to-end, NO deps/keys (proves the plumbing; shows a silent failure)
```

## 0. Prove the plumbing (no install, no keys)
```bash
cd 10-agentic-cad-reliability
python scripts/dry_run.py        # runs MockLLM + MockExecutor end-to-end, prints metrics
python tests/test_grader.py      # or: pytest
```

## 1. Install for real runs
build123d needs Python ≥3.10 (the repo venv uses 3.12):
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt    # build123d (OCP), anthropic; pytest
export ANTHROPIC_API_KEY=sk-...              # or OPENAI_API_KEY with --provider openai
export OPENROUTER_API_KEY=sk-or-...          # --provider openrouter: any deepseek/qwen/openai/
                                             # kimi/... model id, e.g. --model deepseek/deepseek-v3.2
```

## 2. Calibrate the grader on reference solutions
Every task's known-good reference solution must pass every check before agent scores are trusted:
```bash
.venv/bin/python scripts/calibrate.py        # all tasks; exits nonzero on any failure
python -m benchmark._extract tasks/ref_solutions/T1-flange-6bolt.py   # one part, raw properties JSON
```
If a check is too tight/loose, adjust its `tol`/`radius_tol` in the task JSON. Cylinder detection
groups cylindrical faces by their infinite cylinder (radius + axis line) and merges them by axial
extent — overlapping spans are one physical cylinder (a hole split by a boolean seam), disjoint
spans are separate features (coaxial bearing seats). Still a heuristic for exotic topology —
validate a sample by hand; report auto-grader vs. expert κ as in PLAN.md.

## 3. Run the eval
```bash
python -m benchmark.runner --tasks tasks --provider anthropic --model claude-opus-4-8 \
    --seeds 5 --out data/results.jsonl \
    --conditions single_shot tool_use multi_agent     # any subset; default = first two
```
Prints the summary; per-attempt records (incl. `reported_done`, `confidence`, `failed_checks`,
`code`, and — for multi_agent — per-round `cds`) land in the JSONL.

**Multi-agent condition:** planner → coder → checker. The episode reports done only when the
CHECKER returns `VERDICT: PASS`. Every role states its dimensional beliefs on a `DIMS: {...}` line
(the planner's dimension names are propagated so naming noise doesn't inflate drift); `cds` is the
per-round Context Divergence Score = mean pairwise disagreement over those beliefs (Paper-06 CDS
operationalized on machine-comparable dimensions). Offline tests: `tests/test_multiagent.py`.

## 4. Results viewer (leaderboard + 3D)
```bash
.venv/bin/python scripts/build_site.py     # re-executes stored attempt code offline -> STLs + site/data.js
python -m http.server -d site 8123        # then open http://localhost:8123
```
Leaderboard by model × condition, filterable attempt list (silent failures highlighted), and a
three.js viewer showing each attempt's produced geometry against the reference part as a ghost
overlay. Static site — deployable as-is (Cloudflare Pages direct upload, like the Datum demo).

## Adding a task
Drop a `tasks/<id>.json` (see `schema.py` for the property vocabulary + check kinds) and a
`tasks/ref_solutions/<id>.py`. Keep every requirement mapped to a computable property + tolerance —
that is what makes the benchmark auto-gradable. Tier the difficulty (T1 single-feature → T4
edit/constraint).

## What's stubbed for v2
- `MultiAgent` (planner→coder→checker) + **Paper-06 CDS** drift instrumentation across turns.
- Richer feature recognition (counterbores, threads, fillets) and DFM/interference checks for T3/T4.
- The optional human study (RQ4) — over-trust of "agent says done"; likely spins out as Paper 11.

## Integrity
- Open kernel + public data only (COI note in `README.md`).
- Pin build123d/OCP + model ids/dates per run; results are a dated snapshot.
- Citations: DOI-verify before the bib — see `references/CANDIDATE_REFS.md`. No fabrication.
