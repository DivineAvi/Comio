"""OpenAI adapter — connects to GPT-4o, GPT-4-turbo, etc.

Translates between our standardized format and OpenAI's API format.
Supports: text completion, tool/function calling, streaming.
"""

import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from .base import (
    BaseLLMAdapter,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)


class OpenAIAdapter(BaseLLMAdapter):
    """Adapter for OpenAI models (GPT-4o, GPT-4-turbo, GPT-3.5-turbo).

    Usage:
        adapter = OpenAIAdapter(api_key="sk-...", model="gpt-4o")
        response = await adapter.complete([
            Message(role="user", content="Hello!")
        ])
    """

    # Context window sizes for common models
    CONTEXT_WINDOWS = {
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "gpt-4-turbo": 128_000,
        "gpt-4": 8_192,
        "gpt-3.5-turbo": 16_385,
    }

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    # ── Interface methods ─────────────────────────────

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """Send messages and get a complete response from OpenAI."""
        start_time = time.time()

        # Build the request arguments
        request_args = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add tools if provided
        if tools:
            request_args["tools"] = self._format_tools(tools)

        # Make the API call
        response = await self._client.chat.completions.create(**request_args)

        latency_ms = (time.time() - start_time) * 1000
        return self._parse_response(response, latency_ms)

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream response tokens from OpenAI one at a time.

        Yields individual text chunks as they arrive.
        The chat UI uses this so text appears in real-time.
        """
        request_args = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            request_args["tools"] = self._format_tools(tools)

        stream = await self._client.chat.completions.create(**request_args)

        async for chunk in stream:
            # Each chunk may contain a piece of text
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def supports_tool_calling(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def max_context_window(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, 128_000)

    def model_name(self) -> str:
        return self._model

    def provider_name(self) -> str:
        return "openai"

    # ── Private helpers — format conversion ───────────

    def _format_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our Message objects to OpenAI's message format.

        Our format:
            Message(role="user", content="Hello")

        OpenAI's format:
            {"role": "user", "content": "Hello"}
        """
        formatted = []
        for msg in messages:
            entry: dict = {"role": msg.role, "content": msg.content}

            # If the assistant made tool calls, include them
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": _dict_to_json(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            # If this is a tool result message
            if msg.role == "tool" and msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id

            formatted.append(entry)

        return formatted

    def _format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert our ToolDefinition objects to OpenAI's tool format.

        Our format:
            ToolDefinition(name="create_file", description="...", parameters={...})

        OpenAI's format:
            {"type": "function", "function": {"name": "create_file", "description": "...", "parameters": {...}}}
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _parse_response(self, response, latency_ms: float) -> LLMResponse:
        """Convert OpenAI's response to our standardized LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        # Parse tool calls if present
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=_json_to_dict(tc.function.arguments),
                    )
                )

        return LLMResponse(
            content=message.content or "",
            model=response.model,
            provider="openai",
            usage={
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
                "total": response.usage.total_tokens,
            },
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw_response=response.model_dump(),
            finish_reason=choice.finish_reason or "",
        )


# ── Utility functions ─────────────────────────────

import json

def _dict_to_json(d: dict) -> str:
    """Convert a dict to a JSON string (OpenAI expects string arguments)."""
    return json.dumps(d)

def _json_to_dict(s: str) -> dict:
    """Parse a JSON string to a dict (OpenAI returns string arguments)."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {"raw": s}