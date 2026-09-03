"""Orchestrate the eval sweep: tasks x agents(models, conditions) x seeds -> JSONL + metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .executor import Executor
from .grader import grade
from .metrics import summarize
from .schema import Task


@dataclass
class AgentSpec:
    agent: object   # has .condition and .run(task, executor) -> AgentOutput
    model: str      # the underlying model name, recorded per record


def run_suite(
    tasks: list[Task],
    agent_specs: list[AgentSpec],
    executor: Executor,
    seeds: int = 1,
    out_path: str | Path | None = None,
    resume: bool = False,
) -> list[dict]:
    records: list[dict] = []
    done: set[tuple] = set()
    if resume and out_path and Path(out_path).exists():
        for line in Path(out_path).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                records.append(r)
                done.add((r["task_id"], r["model"], r["condition"], r["seed"]))
    fh = open(out_path, "a" if resume else "w") if out_path else None
    # full multi-turn transcripts, persisted per attempt (reviewers + taxonomy coding need them)
    th = open(str(out_path) + ".transcripts.jsonl", "a" if resume else "w") if out_path else None
    try:
        for task in tasks:
            for spec in agent_specs:
                for seed in range(seeds):
                    cond = getattr(spec.agent, "condition", "unknown")
                    if (task.id, spec.model, cond, seed) in done:
                        continue
                    try:
                        out = spec.agent.run(task, executor)
                    except Exception as e:  # one dead attempt must not kill the sweep
                        from .agents import AgentOutput
                        out = AgentOutput(code="", reported_done=False, confidence=None,
                                          props=None, steps=0,
                                          error=f"attempt aborted: {type(e).__name__}: {e}"[:500])
                    g = grade(task, out.props)
                    rec = {
                        "task_id": task.id,
                        "tier": task.tier,
                        "model": spec.model,
                        "condition": getattr(spec.agent, "condition", "unknown"),
                        "seed": seed,
                        "attempt": 0,
                        "reported_done": out.reported_done,
                        "confidence": out.confidence,
                        "passed": g.passed,
                        "valid_solid": g.valid_solid,
                        "score": round(g.score, 4),
                        "steps": out.steps,
                        "input_tokens": out.input_tokens,
                        "output_tokens": out.output_tokens,
                        "error": out.error,
                        "failed_checks": [c.id for c in g.failed_checks()],
                        "code": out.code,  # for post-hoc error-mode coding (C2 taxonomy)
                        "cds": getattr(out, "cds", None),  # multi-agent drift (Paper-06 CDS)
                    }
                    records.append(rec)
                    if fh:
                        fh.write(json.dumps(rec) + "\n")
                        fh.flush()  # long sweeps: progress must be visible + restartable
                    if th:
                        th.write(json.dumps({
                            "task_id": task.id, "model": spec.model, "condition": cond,
                            "seed": seed, "transcript": getattr(out, "transcript", []),
                        }) + "\n")
                        th.flush()
    finally:
        if fh:
            fh.close()
        if th:
            th.close()
    return records


def main() -> None:
    import argparse
    from .schema import load_suite

    ap = argparse.ArgumentParser(description="Run the agentic-CAD benchmark.")
    ap.add_argument("--tasks", default="tasks", help="task suite directory")
    ap.add_argument("--out", default="data/results.jsonl")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--provider", choices=["anthropic", "openai", "openrouter"],
                    default="anthropic")
    ap.add_argument("--max-steps", type=int, default=4)
    ap.add_argument("--conditions", nargs="+", default=["single_shot", "tool_use"],
                    choices=["single_shot", "tool_use", "multi_agent", "tool_use_legacy"])
    ap.add_argument("--resume", action="store_true",
                    help="skip (task,model,condition,seed) combos already in --out; append")
    args = ap.parse_args()

    from .executor import Build123dExecutor
    from .agents import MultiAgent, SingleShotAgent, ToolUseAgent
    if args.provider == "anthropic":
        from .llm import AnthropicLLM as Provider
    elif args.provider == "openrouter":
        from .llm import OpenRouterLLM as Provider
    else:
        from .llm import OpenAILLM as Provider
    llm = Provider(args.model)

    tasks = load_suite(args.tasks)
    by_name = {
        "single_shot": lambda: SingleShotAgent(llm),
        "tool_use": lambda: ToolUseAgent(llm, args.max_steps),
        "multi_agent": lambda: MultiAgent(llm, max_rounds=args.max_steps - 1),
        "tool_use_legacy": lambda: ToolUseAgent(llm, args.max_steps, legacy_claim=True),
    }
    specs = [AgentSpec(by_name[c](), llm.name) for c in args.conditions]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    records = run_suite(tasks, specs, Build123dExecutor(), seeds=args.seeds, out_path=args.out,
                        resume=args.resume)
    print(json.dumps(summarize(records), indent=2))


if __name__ == "__main__":
    main()
