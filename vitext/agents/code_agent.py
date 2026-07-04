"""
Code Agent — generates Manim Python code for a single scene chunk.

Receives a SceneChunk (from the Script Agent) and produces valid Python code
that uses ONLY the Vitext Brand Library. The generated code defines exactly
one Manim Scene subclass (of BrandScene) with a construct() method.

The Code Agent never sees raw Manim docs — it works exclusively from the
Brand Library's api_reference.md, which is injected into its system prompt.
This constraint is what prevents style drift.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import google.generativeai as genai

from vitext.config import PipelineConfig, default_config
from vitext.agents.script_agent import SceneChunk


# ── Output model ──────────────────────────────────────────────────────

@dataclass
class GeneratedCode:
    """Output from the Code Agent for one scene."""
    scene_id: str
    class_name: str          # e.g. "Scene01Intro"
    python_code: str         # Complete, runnable Python file
    imports_valid: bool      # Self-check: does it only use brand library?
    estimated_duration: int  # Seconds


# ── Load the API reference doc ────────────────────────────────────────

_API_REF_PATH = Path(__file__).parent.parent / "brand_library" / "api_reference.md"


def _load_api_reference() -> str:
    """Load the brand library API reference for injection into the prompt."""
    if _API_REF_PATH.exists():
        return _API_REF_PATH.read_text(encoding="utf-8")
    return "(API reference not found — use brand library classes as documented.)"


# ── System prompt ─────────────────────────────────────────────────────

CODE_AGENT_SYSTEM_PROMPT_TEMPLATE = """\
You are the **Code Agent** in the Vitext video generation pipeline.

Your job: receive a scene description and generate **valid, runnable Manim Python code**
that renders that scene using the Vitext Brand Library.

## Brand Library API Reference

{api_reference}

## Output format (strict)

Output ONLY the Python code. No markdown fences, no preamble, no commentary.
The code must:

1. Start with `from vitext.brand_library import *`
2. Import `numpy as np` if math functions are needed
3. Define exactly ONE class that subclasses `BrandScene`
4. The class name must be `{class_name}`
5. Implement a `construct(self)` method
6. Use `self.play(...)` for animations and `self.wait(...)` for pauses
7. Use ONLY Brand Library classes — never raw `Text()`, `MathTex()`, or `Scene()`
8. Use ONLY named brand colors — never raw hex codes
9. Keep total animation under {duration} seconds
10. End with `self.wait(1)` to hold the final frame

## Common patterns

### Title card
```python
from vitext.brand_library import *

class {class_name}(BrandScene):
    def construct(self):
        intro = BrandTitleCard("Topic Name", "Subtitle here")
        self.play(FadeIn(intro, shift=UP * 0.3))
        self.wait(2)
        self.play(FadeOut(intro))
```

### Formula + annotation
```python
from vitext.brand_library import *

class {class_name}(BrandScene):
    def construct(self):
        formula = BrandFormula(r"E = mc^2")
        self.play(Write(formula))
        self.wait(1)
        box = BrandHighlightBox(formula, label="Einstein's famous equation")
        self.play(Create(box))
        self.wait(2)
```

### Graph
```python
from vitext.brand_library import *
import numpy as np

class {class_name}(BrandScene):
    def construct(self):
        axes = BrandAxes(x_range=[-3, 3, 1], y_range=[-2, 2, 1])
        graph = axes.get_function_graph(lambda x: np.sin(x), color_index=0)
        self.play(Create(axes), run_time=1.5)
        self.play(Create(graph), run_time=2)
        self.wait(2)
```

## Handling Critic feedback

