"""
Central configuration for the Vitext pipeline.

All tuneable knobs — resolution, model names, paths, retry limits — live
here so agents and modules import from one place.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RenderConfig:
    """Manim rendering settings."""
    quality: str = "low"                     # "low" (480p), "medium" (720p), "high" (1080p)
    fps: int = 30
    background_color: str = "#1A1A2E"        # Must match brand palette
    pixel_width: int = 1280
    pixel_height: int = 720

    @property
    def manim_quality_flag(self) -> str:
        return {"low": "-ql", "medium": "-qm", "high": "-qh"}.get(self.quality, "-ql")


@dataclass
class AgentConfig:
    """LLM model selection for each agent role."""
    script_model: str = "gemini-2.5-flash"
    code_model: str = "gemini-2.5-flash"
    critic_model: str = "gemini-2.5-flash"   # Needs vision capability

    # API keys — read from env by default
    google_api_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))


@dataclass
class PipelineConfig:
    """Top-level pipeline configuration."""
    render: RenderConfig = field(default_factory=RenderConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)

    # Retry / concurrency
    max_critic_retries: int = 3
    max_concurrent_scenes: int = 4

    # Paths
    workspace_dir: Path = field(default_factory=lambda: Path.cwd() / ".vitext_workspace")
    cache_db_path: Path = field(default_factory=lambda: Path.cwd() / ".vitext_workspace" / "cache.db")
    output_dir: Path = field(default_factory=lambda: Path.cwd() / "vitext_output")

    # Cache
    cache_similarity_threshold: float = 0.92   # Cosine similarity threshold for cache hits
    embedding_model: str = "all-MiniLM-L6-v2"  # sentence-transformers model

    # Assembly
    transition_type: str = "crossfade"          # "cut", "crossfade", "dissolve"
    transition_duration: float = 0.5            # Seconds

    def ensure_directories(self):
        """Create workspace and output directories if they don't exist."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.workspace_dir / "scenes").mkdir(exist_ok=True)
        (self.workspace_dir / "renders").mkdir(exist_ok=True)
        (self.workspace_dir / "frames").mkdir(exist_ok=True)


# Singleton default config — importable anywhere
default_config = PipelineConfig()
