"""
pipeline.py

Framework-agnostic core of the app. Deliberately has ZERO PyQt5 imports so it
can be unit-tested or reused from a CLI/Streamlit/PyQt5 front-end alike.

Turns an educational transcript (.txt) into:
  1. A summary of the transcript.
  2. A Manim scene (rendered to .mp4) that visually explains it.
  3. A complete, runnable Streamlit app that teaches the same content
     interactively (explanations, matplotlib diagrams, quiz with Verify button).

Both generation steps call an Ollama-compatible chat endpoint
(POST {host}/api/chat). If an api_key is supplied, it is sent as
`Authorization: Bearer <api_key>` — useful if you're hitting Ollama through a
reverse proxy / hosted endpoint that requires auth. Local `ollama serve`
usually needs no key at all, in which case just leave it empty.

Requirements (pip):
    pip install requests

Requirements (system):
    - Ollama running locally (or reachable at `ollama_host`) with a model pulled:
        ollama pull llama3.1:70b
    - ffmpeg installed and on PATH (required by Manim)
    - `pip install manim` and the `manim` CLI available on PATH
    - (optional) a LaTeX distribution, only if generated scenes use MathTex
"""

from __future__ import annotations

import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests


# --------------------------------------------------------------------------- #
# Ollama client
# --------------------------------------------------------------------------- #

class OllamaClient:
    """Thin wrapper around an Ollama-compatible /api/chat endpoint."""

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        api_key: Optional[str] = None,
        timeout: int = 600,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.api_key = api_key or None
        self.timeout = timeout

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        """Call /api/chat with a system + user message, non-streaming, return text."""
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host} (model '{self.model}'). "
                f"Is `ollama serve` running and is the model pulled? "
                f"Original error: {exc}"
            ) from exc

        data = resp.json()
        content = (data.get("message") or {}).get("content", "")
        if not content:
            raise RuntimeError(f"Ollama returned an empty response: {data}")
        return content


def _extract_code_block(text: str) -> str:
    """
    Models often wrap code in ```python ... ``` fences, or add prose before/after.
    Pull out the largest fenced code block; fall back to the raw text if none found.
    """
    pattern = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
    matches = pattern.findall(text)
    if matches:
        return max(matches, key=len).strip()
    return text.strip()


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #

@dataclass
class PipelineResult:
    transcript_path: str
    summary: str = ""
    manim_code: str = ""
    manim_video_path: Optional[str] = None
    streamlit_code: str = ""
    errors: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #

