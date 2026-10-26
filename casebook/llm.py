"""One small interface over Anthropic and OpenAI.

Everything else calls `LLM.complete()`, so tests swap in a fake and the evals
can compare providers without touching the pipeline.

The library goes in its own system block marked for prompt caching. It is
identical on every question, so after the first call it is billed at the
cached-input rate.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Usage:
    input: int = 0   # all input tokens, cached ones included
    cached: int = 0  # the part of `input` read from the prompt cache
    output: int = 0
    written: int = 0  # the part of `input` written to the cache (billed at a premium)

    def add(self, other: "Usage") -> None:
        self.input += other.input
        self.cached += other.cached
        self.output += other.output
        self.written += other.written


@dataclass
class Completion:
    text: str = ""
    tool_call: dict | None = None  # {"name": ..., "input": {...}} when the model called a tool
    usage: Usage = field(default_factory=Usage)


class LLM(Protocol):
    def complete(self, instructions: str, library: str, messages: list[dict],
                 tools: list[dict] | None = None, max_tokens: int = 2000) -> Completion: ...


class AnthropicLLM:
    def __init__(self, model: str | None = None):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")

    def complete(self, instructions, library, messages, tools=None, max_tokens=2000):
        kwargs = {}
        if tools:
            kwargs["tools"] = tools
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[
                {"type": "text", "text": instructions},
                {"type": "text", "text": "CASE STUDIES:\n\n" + library,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=messages,
            **kwargs,
        )
        # Anthropic reports cache reads and writes separately from input_tokens;
        # Usage.input is the total, matching OpenAI's convention.
        u = resp.usage
        cached = getattr(u, "cache_read_input_tokens", 0) or 0
        written = getattr(u, "cache_creation_input_tokens", 0) or 0
        usage = Usage(u.input_tokens + cached + written, cached, u.output_tokens, written)
        for b in resp.content:
            if b.type == "tool_use":
                return Completion(tool_call={"name": b.name, "input": dict(b.input or {})},
                                  usage=usage)
        text = "".join(b.text for b in resp.content if b.type == "text")
        return Completion(text=text.strip(), usage=usage)


class OpenAILLM:
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4.1")

    def complete(self, instructions, library, messages, tools=None, max_tokens=2000):
        kwargs = {}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["input_schema"]}} for t in tools]
        # OpenAI caches a long, identical prompt prefix automatically.
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system",
                       "content": instructions + "\n\nCASE STUDIES:\n\n" + library},
                      *messages],
            **kwargs,
        )
        u = resp.usage
        details = getattr(u, "prompt_tokens_details", None)
        usage = Usage(u.prompt_tokens, getattr(details, "cached_tokens", 0) or 0,
                      u.completion_tokens)
        msg = resp.choices[0].message
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            return Completion(tool_call={"name": tc.function.name, "input": args},
                              usage=usage)
        return Completion(text=(msg.content or "").strip(), usage=usage)


def default_llm() -> LLM:
    """Pick a provider from LLM_PROVIDER, or from whichever API key is set."""
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    if not provider:
        provider = "openai" if (os.environ.get("OPENAI_API_KEY")
                                and not os.environ.get("ANTHROPIC_API_KEY")) else "anthropic"
    return OpenAILLM() if provider == "openai" else AnthropicLLM()


def parse_json(raw: str) -> dict:
    """Parse the model's JSON, tolerating code fences and stray prose around it.
    Returns {} when nothing parses, so callers can fail gracefully."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return {}
        try:
            out = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return {}
    return out if isinstance(out, dict) else {}
