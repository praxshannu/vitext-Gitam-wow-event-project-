"""
Scene Cache — SQLite + sentence-transformer embeddings for reusing rendered scenes.

When the Script Agent produces a scene description like "Show a standard normal
distribution curve", the cache checks if a semantically similar scene was already
generated. If the cosine similarity exceeds the threshold (default 0.92), the
cached Manim code and/or rendered .mp4 are returned, skipping the Code Agent
and Renderer entirely.

Storage:
- SQLite for metadata (scene descriptions, code, file paths, timestamps)
- Embedding vectors stored as BLOBs in the same DB
- Rendered .mp4 files stay on disk; the cache stores their paths

This is all local — no cloud vector DB needed. Can be upgraded to Pinecone/Redis
later if the cache grows beyond ~10K entries.
"""

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from vitext.config import PipelineConfig, default_config
from vitext.cache.embeddings import EmbeddingModel


@dataclass
class CacheEntry:
    """A cached scene record."""
    cache_id: int
    description: str
    manim_code: str
    class_name: str
    video_path: Optional[str]      # Path to rendered .mp4 (may no longer exist)
    similarity: float = 0.0        # Set during lookup
    created_at: float = 0.0
    hit_count: int = 0


class SceneCache:
    """
    Semantic cache for rendered Manim scenes.

    Usage:
        cache = SceneCache(config)

        # Check cache before generating
        hit = cache.lookup("Show a standard normal distribution curve")
        if hit:
            print(f"Cache hit! Similarity: {hit.similarity:.3f}")
            print(hit.manim_code)
        else:
            # Generate the scene normally...
            # Then store it
            cache.store(
                description="Show a standard normal distribution curve",
                manim_code=code,
                class_name="Scene02NormalDist",
                video_path=str(video_path),
            )
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self.config.ensure_directories()
        self.db_path = self.config.cache_db_path
        self.threshold = self.config.cache_similarity_threshold
        self.embedder = EmbeddingModel(self.config.embedding_model)
        self._init_db()

    def _init_db(self):
        """Create the cache table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scene_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    manim_code TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    video_path TEXT,
                    embedding BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scene_cache_created
                ON scene_cache(created_at DESC)
            """)
            conn.commit()

    def lookup(self, description: str) -> Optional[CacheEntry]:
        """
        Search the cache for a semantically similar scene.

        Args:
            description: The scene description to match against.

        Returns:
            CacheEntry if a match above the threshold is found, else None.
        """
        query_vec = self.embedder.embed(description)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, description, manim_code, class_name, video_path, "
                "embedding, created_at, hit_count FROM scene_cache"
            ).fetchall()

        if not rows:
            return None

        best_match = None
        best_similarity = -1.0

        for row in rows:
            cache_id, desc, code, cls_name, vid_path, emb_blob, created, hits = row
            cached_vec = np.frombuffer(emb_blob, dtype=np.float32)
            sim = self.embedder.cosine_similarity(query_vec, cached_vec)

            if sim > best_similarity:
                best_similarity = sim
                best_match = CacheEntry(
                    cache_id=cache_id,
                    description=desc,
                    manim_code=code,
                    class_name=cls_name,
                    video_path=vid_path,
                    similarity=sim,
                    created_at=created,
                    hit_count=hits,
                )

        if best_match and best_similarity >= self.threshold:
            # Increment hit count
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE scene_cache SET hit_count = hit_count + 1 WHERE id = ?",
                    (best_match.cache_id,),
                )
                conn.commit()
            return best_match

        return None

    def store(
        self,
        description: str,
        manim_code: str,
        class_name: str,
        video_path: Optional[str] = None,
    ) -> int:
        """
        Store a generated scene in the cache.

        Args:
            description: Scene description text.
            manim_code: The generated Manim Python code.
            class_name: The Scene subclass name.
            video_path: Path to the rendered .mp4 file.

        Returns:
            The cache entry ID.
        """
        embedding = self.embedder.embed(description)
        emb_blob = embedding.astype(np.float32).tobytes()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO scene_cache "
                "(description, manim_code, class_name, video_path, embedding, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (description, manim_code, class_name, video_path, emb_blob, time.time()),
            )
            conn.commit()
            return cursor.lastrowid

    def get_stats(self) -> dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM scene_cache").fetchone()[0]
            total_hits = conn.execute("SELECT SUM(hit_count) FROM scene_cache").fetchone()[0] or 0
        return {
            "total_entries": total,
            "total_hits": total_hits,
            "db_path": str(self.db_path),
        }

    def clear(self):
        """Clear all cached entries."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM scene_cache")
            conn.commit()
