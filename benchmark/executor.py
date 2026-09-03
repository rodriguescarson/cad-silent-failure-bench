"""Run agent-produced CAD code and return a measured-properties dict.

`MockExecutor` returns preset properties (no kernel) so the harness/grader/runner can be tested
offline. `Build123dExecutor` runs the agent code in an isolated subprocess (`benchmark._extract`)
so OpenCascade stays out of the parent process and a crash/segfault can't take the runner down.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExecResult:
    props: dict | None        # measured-properties dict, or None if execution failed
    error: str | None = None
    raw: str = ""

    @property
    def valid(self) -> bool:
        return bool(self.props and self.props.get("valid_solid"))


class Executor:
    def run(self, code: str) -> ExecResult:
        raise NotImplementedError


@dataclass
class MockExecutor(Executor):
    """Returns props for whichever task-id marker appears in the code, ignoring real geometry."""
    props_by_marker: dict = field(default_factory=dict)
    default_props: dict | None = None

    def run(self, code: str) -> ExecResult:
        for marker, props in self.props_by_marker.items():
            if marker in code:
                return ExecResult(props=props, raw="mock")
        if self.default_props is not None:
            return ExecResult(props=self.default_props, raw="mock-default")
        return ExecResult(props=None, error="mock: no props for this code", raw="mock")


@dataclass
class Build123dExecutor(Executor):
    """Execute `code` (must assign a build123d solid/Part to `result`) and extract properties."""
    timeout_s: int = 60

    def run(self, code: str) -> ExecResult:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            code_path = f.name
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "benchmark._extract", code_path],
                capture_output=True, text=True, timeout=self.timeout_s,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
        except subprocess.TimeoutExpired:
            return ExecResult(props=None, error=f"timeout after {self.timeout_s}s")
        finally:
            Path(code_path).unlink(missing_ok=True)

        out = proc.stdout.strip()
        if proc.returncode != 0 and not out:
            return ExecResult(props=None, error=(proc.stderr or "nonzero exit").strip()[:2000], raw=proc.stderr)
        try:
            payload = json.loads(out.splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return ExecResult(props=None, error="could not parse extractor output", raw=out[:2000])
        if "error" in payload:
            return ExecResult(props=None, error=payload["error"], raw=out)
        return ExecResult(props=payload, raw=out)
