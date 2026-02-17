"""Embedding adapter factory — create embedding adapters by provider name.

Factory Pattern: Similar to LLM adapters, this allows creating embedding
adapters without importing concrete classes everywhere.
"""

import logging

from .base import BaseEmbeddingAdapter
from .openai_adapter import OpenAIEmbeddingAdapter

logger = logging.getLogger(__name__)


class EmbeddingFactory:
    """Creates embedding adapters by provider name."""

    # Registry: maps provider names to adapter classes
    _registry: dict[str, type[BaseEmbeddingAdapter]] = {
        "openai": OpenAIEmbeddingAdapter,
    }

    # Default models per provider
    _default_models: dict[str, str] = {
        "openai": "text-embedding-3-small",
    }

    # Default dimensions per provider (for reference)
    _default_dimensions: dict[str, int] = {
        "openai": 1536,
    }

    @classmethod
    def create(
        cls,
        provider: str,
        api_key: str,
        model: str | None = None,
    ) -> BaseEmbeddingAdapter:
        """Create an embedding adapter for the given provider.
        
        Args:
            provider: Provider name ("openai", etc.)
            api_key: API key for the provider
            model: Specific model to use (optional, uses default if not given)
            
        Returns:
            An instance of the appropriate adapter
            
        Raises:
            ValueError: If the provider is not registered
            
        Example:
            adapter = EmbeddingFactory.create("openai", api_key="sk-...")
            result = await adapter.embed("Hello world")
        """
        # Normalize provider name
        provider = provider.lower().strip()

        if provider not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"Unknown embedding provider: '{provider}'. "
                f"Available providers: {available}"
            )

        adapter_class = cls._registry[provider]
        model = model or cls._default_models.get(provider, "")

        logger.info("Creating %s embedding adapter with model: %s", provider, model)

        return adapter_class(api_key=api_key, model=model)

    @classmethod
    def register(
        cls,
        provider: str,
        adapter_class: type[BaseEmbeddingAdapter],
        default_model: str = "",
        default_dimensions: int = 1536,
    ) -> None:
        """Register a new embedding adapter.
        
        This allows adding custom providers without modifying this file.
        
        Args:
            provider: Provider name (e.g., "ollama")
            adapter_class: The adapter class (must inherit BaseEmbeddingAdapter)
            default_model: Default model for this provider
            default_dimensions: Default vector dimensions
            
        Example:
            class MyEmbedder(BaseEmbeddingAdapter):
                ...
            
            EmbeddingFactory.register("my-provider", MyEmbedder, "my-model-v1", 768)
        """
        if not issubclass(adapter_class, BaseEmbeddingAdapter):
            raise TypeError(
                f"{adapter_class.__name__} must inherit from BaseEmbeddingAdapter"
            )

        cls._registry[provider.lower().strip()] = adapter_class
        if default_model:
            cls._default_models[provider.lower().strip()] = default_model
        if default_dimensions:
            cls._default_dimensions[provider.lower().strip()] = default_dimensions

        logger.info(
            "Registered embedding adapter: %s → %s",
            provider,
            adapter_class.__name__
        )

    @classmethod
    def available_providers(cls) -> list[str]:
        """List all registered provider names."""
        return sorted(cls._registry.keys())

    @classmethod
    def is_registered(cls, provider: str) -> bool:
        """Check if a provider is registered."""
        return provider.lower().strip() in cls._registry