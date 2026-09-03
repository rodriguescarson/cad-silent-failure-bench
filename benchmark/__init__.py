"""Agentic-CAD reliability benchmark (Paper 10).

Layers, deliberately decoupled so the framework is testable without OpenCascade or API keys:

    schema     task / check definitions (pure python)
    grader     evaluate checks against a measured-properties dict (pure python)
    metrics    aggregate results -> success@k, silent-failure rate, calibration (pure python)
    llm        LLMClient protocol + MockLLM + real-provider stubs
    executor   run agent-produced CAD code -> measured properties (build123d subprocess) | MockExecutor
    agents     SingleShot / ToolUse (ReAct) / MultiAgent runners
    runner     orchestrate tasks x models x conditions -> JSONL logs + metrics

Only `executor`'s build123d backend and `llm`'s real providers need external deps; everything
else runs (and is unit-tested) with the standard library alone.
"""

__all__ = ["schema", "grader", "metrics"]
