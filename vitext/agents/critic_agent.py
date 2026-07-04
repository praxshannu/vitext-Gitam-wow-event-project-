"""
Critic Agent — vision-based quality assurance for rendered Manim scenes.

After the Manim renderer produces a .mp4 for a scene, the Critic Agent:
1. Extracts keyframes (final frame + optional 25%/50%/75% frames)
2. Sends the frame images + scene description to a vision model (Gemini)
3. Evaluates against an aesthetic/correctness checklist
4. Returns a structured pass/fail verdict with actionable feedback

If the scene fails, the feedback is routed back to the Code Agent for revision.
Max retries are controlled by PipelineConfig.max_critic_retries.
"""

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import google.generativeai as genai

from vitext.config import PipelineConfig, default_config
from vitext.agents.script_agent import SceneChunk


# ── Verdict model ─────────────────────────────────────────────────────

@dataclass
class CriticIssue:
    """A single visual issue found by the Critic."""
    issue_type: str          # "overlap", "contrast", "overflow", "spacing", "timing", "other"
    description: str         # What's wrong
    suggestion: str          # Specific fix instruction for the Code Agent
    severity: str = "medium" # "low", "medium", "high"

    def to_dict(self) -> dict:
        return {
            "issue_type": self.issue_type,
            "description": self.description,
            "suggestion": self.suggestion,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CriticIssue":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CriticVerdict:
    """Complete evaluation result from the Critic Agent."""
    scene_id: str
    passed: bool
    overall_score: float           # 0.0 to 1.0
    issues: list[CriticIssue] = field(default_factory=list)
    positive_notes: list[str] = field(default_factory=list)
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "passed": self.passed,
            "overall_score": self.overall_score,
            "issues": [i.to_dict() for i in self.issues],
            "positive_notes": self.positive_notes,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CriticVerdict":
        issues = [CriticIssue.from_dict(i) for i in d.get("issues", [])]
        return cls(
            scene_id=d["scene_id"],
            passed=d["passed"],
            overall_score=d.get("overall_score", 0.0),
            issues=issues,
            positive_notes=d.get("positive_notes", []),
            retry_count=d.get("retry_count", 0),
        )

    def get_feedback_for_code_agent(self) -> str:
        """Format issues as feedback text for the Code Agent."""
        if self.passed:
            return ""
        lines = ["The Visual Critic found the following issues:\n"]
        for i, issue in enumerate(self.issues, 1):
            lines.append(f"{i}. [{issue.severity.upper()}] {issue.issue_type}: {issue.description}")
            lines.append(f"   → Fix: {issue.suggestion}")
            lines.append("")
        return "\n".join(lines)


# ── System prompt ─────────────────────────────────────────────────────

CRITIC_SYSTEM_PROMPT = """\
You are the **Visual Critic Agent** in the Vitext video pipeline.

You receive:
1. One or more keyframe images from a rendered Manim animation
2. The scene description that was used to generate the animation

Your job: evaluate the visual quality and correctness of the rendered scene.

## Evaluation checklist

Score each criterion 0–10 and provide feedback:

1. **Text Legibility** — Can all text be read clearly? No truncation or overflow?
2. **Element Overlap** — Do any visual elements overlap in ways that obscure content?
3. **Color Contrast** — Is text readable against its background? Are colors distinguishable?
4. **Spacing & Balance** — Is the layout well-balanced? Adequate margins and padding?
5. **Content Accuracy** — Does the visual match the scene description? Are formulas correct?
6. **Animation Readability** — Are elements visible long enough to be read/understood?

## Output format (strict)

Output raw JSON only — no markdown fences, no preamble.

```json
{
  "passed": true/false,
  "overall_score": 0.85,
  "issues": [
    {
      "issue_type": "overlap | contrast | overflow | spacing | timing | accuracy | other",
      "description": "The integral symbol overlaps with the y-axis label",
      "suggestion": "Move the formula RIGHT by 1.5 units using .shift(RIGHT * 1.5)",
      "severity": "high | medium | low"
    }
  ],
  "positive_notes": [
    "Good use of color for the highlighted equation",
    "Title card is well-centered"
  ]
}
```

## Pass/Fail criteria

- **PASS** (`passed: true`): overall_score >= 0.7 AND no "high" severity issues
- **FAIL** (`passed: false`): overall_score < 0.7 OR any "high" severity issue

## Suggestion format

Suggestions MUST be specific, actionable Manim code hints:
- ✅ "Move the formula RIGHT by 1.5 units using `.shift(RIGHT * 1.5)`"
- ✅ "Scale the body text to 0.7 using `.scale(0.7)` to prevent overflow"
- ✅ "Add `.next_to(axes, UP, buff=0.5)` to separate the title from the graph"
- ❌ "The text is hard to read" (too vague)
- ❌ "Fix the overlap" (no specific instruction)
"""


# ── Agent implementation ──────────────────────────────────────────────

class CriticAgent:
    """
    Evaluates rendered Manim scenes for visual quality.

    Usage:
        critic = CriticAgent(config)
        verdict = await critic.evaluate(
            scene_chunk=scene,
            frame_paths=[Path("frame_final.png")],
        )
        if not verdict.passed:
            feedback = verdict.get_feedback_for_code_agent()
            # Send feedback to Code Agent for revision
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self._configure_api()

    def _configure_api(self):
        """Set up the Gemini client (needs vision capability)."""
        api_key = self.config.agents.google_api_key
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY not set. Set it in the environment or in PipelineConfig."
            )
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=self.config.agents.critic_model,
            system_instruction=CRITIC_SYSTEM_PROMPT,
        )

    def _load_image(self, path: Path) -> dict:
        """Load an image file as a Gemini-compatible part."""
        data = path.read_bytes()
        # Determine MIME type
        suffix = path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        mime = mime_map.get(suffix, "image/png")
        return {
            "mime_type": mime,
            "data": data,
        }

    async def evaluate(
        self,
        scene_chunk: SceneChunk,
        frame_paths: list[Path],
        retry_count: int = 0,
    ) -> CriticVerdict:
        """
        Evaluate a rendered scene's visual quality.

        Args:
            scene_chunk: The original scene description.
            frame_paths: Paths to keyframe PNG images extracted from the render.
            retry_count: Current retry iteration (0 = first attempt).

        Returns:
            CriticVerdict with pass/fail and actionable feedback.
        """
        # Build multi-modal content: images + text
        content_parts = []

        for frame_path in frame_paths:
            if frame_path.exists():
                img_data = self._load_image(frame_path)
                content_parts.append(img_data)

        # Add the scene description as context
        text_context = f"""Evaluate the rendered scene shown in the image(s) above.

**Scene Description:** {scene_chunk.description}
**Expected Visual Elements:** {', '.join(scene_chunk.visual_elements)}
**Target Duration:** {scene_chunk.duration_seconds} seconds
**Retry Count:** {retry_count} ({"first attempt" if retry_count == 0 else f"retry #{retry_count}"})

Analyze the image(s) and provide your evaluation JSON.
"""
        content_parts.append(text_context)

        response = await self.model.generate_content_async(
            content_parts,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.3,
                max_output_tokens=2048,
            ),
        )

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        data = json.loads(raw_text)

        # Build verdict
        issues = [CriticIssue.from_dict(i) for i in data.get("issues", [])]

        verdict = CriticVerdict(
            scene_id=scene_chunk.scene_id,
            passed=data.get("passed", False),
            overall_score=data.get("overall_score", 0.0),
            issues=issues,
            positive_notes=data.get("positive_notes", []),
            retry_count=retry_count,
        )

        return verdict

    def evaluate_sync(
        self,
        scene_chunk: SceneChunk,
        frame_paths: list[Path],
        retry_count: int = 0,
    ) -> CriticVerdict:
        """Synchronous wrapper."""
        import asyncio
        return asyncio.run(self.evaluate(scene_chunk, frame_paths, retry_count))
