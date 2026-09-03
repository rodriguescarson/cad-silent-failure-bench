"""LLM client abstraction.

`MockLLM` lets the whole pipeline run offline (no keys) for tests/dry-runs. Real providers are thin
adapters; pin the model id + record it in every result so runs are a dated snapshot (see PLAN.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LLMReply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient:
    """Protocol: .name (str) and .complete(system, user_or_messages) -> LLMReply."""
    name: str

    def complete(self, system: str, messages: list[dict]) -> LLMReply:  # messages: [{role, content}]
        raise NotImplementedError


class MockLLM(LLMClient):
    """Returns a canned reply keyed by a marker in the latest user message.

    `replies` maps a substring found in the prompt -> reply text. Used so dry-runs and unit tests
    exercise the full agent/grader/runner path without network or API keys.
    """

    def __init__(self, replies: dict[str, str], name: str = "mock"):
        self.replies = replies
        self.name = name

    def complete(self, system: str, messages: list[dict]) -> LLMReply:
        prompt = "\n".join(m["content"] for m in messages)
        for key, text in self.replies.items():
            if key in prompt:
                return LLMReply(text=text, input_tokens=len(prompt) // 4, output_tokens=len(text) // 4)
        # default: claim done with no code (will fail grading) — models a non-compliant agent
        return LLMReply(text="DONE\nCONFIDENCE: 0.5\n```python\nresult = None\n```")


class AnthropicLLM(LLMClient):
    """Adapter for the Anthropic Messages API. Requires `anthropic` + ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 4096):
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise ImportError("pip install anthropic, and set ANTHROPIC_API_KEY") from e
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from anthropic import Anthropic
        self._client = Anthropic()
        self.model = model
        self.name = model
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: list[dict]) -> LLMReply:
        resp = self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=system, messages=messages,
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return LLMReply(text=text, input_tokens=resp.usage.input_tokens,
                        output_tokens=resp.usage.output_tokens)


class OpenAILLM(LLMClient):
    """Adapter for OpenAI chat models. Requires `openai` + OPENAI_API_KEY."""

    max_tokens = 4096  # cap output; also bounds OpenRouter's per-call credit reservation

    def __init__(self, model: str = "gpt-5"):
        try:
            import openai  # noqa: F401
        except ImportError as e:
            raise ImportError("pip install openai, and set OPENAI_API_KEY") from e
        from openai import OpenAI
        self._client = OpenAI()
        self.model = model
        self.name = model

    def complete(self, system: str, messages: list[dict]) -> LLMReply:
        import time

        msgs = [{"role": "system", "content": system}, *messages]
        last_err: Exception | None = None
        for attempt in range(3):  # transient 5xx/overload happen, esp. on OpenRouter
            try:
                resp = self._client.chat.completions.create(
                    model=self.model, messages=msgs, max_tokens=self.max_tokens)
                text = resp.choices[0].message.content or ""
                u = resp.usage
                return LLMReply(text=text, input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                                output_tokens=getattr(u, "completion_tokens", 0) or 0)
            except Exception as e:
                last_err = e
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"{self.name}: LLM call failed after 3 attempts: {last_err}")


class OpenRouterLLM(OpenAILLM):
    """Any model on OpenRouter (deepseek/qwen/openai/kimi/...) via its OpenAI-compatible API.
    Requires `openai` + OPENROUTER_API_KEY."""

    def __init__(self, model: str):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("pip install openai, and set OPENROUTER_API_KEY") from e
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        # explicit timeout: some hosted open-weight endpoints hang far past the 600s SDK default
        self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                              timeout=180.0, max_retries=1)
        self.model = model
        self.name = model
