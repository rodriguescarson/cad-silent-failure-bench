"""Agent conditions: SingleShot, ToolUse (ReAct w/ kernel feedback), MultiAgent (stub).

Each agent returns an AgentOutput; the runner then grades `output.props` (for tool-use, the props
measured on the final code) against the task. `reported_done` + `confidence` feed the silent-failure
and calibration metrics — they are what the agent *claims*, independent of ground truth.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .executor import Executor
from .llm import LLMClient
from .schema import Task

_CODE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)
_CONF_RE = re.compile(r"CONFIDENCE:\s*([01](?:\.\d+)?)", re.IGNORECASE)
_DIMS_RE = re.compile(r"DIMS:\s*(\{[^\n]*\})")
_VERDICT_RE = re.compile(r"VERDICT:\s*(PASS|REVISE)", re.IGNORECASE)

SYSTEM = (
    "You are a senior mechanical CAD engineer. You build parts as parametric code with the "
    "`build123d` Python library. Always assign the final solid to a top-level variable named "
    "`result`. Import everything you use. Work in millimetres, and model the part in the "
    "conventional orientation: primary axis / thickness along +Z. Reply with exactly one "
    "```python code block. When you are confident the part satisfies the specification, also "
    "write — after and outside the code block, on their own lines — `DONE` and "
    "`CONFIDENCE: <0..1>`, your calibrated probability that every requirement is met."
)


@dataclass
class AgentOutput:
    code: str
    reported_done: bool
    confidence: float | None
    props: dict | None
    steps: int
    input_tokens: int = 0
    output_tokens: int = 0
    transcript: list[dict] = field(default_factory=list)
    error: str | None = None
    cds: list[float] | None = None  # multi-agent: per-round Context Divergence Score (Paper 06)


def _parse(text: str) -> tuple[str, bool, float | None]:
    m = _CODE_RE.search(text)
    code = m.group(1).strip() if m else ""
    prose = _CODE_RE.sub("", text)  # the DONE claim must be outside the code block
    # line-anchored: "DONE" at the start of its own line, so "this is NOT DONE" never counts
    done = re.search(r"^\s*\**DONE\b", prose, re.MULTILINE) is not None
    cm = _CONF_RE.search(prose)
    conf = float(cm.group(1)) if cm else None
    return code, done, conf


def _user_spec(task: Task) -> str:
    return f"Specification (task {task.id}):\n{task.nl_spec}\n\nUnits: {task.units}."


class SingleShotAgent:
    condition = "single_shot"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def run(self, task: Task, executor: Executor) -> AgentOutput:
        msgs = [{"role": "user", "content": _user_spec(task)}]
        reply = self.llm.complete(SYSTEM, msgs)
        code, done, conf = _parse(reply.text)
        ex = executor.run(code) if code else None
        return AgentOutput(
            code=code, reported_done=done, confidence=conf,
            props=ex.props if ex else None, steps=1,
            input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
            transcript=[*msgs, {"role": "assistant", "content": reply.text}],
            error=(ex.error if ex else "no code produced"),
        )


class ToolUseAgent:
    condition = "tool_use"

    def __init__(self, llm: LLMClient, max_steps: int = 4, legacy_claim: bool = False):
        # legacy_claim=True reproduces the pre-audit claim contract (DONE accepted alongside
        # fresh unmeasured code) for the loophole ablation; feedback content stays current,
        # so the ablation isolates the claim contract as the single variable.
        self.llm = llm
        self.max_steps = max_steps
        self.legacy_claim = legacy_claim
        if legacy_claim:
            self.condition = "tool_use_legacy"


    def run(self, task: Task, executor: Executor) -> AgentOutput:
        msgs = [{"role": "user", "content": _user_spec(task)
                 + "\n\nYou may iterate: I will run your code and report measured geometry. "
                   "Declare DONE only after reviewing the measurements of your latest code."}]
        in_tok = out_tok = 0
        last_code, last_props, last_error, conf, done = "", None, None, None, False
        step = 0
        for step in range(1, self.max_steps + 1):
            reply = self.llm.complete(SYSTEM, msgs)
            in_tok += reply.input_tokens
            out_tok += reply.output_tokens
            msgs.append({"role": "assistant", "content": reply.text})
            code, done, conf = _parse(reply.text)
            if code:
                last_code = code
                ex = executor.run(code)
                last_props, last_error = ex.props, ex.error
                feedback = _format_feedback(ex)
                if done and self.legacy_claim:
                    break  # ablation arm: original contract accepted DONE with unmeasured code
                if done:
                    # DONE alongside fresh, unverified code NEVER ends the episode — including at
                    # the step cap (a final confirmation exchange happens after the loop). The
                    # point of this condition is that the agent sees kernel feedback for its
                    # final code before its claim counts.
                    feedback += ("\nYour DONE was not accepted yet: review the measurements above, "
                                 "then reply DONE + CONFIDENCE (no code) if the part meets the "
                                 "spec, or send a corrected ```python block.")
                    done = False
            else:
                if done and last_code:
                    break  # DONE after seeing feedback for the final code: claim accepted
                feedback = "No ```python block found. Provide one assigning `result`."
                done = False
            msgs.append({"role": "user", "content": feedback})
        else:
            if self.legacy_claim:
                return AgentOutput(code=last_code, reported_done=done, confidence=conf,
                                   props=last_props, steps=step, input_tokens=in_tok,
                                   output_tokens=out_tok, transcript=msgs, error=last_error)
            # step cap reached with the last reply containing code: one confirmation exchange so
            # the claim, if any, is made AFTER seeing the final code's measurements.
            if last_code:
                reply = self.llm.complete(SYSTEM, msgs)
                in_tok += reply.input_tokens
                out_tok += reply.output_tokens
                msgs.append({"role": "assistant", "content": reply.text})
                c_code, done, conf2 = _parse(reply.text)
                conf = conf2 if conf2 is not None else conf
                if c_code:  # new code at confirmation = not a clean claim; episode ends unclaimed
                    done = False
        return AgentOutput(
            code=last_code, reported_done=done, confidence=conf, props=last_props,
            steps=step, input_tokens=in_tok, output_tokens=out_tok, transcript=msgs,
            error=last_error,
        )


def _format_feedback(ex) -> str:
    """Full measured-property feedback, information-matched to what the multi-agent checker sees
    (and to what the grader reads) — so condition differences are architectural, not informational."""
    if ex.error:
        return f"Execution error: {ex.error}\nFix the code and resend the ```python block."
    p = ex.props or {}
    keep = {k: p.get(k) for k in
            ("valid_solid", "bbox", "volume", "com", "solid_count", "cylinders")}
    return (
        "Kernel-measured properties of your solid:\n" + json.dumps(keep, indent=1) + "\n"
        "If this meets the spec, reply DONE + CONFIDENCE. Otherwise send a corrected ```python block."
    )


def _parse_dims(text: str) -> dict[str, float]:
    """Extract the agent's `DIMS: {...}` belief line — flat JSON of governing dimensions in mm."""
    m = _DIMS_RE.search(text)
    if not m:
        return {}
    try:
        raw = json.loads(m.group(1))
        return {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _dims_disagreement(a: dict, b: dict, rel: float = 0.02) -> float | None:
    """Fraction of the union of dimension keys on which two agents disagree (missing counts as
    disagreement; numeric values agree within `rel` relative tolerance). None if no keys at all."""
    keys = set(a) | set(b)
    if not keys:
        return None
    agree = sum(
        1 for k in keys
        if k in a and k in b and abs(a[k] - b[k]) <= rel * max(abs(a[k]), abs(b[k]), 1e-9)
    )
    return 1.0 - agree / len(keys)


def _cds_round(*dims: dict) -> float | None:
    """Context Divergence Score for one round = mean pairwise dimension disagreement across the
    agents' stated beliefs (Paper-06 CDS operationalized on machine-comparable dimensions).
    0 = perfectly aligned context, 1 = no shared belief."""
    vals = [
        _dims_disagreement(dims[i], dims[j])
        for i in range(len(dims)) for j in range(i + 1, len(dims))
    ]
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


PLANNER_SYSTEM = (
    "You are the PLANNER in a mechanical CAD team. From the specification, produce a short "
    "numbered build plan (features, order of operations, datums) for a `build123d` Python "
    "implementation. Work in millimetres. Do NOT write code. End your reply with one line "
    "`DIMS: {\"name\": value, ...}` — a flat JSON object naming every governing dimension in mm "
    "(numeric values only)."
)

CODER_SYSTEM = (
    "You are the CODER in a mechanical CAD team. Implement the plan with the `build123d` Python "
    "library. Always assign the final solid to a top-level variable named `result`. Import "
    "everything you use. Work in millimetres. Reply with exactly one ```python code block, then "
    "one line `DIMS: {\"name\": value, ...}` — a flat JSON object of the governing dimensions (mm) "
    "your code implements."
)

CHECKER_SYSTEM = (
    "You are the CHECKER in a mechanical CAD team. You receive the original specification and "
    "kernel-measured properties of the part the coder built. Judge whether the part satisfies "
    "every requirement. Reply with: `VERDICT: PASS` or `VERDICT: REVISE`, a one-line reason "
    "(if REVISE, say exactly what to change), one line `DIMS: {\"name\": value, ...}` — the "
    "governing dimensions (mm) you believe the measured part actually has — and one line "
    "`CONFIDENCE: <0..1>`, your calibrated probability that every requirement is met."
)


def _format_props_for_checker(props: dict | None, error: str | None) -> str:
    if error:
        return f"Execution FAILED: {error}"
    if not props:
        return "Execution produced no measurable solid."
    keep = {k: props.get(k) for k in
            ("valid_solid", "watertight", "bbox", "volume", "com", "solid_count", "cylinders")}
    return "Kernel-measured properties of the built part:\n" + json.dumps(keep, indent=1)


class MultiAgent:
    """Planner -> coder -> checker with Paper-06 CDS drift instrumentation.

    The planner plans once; then up to `max_rounds` of coder -> execute -> checker. The episode
    reports done only when the CHECKER returns VERDICT: PASS (the system's completion claim).
    Each role states its dimensional beliefs on a `DIMS:` line; `cds` records one Context
    Divergence Score per round (planner vs coder vs checker pairwise disagreement)."""

    condition = "multi_agent"

    def __init__(self, llm: LLMClient, max_rounds: int = 3):
        self.llm = llm
        self.max_rounds = max_rounds

    def run(self, task: Task, executor: Executor) -> AgentOutput:
        in_tok = out_tok = 0
        transcript: list[dict] = []

        def call(system: str, content: str) -> str:
            nonlocal in_tok, out_tok
            msgs = [{"role": "user", "content": content}]
            reply = self.llm.complete(system, msgs)
            in_tok += reply.input_tokens
            out_tok += reply.output_tokens
            transcript.append({"role": "user", "content": content})
            transcript.append({"role": "assistant", "content": reply.text})
            return reply.text

        plan_text = call(PLANNER_SYSTEM, f"[PLANNER]\n{_user_spec(task)}")
        planner_dims = _parse_dims(plan_text)
        plan_body = _DIMS_RE.sub("", _CODE_RE.sub("", plan_text)).strip()
        # share the planner's dimension vocabulary so CDS measures value divergence, not naming noise
        dims_vocab = (f"\n\nIn your DIMS line, use exactly these dimension names: "
                      f"{sorted(planner_dims)}." if planner_dims else "")

        last_code, last_props, last_error = "", None, None
        conf: float | None = None
        done = False
        cds: list[float] = []
        feedback = ""
        rounds = 0

        for rounds in range(1, self.max_rounds + 1):
            coder_prompt = (f"[CODER]\n{_user_spec(task)}\n\nPlan from the planner:\n{plan_body}"
                            f"{dims_vocab}")
            if feedback:
                coder_prompt += f"\n\nChecker feedback on your previous attempt:\n{feedback}"
            coder_text = call(CODER_SYSTEM, coder_prompt)
            code, _, _ = _parse(coder_text)
            coder_dims = _parse_dims(coder_text)

            if code:
                last_code = code
                ex = executor.run(code)
                last_props, last_error = ex.props, ex.error
            else:
                last_error = "coder produced no ```python block"

            checker_prompt = (f"[CHECKER]\n{_user_spec(task)}\n\n"
                              f"{_format_props_for_checker(last_props, last_error)}{dims_vocab}")
            checker_text = call(CHECKER_SYSTEM, checker_prompt)
            checker_dims = _parse_dims(checker_text)
            cm = _CONF_RE.search(checker_text)
            conf = float(cm.group(1)) if cm else conf
            vm = _VERDICT_RE.search(checker_text)
            verdict = vm.group(1).upper() if vm else "REVISE"

            r = _cds_round(planner_dims, coder_dims, checker_dims)
            if r is not None:
                cds.append(r)

            if verdict == "PASS":
                done = True
                break
            reason = _VERDICT_RE.sub("", _DIMS_RE.sub("", checker_text)).strip()[:600]
            feedback = reason or "Checker rejected the part; re-derive dimensions from the spec."

        return AgentOutput(
            code=last_code, reported_done=done, confidence=conf, props=last_props,
            steps=rounds, input_tokens=in_tok, output_tokens=out_tok, transcript=transcript,
            error=last_error, cds=cds or None,
        )
