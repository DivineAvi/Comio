"""Embedding adapters — convert text to vectors."""

from .base import BaseEmbeddingAdapter, EmbeddingResult
from .openai_adapter import OpenAIEmbeddingAdapter
from .factory import EmbeddingFactory

__all__ = [
    "BaseEmbeddingAdapter",
    "EmbeddingResult",
    "OpenAIEmbeddingAdapter",
    "EmbeddingFactory",
]