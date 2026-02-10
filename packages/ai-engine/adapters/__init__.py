"""LLM Adapter Layer — provider-agnostic interface to any LLM.

Usage:
    from packages.ai_engine.adapters import AdapterFactory, Message, ToolDefinition

    adapter = AdapterFactory.create("openai", api_key="sk-...")
    response = await adapter.complete([Message(role="user", content="Hello")])
"""

from .base import (
    BaseLLMAdapter,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
)
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter
from .factory import AdapterFactory
from .middleware import RetryMiddleware, CostTrackingMiddleware

__all__ = [
    # Base types
    "BaseLLMAdapter",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolDefinition",
    # Adapters
    "OpenAIAdapter",
    "AnthropicAdapter",
    # Factory
    "AdapterFactory",
    # Middleware
    "RetryMiddleware",
    "CostTrackingMiddleware",
]