If you receive feedback from the Visual Critic (e.g., "text overlaps with graph"),
apply the specific spatial corrections mentioned. Common fixes:
- `.shift(UP * 0.5)` — move elements up
- `.shift(RIGHT * 1)` — move elements right
- `.scale(0.8)` — shrink an element
- `.next_to(other, DOWN, buff=0.5)` — position relative to another element
- Add `self.wait(0.5)` between rapid animations so elements are visible longer
"""


# ── Agent implementation ──────────────────────────────────────────────

class CodeAgent:
    """
    Generates Manim code for a single scene chunk.

    Usage:
        agent = CodeAgent(config)
        result = await agent.generate(scene_chunk)
        print(result.python_code)
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self._api_reference = _load_api_reference()
        self._configure_api()

    def _configure_api(self):
        """Set up the Gemini client."""
        api_key = self.config.agents.google_api_key
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY not set. Set it in the environment or in PipelineConfig."
            )
        genai.configure(api_key=api_key)

    def _make_class_name(self, scene_id: str) -> str:
        """Convert scene_id to a valid Python class name."""
        # "scene_01_intro" -> "Scene01Intro"
        parts = scene_id.split("_")
        return "".join(p.capitalize() for p in parts)

    def _build_system_prompt(self, class_name: str, duration: int) -> str:
        """Build the full system prompt with API reference injected."""
        return CODE_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
            api_reference=self._api_reference,
            class_name=class_name,
            duration=duration,
        )

    async def generate(
        self,
        scene: SceneChunk,
        critic_feedback: Optional[str] = None,
    ) -> GeneratedCode:
        """
        Generate Manim code for a scene.

        Args:
            scene: The scene description from the Script Agent.
            critic_feedback: Optional feedback from a previous Critic evaluation
                             (for retry iterations).

        Returns:
            GeneratedCode with the Python source and metadata.
        """
        class_name = self._make_class_name(scene.scene_id)

        system_prompt = self._build_system_prompt(class_name, scene.duration_seconds)

        # Build the user message
        user_message = f"""Generate Manim code for this scene:

**Scene ID:** {scene.scene_id}
**Title:** {scene.title}
**Description:** {scene.description}
**Narration:** {scene.narration}
**Duration:** {scene.duration_seconds} seconds
**Visual Elements:** {', '.join(scene.visual_elements)}
**Manim Hints:** {scene.manim_hints or 'None'}
"""

        if critic_feedback:
            user_message += f"""

## ⚠️ CRITIC FEEDBACK (you MUST address these issues):

{critic_feedback}

Fix ALL the issues listed above. Apply the specific spatial corrections mentioned.
"""

        model = genai.GenerativeModel(
            model_name=self.config.agents.code_model,
            system_instruction=system_prompt,
        )

        response = await model.generate_content_async(
            user_message,
            generation_config=genai.GenerationConfig(
                temperature=0.2,        # Very low temp for code gen
                max_output_tokens=4096,
            ),
        )

        code = response.text.strip()
        # Strip markdown fences if present
        if code.startswith("```"):
            lines = code.split("\n")
            # Remove first and last fence lines
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)

        # Basic validation: check it imports from brand library
        imports_valid = "from vitext.brand_library import" in code

        return GeneratedCode(
            scene_id=scene.scene_id,
            class_name=class_name,
            python_code=code,
            imports_valid=imports_valid,
            estimated_duration=scene.duration_seconds,
        )

    async def generate_with_retry(
        self,
        scene: SceneChunk,
        max_retries: int = 2,
    ) -> GeneratedCode:
        """
        Generate code with automatic retries on syntax errors.

        Tries to compile the generated code. If there's a SyntaxError,
        feeds the error back and retries.
        """
        last_error = None
        for attempt in range(max_retries + 1):
            feedback = None
            if last_error:
                feedback = f"SYNTAX ERROR in previous attempt:\n{last_error}\nFix the syntax error."

            result = await self.generate(scene, critic_feedback=feedback)

            # Try to compile
            try:
                compile(result.python_code, f"{scene.scene_id}.py", "exec")
                return result
            except SyntaxError as e:
                last_error = f"Line {e.lineno}: {e.msg}"
                if attempt == max_retries:
                    # Return even with syntax error on final attempt
                    return result

        return result  # Should never reach here

    def generate_sync(self, scene: SceneChunk, critic_feedback: Optional[str] = None) -> GeneratedCode:
        """Synchronous wrapper."""
        import asyncio
        return asyncio.run(self.generate(scene, critic_feedback))
