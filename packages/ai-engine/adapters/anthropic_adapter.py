"""Anthropic adapter — connects to Claude 3.5 Sonnet, Claude 3 Opus, etc.

Translates between our standardized format and Anthropic's API format.
Supports: text completion, tool/function calling, streaming.

Key difference from OpenAI:
- System message is a separate parameter, not in the messages list
- Tool results use a different format (tool_result content blocks)
- Response content is an array of blocks, not a plain string
"""

import json
import time
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from .base import (
    BaseLLMAdapter,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)


class AnthropicAdapter(BaseLLMAdapter):
    """Adapter for Anthropic models (Claude 3.5 Sonnet, Claude 3 Opus, etc.).

    Usage:
        adapter = AnthropicAdapter(api_key="sk-ant-...", model="claude-sonnet-4-20250514")
        response = await adapter.complete([
            Message(role="user", content="Hello!")
        ])
    """

    CONTEXT_WINDOWS = {
        "claude-sonnet-4-20250514": 200_000,
        "claude-3-5-sonnet-20241022": 200_000,
        "claude-3-opus-20240229": 200_000,
        "claude-3-haiku-20240307": 200_000,
    }

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=api_key)
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
        """Send messages and get a complete response from Anthropic."""
        start_time = time.time()

        # Anthropic requires system message as a separate parameter
        system_msg, chat_messages = self._split_system_message(messages)

        request_args = {
            "model": self._model,
            "messages": self._format_messages(chat_messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_msg:
            request_args["system"] = system_msg

        if tools:
            request_args["tools"] = self._format_tools(tools)
        
        # Merge any additional kwargs
        request_args.update(kwargs)

        response = await self._client.messages.create(**request_args)

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
        """Stream response tokens from Anthropic one at a time."""
        system_msg, chat_messages = self._split_system_message(messages)

        request_args = {
            "model": self._model,
            "messages": self._format_messages(chat_messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_msg:
            request_args["system"] = system_msg

        if tools:
            request_args["tools"] = self._format_tools(tools)
        
        # Merge any additional kwargs
        request_args.update(kwargs)

        async with self._client.messages.stream(**request_args) as stream:
            async for text in stream.text_stream:
                yield text

    def supports_tool_calling(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def max_context_window(self) -> int:
        return self.CONTEXT_WINDOWS.get(self._model, 200_000)

    def model_name(self) -> str:
        return self._model

    def provider_name(self) -> str:
        return "anthropic"

    # ── Private helpers — format conversion ───────────

    def _split_system_message(self, messages: list[Message]) -> tuple[str, list[Message]]:
        """Extract the system message from the list.

        Anthropic wants:
            messages.create(system="You are...", messages=[...])

        NOT:
            messages.create(messages=[{"role": "system", "content": "You are..."}])
        """
        system_content = ""
        chat_messages = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                chat_messages.append(msg)

        return system_content, chat_messages

    def _format_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our Message objects to Anthropic's message format."""
        formatted = []

        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                # Assistant message with tool calls — Anthropic uses content blocks
                content_blocks = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                formatted.append({"role": "assistant", "content": content_blocks})

            elif msg.role == "tool":
                # Tool result — Anthropic uses "user" role with tool_result content block
                formatted.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })

            else:
                # Regular user or assistant message
                formatted.append({"role": msg.role, "content": msg.content})

        return formatted

    def _format_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert our ToolDefinition objects to Anthropic's tool format.

        Anthropic format:
            {"name": "create_file", "description": "...", "input_schema": {...}}

        Note: Anthropic uses "input_schema" while OpenAI uses "parameters"
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    def _parse_response(self, response, latency_ms: float) -> LLMResponse:
        """Convert Anthropic's response to our standardized LLMResponse.

        Anthropic response.content is a LIST of blocks:
            [
                {"type": "text", "text": "I'll create that file"},
                {"type": "tool_use", "id": "123", "name": "create_file", "input": {...}}
            ]
        """
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        return LLMResponse(
            content=content,
            model=response.model,
            provider="anthropic",
            usage={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "total": response.usage.input_tokens + response.usage.output_tokens,
            },
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw_response=response.model_dump(),
            finish_reason=response.stop_reason or "",
        )