class TranscriptEduPipeline:

    SUMMARY_SYSTEM_PROMPT = (
        "You are an expert note-taker. Summarize the given lecture transcript into "
        "a dense, well-organized study summary covering every key concept, "
        "definition, and example, in under 600 words. Output plain text only, "
        "no markdown headers."
    )

    MANIM_SYSTEM_PROMPT = textwrap.dedent("""
        You are an expert Manim (Community Edition) developer and educator.
        Your job is to convert an educational transcript summary into a single,
        complete, runnable Manim Scene that visually explains the material.

        Rules:
        1. Identify the subject and the 3-6 most important concepts to visualize.
        2. Plan a short sequence of animations that build understanding step by
           step (e.g. write a title, show a diagram, transform it, highlight key
           parts, show short on-screen text summarizing each idea).
        3. Use only the `manim` Community Edition API (`from manim import *`).
        4. Define exactly ONE Scene subclass named `GeneratedScene` with a
           `construct(self)` method.
        5. Prefer Text() over Tex()/MathTex() unless real mathematical notation
           is required, to avoid requiring a LaTeX installation.
        6. Keep total runtime reasonable (roughly 45-90 seconds of animation).
        7. Do not leave TODO comments or placeholders.
        8. Output ONLY a single Python code block. No prose before or after it.
    """).strip()

    STREAMLIT_SYSTEM_PROMPT = textwrap.dedent("""
        You are an expert educational software engineer.
        Your job is to convert summarized educational transcripts into complete
        interactive Streamlit applications.
        Always think before coding.
        Rules:
          1. Identify the subject.
          2. Identify important concepts.
          3. Decide what interactive widgets should be created.
          4. Produce a beautiful Streamlit webpage.
          5. Add explanations.
          6. Add diagrams using matplotlib if needed.
          7. Add animations whenever appropriate.
          8. Add quiz questions with a Verify button.
          9. The code must be complete and runnable.
          10. Do not leave TODO comments.
          11. Generate production-quality Python code.

        Output ONLY a single Python code block. No prose before or after it.
    """).strip()

    def __init__(
        self,
        model: str = "llama3.1:70b",
        ollama_host: str = "http://localhost:11434",
        api_key: Optional[str] = None,
    ):
        self.client = OllamaClient(model=model, host=ollama_host, api_key=api_key)

    # ---------------- Step 1: read ----------------
    def read_transcript(self, path: str) -> str:
        text = Path(path).read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            raise ValueError(f"Transcript file '{path}' is empty.")
        return text

    # ---------------- Step 1b: summarize ----------------
    def summarize_transcript(self, transcript: str) -> str:
        """Chunks + summarizes very long transcripts in two passes so prompts
        stay small regardless of source length."""
        if len(transcript) < 6000:
            return self.client.generate(self.SUMMARY_SYSTEM_PROMPT, transcript)

        chunks = [transcript[i : i + 6000] for i in range(0, len(transcript), 6000)]
        partial_summaries = [self.client.generate(self.SUMMARY_SYSTEM_PROMPT, c) for c in chunks]
        combined = "\n\n".join(partial_summaries)
        return self.client.generate(self.SUMMARY_SYSTEM_PROMPT, combined)

    # ---------------- Step 2: Manim ----------------
    def generate_manim_code(self, summary: str) -> str:
        raw = self.client.generate(self.MANIM_SYSTEM_PROMPT, summary)
        return _extract_code_block(raw)

    def render_manim_video(self, manim_code: str, output_dir: str, quality: str = "m") -> str:
        """
        Writes the scene to disk and renders it with the `manim` CLI.
        quality: 'l' (480p, fast), 'm' (720p), 'h' (1080p)
        Returns the path to the rendered .mp4, or raises RuntimeError on failure.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        scene_file = out_dir / "generated_scene.py"
        scene_file.write_text(manim_code, encoding="utf-8")

        media_dir = out_dir / "media"
        cmd = [
            "manim",
            f"-q{quality}",
            "--media_dir", str(media_dir),
            str(scene_file),
            "GeneratedScene",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise RuntimeError(
                "Manim render failed.\n--- stdout ---\n" + proc.stdout +
                "\n--- stderr ---\n" + proc.stderr
            )

        candidates = list(media_dir.rglob("GeneratedScene.mp4"))
        if not candidates:
            raise RuntimeError("Manim reported success but no output .mp4 was found.")
        return str(candidates[0])

    # ---------------- Step 3: Streamlit ----------------
    def generate_streamlit_code(self, summary: str) -> str:
        raw = self.client.generate(self.STREAMLIT_SYSTEM_PROMPT, summary)
        return _extract_code_block(raw)

    # ---------------- Full orchestration ----------------
    def run(self, transcript_path: str, output_dir: str = "output", render_video: bool = True,
             quality: str = "m") -> PipelineResult:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = PipelineResult(transcript_path=transcript_path)

        transcript = self.read_transcript(transcript_path)
        result.summary = self.summarize_transcript(transcript)
        (out_dir / "summary.txt").write_text(result.summary, encoding="utf-8")

        result.manim_code = self.generate_manim_code(result.summary)
        (out_dir / "generated_scene.py").write_text(result.manim_code, encoding="utf-8")

        if render_video:
            try:
                result.manim_video_path = self.render_manim_video(result.manim_code, str(out_dir), quality=quality)
            except Exception as exc:
                result.errors.append(f"Manim render failed: {exc}")

        result.streamlit_code = self.generate_streamlit_code(result.summary)
        (out_dir / "generated_app.py").write_text(result.streamlit_code, encoding="utf-8")

        return result
