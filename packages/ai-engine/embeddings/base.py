"""Base embedding adapter interface.

All embedding providers (OpenAI, Ollama, etc.) implement this interface.
Follows the same adapter pattern as LLM adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """Result from embedding a text."""
    embedding: list[float]  # The vector representation
    tokens_used: int        # Number of tokens processed


class BaseEmbeddingAdapter(ABC):
    """Abstract base class for embedding adapters.
    
    All embedding providers must implement this interface.
    """

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single text into a vector.
        
        Args:
            text: Text to embed
            
        Returns:
            EmbeddingResult with vector and token count
        """
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed multiple texts in a single batch (more efficient).
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of EmbeddingResults
        """
        ...

    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of embeddings from this adapter.
        
        Returns:
            Number of dimensions (e.g., 1536 for text-embedding-3-small)
        """
        ...