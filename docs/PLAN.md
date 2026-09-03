# Study Plan — Agentic LLMs as Engineering Co-Pilots (CAD action reliability)

> **Positioning updated 2026-06-10 after the literature sweep** (see `references/RELATED_WORK.md`
> for the full map; all cite keys below resolve in `references/verified.bib`). The field moved fast
> in 2024–26: the claim is NOT "first NL→CAD benchmark" — it is the conjunction nobody measures.

## Background & gap
LLM agents increasingly *take actions* via tool use and code execution (ReAct `yao2023react`;
SWE-bench `jimenez2024swebench`). In engineering the analogous move is **NL spec → parametric CAD
model**: the agent doesn't advise, it *builds the geometry*. A 2024–26 wave covers generation:
one-shot text-to-CAD (`khan2024text2cad`, `xie2025texttocadquery`), benchmark suites
(`wang2026text2cadbench`), graders-as-reward (`zhou2025cadjudge`), and *agentic* systems with kernel
or visual feedback (`mallis2024cadassistant`, `ocker2025ideatocad`, `yuan2026procad`,
`alrashedy2024cadcodeverify`, `schuepbach2025texttodesign`, `barkley2026cadsmith`). CADSmith — the
closest work — validates agent-generated CadQuery against exact kernel measurements and even *names*
silent divergence from prompt intent, but treats it as a data-quality defect to engineer away.
Meanwhile the agent-reliability literature shows agents systematically overclaim: intrinsic
self-correction fails (`huang2024selfcorrect`, `kamoi2024selfcorrection`), agents predict 77%
success while achieving 22% (`kaddour2026overconfidence`), and benchmark graders themselves admit
false positives (`yu2025utboost`, `zhu2025benchpractices`).

**Gap (the conjunction):** no work measures the **silent-failure rate** — (valid, renderable solid)
∧ (agent explicitly reports done) ∧ (fails ≥1 machine-checkable semantic property) — nor
completion-claim **calibration (ECE/AUROC) against a geometric oracle**, nor how either varies with
**agent architecture**. CAD is the ideal domain for this question precisely because the B-rep makes
ground truth exactly computable, separating agent-side overclaiming from grader inadequacy by
construction. We measure what CADSmith assumes away, in the slice Kaddour et al. leave open.

Carson's prior work frames the hazard: Paper 06 shows multi-agent LLM pipelines accumulate **context
drift** (CDS metric); Paper 09 shows humans **over-delegate** to action-taking agents, withdrawing
oversight. Neither studied a domain with an *objective* correctness signal. CAD supplies exactly that:
the produced B-rep can be measured (dimensions, hole count/positions, volume/mass, mate/interference,
DFM heuristics), so agent success can be auto-graded and **silent failures** (plausible-looking but
wrong geometry, reported as "done") can be detected without human rubric noise. **Gap:** there is no
reproducible benchmark of *agentic* CAD reliability, no validated error-mode taxonomy, and no evidence
on whether tool-use feedback closes the syntactic-vs-semantic gap or merely hides it.

## Research questions
- **RQ1.** How reliably do frontier LLM agents translate a natural-language mechanical spec into a
  *correct* parametric model, and how does this differ by agent architecture (single-shot codegen vs.
  tool-using w/ kernel feedback vs. planner–coder–checker multi-agent)?
- **RQ2.** Does kernel-feedback tool-use reduce **silent semantic failures** (wrong dimensions/
  constraints on a part that runs and renders), or only syntactic failures?
- **RQ3.** In the multi-agent condition, does Paper 06-style **context drift** predict
  constraint-violation on multi-feature/multi-part specs?
- **RQ4 (stretch / Paper 09 link).** Do engineers catch silent CAD failures when the agent reports
  success, and is catching modulated by anthropomorphic framing? *(optional human study; can spin out.)*

## Contributions (falsifiable predictions)
- **C1 — Benchmark.** A reproducible, open suite of ~40–60 NL→CAD tasks with **machine-checkable**
  success criteria + an auto-grader (geometric property checks on the produced solid).
- **C2 — Error taxonomy.** An empirically grounded taxonomy of agentic-CAD failure modes
  (misread/units dimension error, wrong datum/reference, topological invalidity, constraint conflict,
  hallucinated feature, manufacturability violation), defined and validated by a mechanical engineer.
