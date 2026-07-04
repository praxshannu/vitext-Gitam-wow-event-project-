"""
Vitext — Chunked, Multi-Modal, Parallelized Manim Video Pipeline
=================================================================

Transforms lecture transcripts into polished Manim-animated math/science
videos through a multi-agent architecture:

    Script Agent  →  Code Agent(s)  →  Renderer  →  Critic  →  Assembly

Key design principles:
    1. Scene chunking: every video is broken into atomic, independent scenes
    2. Brand library: code agents use pre-built wrappers, never raw Manim
    3. Visual critic: a vision model reviews rendered frames for quality
    4. Caching: previously rendered concepts are reused via semantic search
"""

__version__ = "0.1.0"
