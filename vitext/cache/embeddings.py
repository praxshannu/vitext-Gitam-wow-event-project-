"""
Embeddings — thin wrapper around sentence-transformers for semantic caching.

Generates embeddings for scene descriptions so the cache can do similarity
lookups ("have we rendered something like this before?").

Uses a small, fast model (all-MiniLM-L6-v2 by default) that runs entirely
locally — no cloud calls needed.
"""

import numpy as np
from typing import Optional


class EmbeddingModel:
    """
    Lazy-loaded sentence-transformer for local embedding generation.

    The model is loaded on first use and cached for subsequent calls.

    Usage:
        embedder = EmbeddingModel()
        vec = embedder.embed("Show a standard normal distribution curve")
        similarity = embedder.cosine_similarity(vec1, vec2)
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for caching. "
                    "Install with: pip install sentence-transformers"
                )

    def embed(self, text: str) -> np.ndarray:
        """
        Generate an embedding vector for a text string.

        Args:
            text: The scene description to embed.

        Returns:
            numpy array of shape (dim,) — the embedding vector.
        """
        self._load_model()
        return self._model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """
        Generate embeddings for multiple texts at once.

        Args:
            texts: List of scene descriptions.

        Returns:
            numpy array of shape (n, dim).
        """
        self._load_model()
        return self._model.encode(texts, normalize_embeddings=True)

    @staticmethod
    def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """
        Compute cosine similarity between two normalized vectors.

        Since we normalize embeddings during encode, this is just a dot product.
        """
        return float(np.dot(vec_a, vec_b))