- **C3 — Reliability findings.** Evidence for **P1:** tool-use w/ kernel feedback > single-shot on
  *dimensional* accuracy; **P2:** multi-agent context drift raises *constraint-violation* rate on
  multi-part specs; **P3:** **silent-failure rate** improves far less with model scale than syntactic
  success does — i.e. the dangerous gap persists. (P3 is the headline; it operationalizes the
  over-delegation thesis with ground truth.)
- **C4 (stretch).** Human under-catching of silent failures under "agent says done" + framing effect.

## Design — the benchmark & harness
**Substrate (recommend open for reproducibility):** parametric CAD-as-code via **CadQuery / build123d**
(OpenCascade, pip-installable; the agent writes Python that emits a solid). Optional **industrial
track:** Clive reproduces a subset in **NXOpen** to show transfer to production CAD. (Open kernel = a
benchmark anyone can rerun; NX track = external validity.)

**Agent conditions (within-task):**
1. **Single-shot** — model emits CAD code once from the spec.
2. **Tool-use (ReAct-style)** — agent can run the code, *query measured properties* (bbox, mass, hole
   count, interference), read errors, and iterate up to *k* steps.
3. **Multi-agent** — planner → coder → checker (the checker has grader-like tools); instrument turns
   for **context drift** (reuse Paper 06 CDS).

**Models:** ≥3 frontier families (e.g. Claude / GPT / Gemini current versions) + ≥1 open-weight
code model; **pin versions + dates**; report per-model; multi-seed (≥5) for variance.

## Task suite (machine-checkable by construction)
Each task = `{ nl_spec, params, checks[] }`. Specs are written so every requirement maps to a
computable property with a tolerance band. **Design upgrades adopted from the 2026-06-10 sweep
(`references/RELATED_WORK.md` §improvements):**
- **Dual prompt styles per task** — expert + non-expert phrasing of the same spec
  (`wang2026text2cadbench` precedent; links to `yuan2026procad` ambiguity findings). Same checks,
  double the effective suite.
- **ISO 2768 tolerance bands** — no existing benchmark grades against engineering tolerances
  (CADSmith is pass/fail-exact); Clive selects tolerance classes per feature. *Our differentiator.*
- **Topology checks** (Euler characteristic, from `preintner2025evocad`) alongside hole-count/PCD —
  catches fused/missing holes that volume misses.
- **Parametric re-instantiation** — each task family re-instantiates with varied parameters +
  regenerated ground truth (contamination resistance; no current benchmark does this).
- **ABC compliance** — design to the Agentic Benchmark Checklist (`zhu2025benchpractices`) and state
  it.

Tiers:
- **T1 single feature** — "flange, OD 120 mm, 6× Ø11 bolt holes on a 95 mm PCD, 14 mm thick." Checks:
  bbox, bore Ø, hole count + PCD + positions, thickness.
- **T2 multi-feature** — stepped shaft with two bearing seats + keyway to tolerance; chamfers.
- **T3 multi-part / assembly intent** — bracket + fastener pattern that must not interfere with a
  mating boss; checks include **interference/clearance** and assembly mate satisfaction.
- **T4 constraint/edit** — "take this part and add a 3 mm fillet to all top edges, keep mass < X" —
  tests editing an existing model + a global constraint.
Ground-truth params + tolerances authored by Clive; a reference solution exists per task for grader
calibration (not shown to the agent).

## Measures / metrics
- **success@k** (all checks pass within tolerance), per condition.
- **Dimensional error** (signed/abs, per toleranced feature); **constraint-violation rate**;
  **interference rate**; **DFM-violation rate** (simple manufacturability heuristics).
- **Silent-failure rate** = produced a valid, renderable solid that the agent *reported as complete*
  but that fails ≥1 semantic check. **Self-verification calibration** = agreement between the agent's
  claimed done/confidence and actual correctness: **ECE (equal-mass bins) + reliability diagrams +
  AUROC + Brier** (AUROC because base rates are low, per `kaddour2026overconfidence`; verbalized
  confidence justified by `tian2023justask`; ECE per `guo2017calibration`). Also report **pass^k**
  consistency over seeds (`yao2024taubench`). Optional intervention arm: adversarial "find the bug
  before declaring done" elicitation (best-calibrated condition in `kaddour2026overconfidence`).
- **Context-Drift Score (CDS, Paper 06)** in the multi-agent condition vs. constraint-violation.
- **Cost/efficiency:** tokens, tool-calls, wall-clock to first-correct.

## Analysis
- Mixed-effects models: `pass(0/1) ~ condition × tier × model + (1|task) + (1|seed)`; pre-specified
  contrasts for P1–P3. Silent-failure and calibration analyzed separately from raw success.
