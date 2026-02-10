"""Adapter Factory and Registry — create LLM adapters by name.

Factory Pattern: Instead of importing concrete classes everywhere,
ask the factory to create the right adapter based on a config string.

Registry Pattern: New adapters can be registered at runtime without
modifying this file. Third-party providers just call register().

Usage:
    # Basic usage
    adapter = AdapterFactory.create("openai", api_key="sk-...")

    # With specific model
    adapter = AdapterFactory.create("anthropic", api_key="sk-ant-...", model="claude-sonnet-4-20250514")

    # Register a custom adapter
    AdapterFactory.register("my-provider", MyCustomAdapter)
    adapter = AdapterFactory.create("my-provider", api_key="...")
"""

import logging

from .base import BaseLLMAdapter
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter

logger = logging.getLogger(__name__)


class AdapterFactory:
    """Creates LLM adapters by provider name.

    This is the ONLY place in the codebase that knows about
    concrete adapter classes. Everything else uses BaseLLMAdapter.
    """

    # Registry: maps provider names to adapter classes
    _registry: dict[str, type[BaseLLMAdapter]] = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
    }

    # Default models per provider (used when no model is specified)
    _default_models: dict[str, str] = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
    }

    @classmethod
    def create(
        cls,
        provider: str,
        api_key: str,
        model: str | None = None,
        **kwargs,
    ) -> BaseLLMAdapter:
        """Create an adapter for the given provider.

        Args:
            provider: Provider name ("openai", "anthropic", etc.)
            api_key: API key for the provider
            model: Specific model to use (optional, uses default if not given)
            **kwargs: Additional provider-specific arguments

        Returns:
            An instance of the appropriate adapter

        Raises:
            ValueError: If the provider is not registered

        Example:
            adapter = AdapterFactory.create("openai", api_key="sk-...")
            response = await adapter.complete([Message(role="user", content="Hi")])
        """
        # Normalize the provider name (handle case differences)
        provider = provider.lower().strip()

        if provider not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"Unknown LLM provider: '{provider}'. "
                f"Available providers: {available}"
            )

        adapter_class = cls._registry[provider]
        model = model or cls._default_models.get(provider, "")

        logger.info("Creating %s adapter with model: %s", provider, model)

        return adapter_class(api_key=api_key, model=model, **kwargs)

    @classmethod
    def register(
        cls,
        provider: str,
        adapter_class: type[BaseLLMAdapter],
        default_model: str = "",
    ) -> None:
        """Register a new adapter for a provider.

        This allows adding custom providers without modifying this file.

        Args:
            provider: Provider name (e.g., "my-custom-llm")
            adapter_class: The adapter class (must inherit BaseLLMAdapter)
            default_model: Default model for this provider

        Example:
            class MyAdapter(BaseLLMAdapter):
                ...

            AdapterFactory.register("my-provider", MyAdapter, "my-model-v1")
        """
        if not issubclass(adapter_class, BaseLLMAdapter):
            raise TypeError(
                f"{adapter_class.__name__} must inherit from BaseLLMAdapter"
            )

        cls._registry[provider.lower().strip()] = adapter_class
        if default_model:
            cls._default_models[provider.lower().strip()] = default_model

        logger.info("Registered LLM adapter: %s → %s", provider, adapter_class.__name__)

    @classmethod
    def available_providers(cls) -> list[str]:
        """List all registered provider names."""
        return sorted(cls._registry.keys())

    @classmethod
    def is_registered(cls, provider: str) -> bool:
        """Check if a provider is registered."""
        return provider.lower().strip() in cls._registry