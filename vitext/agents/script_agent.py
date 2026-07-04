"""
Script Agent — transforms a transcript into a structured list of scene chunks.

This is the first agent in the pipeline. It receives the raw lecture transcript
(or user text) and outputs a JSON list of scene descriptions, each one an
atomic, self-contained unit of visual content that can be independently coded,
rendered, and critiqued.

The Script Agent does NOT generate any Manim code. Its output is purely
descriptive — what should appear, not how to draw it.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import google.generativeai as genai

from vitext.config import PipelineConfig, default_config


# ── Scene data model ──────────────────────────────────────────────────

@dataclass
class SceneChunk:
    """One atomic scene in the video."""
    scene_id: str                            # e.g. "scene_01_intro"
    title: str                               # Human-readable name
    description: str                         # What the scene should show
    narration: str                           # Voiceover / narration text
    duration_seconds: int                    # Target length
    visual_elements: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    manim_hints: str = ""                    # Optional hints about Manim approach

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "description": self.description,
            "narration": self.narration,
            "duration_seconds": self.duration_seconds,
            "visual_elements": self.visual_elements,
            "depends_on": self.depends_on,
            "manim_hints": self.manim_hints,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SceneChunk":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ScriptOutput:
    """Complete output from the Script Agent."""
    video_title: str
    total_duration_seconds: int
    scenes: list[SceneChunk]

    def to_dict(self) -> dict:
        return {
            "video_title": self.video_title,
            "total_duration_seconds": self.total_duration_seconds,
            "scenes": [s.to_dict() for s in self.scenes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScriptOutput":
        return cls(
            video_title=d["video_title"],
            total_duration_seconds=d.get("total_duration_seconds", 0),
            scenes=[SceneChunk.from_dict(s) for s in d["scenes"]],
        )


# ── System prompt ─────────────────────────────────────────────────────

SCRIPT_AGENT_SYSTEM_PROMPT = """\
You are the **Script Agent** in the Vitext video generation pipeline.

Your job: read a lecture transcript or topic description and break it down
into **modular, atomic scene chunks** for a Manim-animated explainer video.

## Output format (strict)

Output raw JSON only — no markdown fences, no preamble, no commentary.

```json
{
  "video_title": "string",
  "total_duration_seconds": number,
  "scenes": [
    {
      "scene_id": "scene_01_intro",
      "title": "Introduction",
      "description": "Detailed description of what this scene should visually show. Be specific about layout, elements, animations.",
      "narration": "The narration text that would accompany this scene.",
      "duration_seconds": 15,
      "visual_elements": ["title_card", "subtitle", "fade_in"],
      "depends_on": [],
      "manim_hints": "Use BrandTitleCard for the intro. Fade in from below."
    }
  ]
}
```

## Rules

1. **Break into 3–8 scenes.** Each scene should be 10–30 seconds. Never exceed 30s per scene.

2. **Each scene is self-contained.** It should be renderable without knowledge of other scenes.
   Do NOT reference "the equation from the previous scene" — repeat the formula if needed.

3. **Scene 1 is always an intro title card.** Use `visual_elements: ["title_card"]`.

4. **The last scene is always a recap/summary.** Briefly restate key takeaways.

5. **`visual_elements` uses these tags** (one or more per scene):
   - `title_card` — intro/outro title
   - `formula` — LaTeX equation build-up
   - `formula_derivation` — step-by-step derivation
   - `graph_2d` — function plot
   - `graph_3d` — 3D surface/parametric
   - `diagram` — conceptual diagram with arrows/labels
   - `step_reveal` — numbered step-by-step reveal
   - `comparison` — side-by-side comparison
   - `highlight_annotation` — arrow annotations on existing elements
   - `code_snippet` — code block display
   - `data_table` — tabular data
   - `animation_transform` — morphing one expression into another

6. **`depends_on`** lists scene_ids that must logically precede this scene.
   Independent scenes (no dependency) can be processed in parallel.
   Most scenes should have `depends_on: []` unless they build on a specific prior result.

7. **`description` must be detailed enough** for a Code Agent to write Manim code without
   seeing the transcript. Include exact formulas, exact text to display, exact layout positions.

8. **`manim_hints`** — optional suggestions about which Brand Library components to use
   (e.g., "Use BrandAxes for the graph", "Use BrandStepReveal for the derivation").

9. **`narration`** — write the actual spoken narration for TTS. Keep it natural and conversational.
"""


# ── Agent implementation ──────────────────────────────────────────────

class ScriptAgent:
    """
    Generates a structured scene breakdown from a transcript.

    Usage:
        agent = ScriptAgent(config)
        result = await agent.generate(transcript_text)
        for scene in result.scenes:
            print(scene.scene_id, scene.title)
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self._configure_api()

    def _configure_api(self):
        """Set up the Gemini client."""
        api_key = self.config.agents.google_api_key
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY not set. Set it in the environment or in PipelineConfig."
            )
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=self.config.agents.script_model,
            system_instruction=SCRIPT_AGENT_SYSTEM_PROMPT,
        )

    async def generate(self, transcript: str) -> ScriptOutput:
        """
        Generate scene chunks from a transcript.

        Args:
            transcript: The raw lecture transcript or topic description.

        Returns:
            ScriptOutput with the video title and list of SceneChunks.
        """
        response = await self.model.generate_content_async(
            f"Transcript / topic:\n\n{transcript}",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.4,        # Low temp for structured output
                max_output_tokens=4096,
            ),
        )

        raw_text = response.text.strip()
        # Handle potential markdown fencing
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        data = json.loads(raw_text)
        result = ScriptOutput.from_dict(data)

        # Validate: ensure at least 2 scenes
        if len(result.scenes) < 2:
            raise ValueError(
                f"Script Agent produced only {len(result.scenes)} scene(s). "
                "Expected at least 2 (intro + content)."
            )

        # Calculate total duration if not set
        if result.total_duration_seconds == 0:
            result.total_duration_seconds = sum(s.duration_seconds for s in result.scenes)

        return result

    def generate_sync(self, transcript: str) -> ScriptOutput:
        """Synchronous wrapper for generate()."""
        import asyncio
        return asyncio.run(self.generate(transcript))