- **Grader validation:** Clive manually scores a stratified sample; report auto-grader vs. expert
  agreement (target κ ≥ 0.8) — mirrors Paper 02's inter-rater rigor.
- Error-mode coding: two coders (Carson + Clive) label failure transcripts to the C2 taxonomy; report κ.

## What Clive owns + what the paper does for him
Genuine, attributable co-authorship — not acknowledgment-tier. Clive's named, citable contributions:
1. **The task suite + ISO 2768 tolerance classes** (T1–T4 specs, ground-truth params, per-feature
   tolerance bands) — the artifact every user of the benchmark touches; mechanical-engineering
   judgment no ML author can supply.
2. **The error-mode taxonomy (C2)** — defined and validated by a practicing CAD engineer, with κ
   inter-rater coding (MAST `cemri2025mast` is the citable template, κ=0.88 bar). In the paper this
   is *Clive's section*.
3. **Grader validation** — expert hand-scoring of the stratified sample vs the auto-grader (target
   κ ≥ 0.8); the external-validity check.
4. **The NXOpen industrial track** — reproducing a task subset in Siemens NX via NXOpen scripting:
   showcases exactly his professional stack and is the bridge from open-kernel research to
   production CAD. No one else in this literature has it.
Career payoff for Clive: a peer-reviewed AI×CAD publication is rare among CAD engineers — it
credentializes his CAD-for-AI consulting (Mecado and beyond); the venue plan includes his
community's journals (ASME JCISE / IDETC-CIE, see VENUES.md); CRediT author-contribution statement
makes the division of labor explicit; and the COI (Mecado contract) is disclosed cleanly per venue
policy, which protects him professionally. Author order: decide together — Carson-first with Clive
as co-equal contribution-statement, or alphabetical; flag at the framing call.

## Open-science / integrity
- Release task suite + auto-grader + harness + result logs (MIT/CC-BY); `make reproduce` per model.
- **Public/open data & kernels only**; no proprietary CAD/data (see COI note in README).
- Every citation DOI-verified (CrossRef/arXiv) before the bib — reuse `verify_dois.py`. No fabrication.
- Pin model versions + API dates; results are a snapshot, stated as such.

## Venue & timeline (from June 2026)
- **Primary: NeurIPS 2027 Datasets & Benchmarks Track** — purpose-built for a benchmark+taxonomy where
  insight beats compute. (Or the 2026 cycle if scope is kept tight and work starts now.)
- **Strong domain alt: ASME IDETC/CIE 2027** (Computers & Information in Engineering) — Clive-friendly,
  receptive to CAD+AI, archival.
- **Workshops (fast path):** an LLM-agents or ML-for-engineering-design workshop at NeurIPS/ICML/ICLR;
  good for an early short version + arXiv preprint.
- **Journal alt:** *Computer-Aided Design* (Elsevier) or *ASME J. Mechanical Design*.

## Risks & mitigations
- *Auto-grading arbitrary geometry is hard* → constrain task specs to **checkable properties** with
  tolerance bands + reference solutions; property-based grading, not shape-matching; Clive validates a
  sample (inter-rater κ).
- *Kernel/licensing* → primary = open CadQuery/build123d; NXOpen only as an optional external-validity
  track.
- *Models drift over time* → pin versions/dates, report per-model, treat as a dated snapshot.
- *Scope creep* → the human study (RQ4/C4) is a **stretch goal / spin-out Paper 11**, not a blocker.
- *"Just prompt-engineering" critique* → the contribution is the **benchmark + taxonomy + silent-failure
  metric + drift link**, model-agnostic and reusable, not a single prompting trick.

---

## Alternative framings (decide on the Carson + Clive call before building)
- **B — VLM benchmark: "Can frontier VLMs read a mechanical drawing?"** Inputs = 2D engineering
  drawings (dimensions, GD&T, views); task = extract structured specs. Pure perception/benchmark, very
  topical, Clive supplies drawings + ground truth. Lower systems-build than the agentic harness; less
  tied to Carson's agent line. Could be **Paper 11**.
- **C — Context drift in autonomous-driving multi-agent planning.** Apply Paper 06's CDS to a
  perception→prediction→planning agent stack (Clive's thesis domain). Highest external relevance to
  Clive's M.Eng but heavier (sim/compute) and less cleanly auto-checkable than CAD. Weaker near-term fit.

**Recommendation:** lead with the primary (agentic CAD reliability) — cleanest verifiable signal,
strongest reuse of Papers 06/09, most demoable, lowest compute. Hold B as the likely Paper 11.
