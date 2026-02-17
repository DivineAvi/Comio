"""OpenAI embedding adapter."""

import logging
from openai import AsyncOpenAI

from .base import BaseEmbeddingAdapter, EmbeddingResult

logger = logging.getLogger(__name__)


class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """OpenAI embedding adapter using text-embedding-3-small model."""

    # Model dimensions mapping
    _MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """Initialize OpenAI embedding adapter.
        
        Args:
            api_key: OpenAI API key
            model: Model name (default: text-embedding-3-small)
        """
        self._api_key = api_key
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)
        
        if model not in self._MODEL_DIMENSIONS:
            logger.warning(
                f"Unknown model {model}, defaulting to 1536 dimensions. "
                f"Known models: {list(self._MODEL_DIMENSIONS.keys())}"
            )

    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            EmbeddingResult with vector and token count
        """
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        
        return EmbeddingResult(
            embedding=response.data[0].embedding,
            tokens_used=response.usage.total_tokens,
        )

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed multiple texts in a batch (more efficient than individual calls).
        
        OpenAI supports up to 2048 texts per batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of EmbeddingResults in same order as input
        """
        if not texts:
            return []
        
        if len(texts) > 2048:
            logger.warning(
                f"Batch size {len(texts)} exceeds OpenAI limit of 2048. "
                "Consider splitting into smaller batches."
            )
        
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        
        # OpenAI returns results in the same order as input
        results = []
        tokens_per_text = response.usage.total_tokens // len(texts)
        
        for data in response.data:
            results.append(
                EmbeddingResult(
                    embedding=data.embedding,
                    tokens_used=tokens_per_text,  # Approximate distribution
                )
            )
        
        return results

    def dimensions(self) -> int:
        """Return embedding dimensions for this model.
        
        Returns:
            Number of dimensions (1536 for text-embedding-3-small)
        """
        return self._MODEL_DIMENSIONS.get(self._model, 1536)