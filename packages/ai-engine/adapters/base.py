"""Base LLM adapter — the contract all providers must follow.

This is the Strategy Pattern:
- Define a common interface (BaseLLMAdapter)
- Each provider (OpenAI, Anthropic, Ollama) implements it
- Your application code only talks to the interface, never the concrete class

Why this matters:
- Switch providers with ONE config change (no code changes)
- Test with mock adapters (no real API calls)
- Add new providers without touching existing code
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ToolCall:
    """Represents a tool/function call requested by the LLM.

    When the LLM decides to use a tool (e.g., create_file, run_command),
    it returns a ToolCall instead of regular text.
    """
    id: str                    # Unique ID for this call (provider-generated)
    name: str                  # Tool name, e.g. "create_file"
    arguments: dict            # Tool arguments, e.g. {"path": "app.py", "content": "..."}


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider.

    No matter which provider you use (OpenAI, Anthropic, Ollama),
    you always get back this same structure.
    """
    content: str                           # The text response (empty if tool_calls)
    model: str                             # Which model was used, e.g. "gpt-4o"
    provider: str                          # Which provider, e.g. "openai"
    usage: dict = field(default_factory=dict)  # Token counts: {"input": 100, "output": 50, "total": 150}
    latency_ms: float = 0.0               # How long the API call took
    tool_calls: list[ToolCall] = field(default_factory=list)  # Tool calls (if any)
    raw_response: dict = field(default_factory=dict)          # Full raw API response for debugging
    finish_reason: str = ""                # Why the LLM stopped: "stop", "tool_calls", "length"


@dataclass
class Message:
    """A single message in a conversation.

    Conversations are lists of messages:
        [
            Message(role="system", content="You are Comio..."),
            Message(role="user", content="Create a Flask API"),
            Message(role="assistant", content="I'll create that for you..."),
        ]
    """
    role: str                                    # "system", "user", "assistant", "tool"
    content: str = ""                            # The message text
    tool_calls: list[ToolCall] | None = None     # Tool calls made by assistant
    tool_call_id: str | None = None              # ID of the tool call this message responds to (for role="tool")
    name: str | None = None                      # Tool name (for role="tool" messages)


@dataclass
class ToolDefinition:
    """Definition of a tool the LLM can use.

    This tells the LLM: "Here's a tool you can call, here's what it does,
    and here are the parameters it accepts."
    """
    name: str                    # e.g. "create_file"
    description: str             # e.g. "Create or overwrite a file in the project"
    parameters: dict             # JSON Schema for the parameters


class BaseLLMAdapter(ABC):
    """Abstract base class for all LLM providers.

    Every provider (OpenAI, Anthropic, Ollama) must implement ALL
    of these methods. If they don't, Python raises an error.

    Usage:
        adapter = OpenAIAdapter(api_key="sk-...")
        response = await adapter.complete([
            Message(role="user", content="Hello!")
        ])
        print(response.content)  # "Hello! How can I help?"
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """Send messages to the LLM and get a complete response.

        This waits for the FULL response before returning.
        Use this when you need the complete answer at once.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream the response token-by-token.

        Use this for the chat UI — shows text appearing in real-time
        instead of a loading spinner.

        Usage:
            async for token in adapter.stream(messages):
                send_to_websocket(token)  # "Hello" " world" "!" ...
        """
        ...

    @abstractmethod
    def supports_tool_calling(self) -> bool:
        """Does this provider support native tool/function calling?

        OpenAI, Anthropic: True
        Some Ollama models: False (would need prompt-based tool calling)
        """
        ...

    @abstractmethod
    def supports_streaming(self) -> bool:
        """Does this provider support streaming responses?"""
        ...

    @abstractmethod
    def max_context_window(self) -> int:
        """Maximum number of tokens this model can handle (input + output).

        GPT-4o: 128,000
        Claude 3.5 Sonnet: 200,000
        Llama 3: 8,000
        """
        ...

    @abstractmethod
    def model_name(self) -> str:
        """The model identifier string, e.g. 'gpt-4o', 'claude-3-5-sonnet'."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """The provider identifier, e.g. 'openai', 'anthropic', 'ollama'."""
        ...