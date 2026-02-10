"""Middleware for LLM adapters — retry, cost tracking, logging.

These wrap any adapter to add cross-cutting concerns without
modifying the adapter code. Uses the Decorator Pattern.

Usage:
    # Wrap any adapter with retry logic
    base_adapter = OpenAIAdapter(api_key="sk-...")
    adapter = RetryMiddleware(base_adapter, max_retries=3)

    # Stack multiple middleware
    adapter = RetryMiddleware(
        CostTrackingMiddleware(
            OpenAIAdapter(api_key="sk-...")
        )
    )
"""

import asyncio
import logging
import time
from typing import AsyncIterator

from .base import (
    BaseLLMAdapter,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class RetryMiddleware(BaseLLMAdapter):
    """Wraps an adapter to automatically retry failed API calls.

    Retries on:
    - Rate limit errors (429)
    - Server errors (500, 502, 503)
    - Connection timeouts

    Does NOT retry on:
    - Authentication errors (401) — retrying won't help
    - Bad request errors (400) — the request itself is wrong
    """

    def __init__(
        self,
        adapter: BaseLLMAdapter,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self._adapter = adapter
        self._max_retries = max_retries
        self._base_delay = base_delay    # First retry waits 1 second
        self._max_delay = max_delay      # Never wait more than 30 seconds

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """Call complete() with automatic retry on failure."""
        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._adapter.complete(
                    messages, tools, temperature, max_tokens, **kwargs
                )
                if attempt > 0:
                    logger.info("Succeeded on retry attempt %d", attempt)
                return response

            except Exception as e:
                last_error = e

                if not self._should_retry(e):
                    logger.error("Non-retryable error: %s", e)
                    raise

                if attempt < self._max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt + 1,
                        self._max_retries + 1,
                        str(e)[:100],
                        delay,
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        logger.error("All %d attempts failed. Last error: %s", self._max_retries + 1, last_error)
        raise last_error  # type: ignore

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream with retry — retries the entire stream on failure.

        Note: If a stream fails midway, we restart from the beginning.
        The user might see repeated text, but it's better than crashing.
        """
        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                async for token in self._adapter.stream(
                    messages, tools, temperature, max_tokens, **kwargs
                ):
                    yield token
                return  # Stream completed successfully

            except Exception as e:
                last_error = e

                if not self._should_retry(e):
                    raise

                if attempt < self._max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        "Stream attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt + 1,
                        self._max_retries + 1,
                        str(e)[:100],
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore

    # ── Delegate info methods to the inner adapter ────

    def supports_tool_calling(self) -> bool:
        return self._adapter.supports_tool_calling()

    def supports_streaming(self) -> bool:
        return self._adapter.supports_streaming()

    def max_context_window(self) -> int:
        return self._adapter.max_context_window()

    def model_name(self) -> str:
        return self._adapter.model_name()

    def provider_name(self) -> str:
        return self._adapter.provider_name()

    # ── Private helpers ───────────────────────────────

    def _should_retry(self, error: Exception) -> bool:
        """Determine if the error is retryable.

        Rate limits and server errors → retry
        Auth errors and bad requests → don't retry
        """
        error_str = str(error).lower()

        # Rate limit (429)
        if "rate" in error_str and "limit" in error_str:
            return True
        if "429" in error_str:
            return True

        # Server errors (5xx)
        if "500" in error_str or "502" in error_str or "503" in error_str:
            return True
        if "server" in error_str and "error" in error_str:
            return True

        # Connection issues
        if "timeout" in error_str or "connection" in error_str:
            return True
        if "overloaded" in error_str:
            return True

        return False

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Attempt 0: 1.0s
        Attempt 1: 2.0s
        Attempt 2: 4.0s
        ...
        Capped at max_delay (30s)
        """
        delay = self._base_delay * (2 ** attempt)
        return min(delay, self._max_delay)


class CostTrackingMiddleware(BaseLLMAdapter):
    """Wraps an adapter to log token usage and estimated cost per call.

    Useful for monitoring how much you're spending on LLM APIs.
    """

    # Approximate cost per 1M tokens (input/output) as of 2024
    COST_PER_MILLION = {
        "gpt-4o":           {"input": 2.50,  "output": 10.00},
        "gpt-4o-mini":      {"input": 0.15,  "output": 0.60},
        "gpt-4-turbo":      {"input": 10.00, "output": 30.00},
        "claude-sonnet-4-20250514":  {"input": 3.00,  "output": 15.00},
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-opus-20240229":    {"input": 15.00, "output": 75.00},
    }

    def __init__(self, adapter: BaseLLMAdapter):
        self._adapter = adapter
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.call_count = 0

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        response = await self._adapter.complete(
            messages, tools, temperature, max_tokens, **kwargs
        )
        self._track(response)
        return response

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        # Streaming doesn't return usage info, so we just pass through
        async for token in self._adapter.stream(
            messages, tools, temperature, max_tokens, **kwargs
        ):
            yield token

    def supports_tool_calling(self) -> bool:
        return self._adapter.supports_tool_calling()

    def supports_streaming(self) -> bool:
        return self._adapter.supports_streaming()

    def max_context_window(self) -> int:
        return self._adapter.max_context_window()

    def model_name(self) -> str:
        return self._adapter.model_name()

    def provider_name(self) -> str:
        return self._adapter.provider_name()

    def _track(self, response: LLMResponse) -> None:
        """Log and accumulate token usage and cost."""
        self.call_count += 1
        input_tokens = response.usage.get("input", 0)
        output_tokens = response.usage.get("output", 0)

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # Calculate cost
        model = response.model
        rates = self.COST_PER_MILLION.get(model, {"input": 0, "output": 0})
        cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        self.total_cost_usd += cost

        logger.info(
            "LLM call #%d [%s/%s]: %d in + %d out tokens | $%.4f (total: $%.4f)",
            self.call_count,
            response.provider,
            model,
            input_tokens,
            output_tokens,
            cost,
            self.total_cost_usd,
        )