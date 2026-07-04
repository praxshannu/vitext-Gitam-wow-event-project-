"""
Orchestrator — the main pipeline coordinator for Vitext.

Implements the full execution graph:

    User Input → Script Agent → [Cache Check → Code Agent → Render → Critic] × N → Assembly

Key features:
- Concurrent processing: scenes without dependencies are dispatched in parallel
- Retry loop: Critic feedback → Code Agent revision, up to max_critic_retries
- Cache integration: skips Code + Render for previously generated concepts
- Progress callbacks: report status to the UI layer

This module uses asyncio for concurrency. No LangGraph dependency —
just plain async Python with a clean state machine.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from vitext.config import PipelineConfig, default_config
from vitext.agents.script_agent import ScriptAgent, ScriptOutput, SceneChunk
from vitext.agents.code_agent import CodeAgent, GeneratedCode
from vitext.agents.critic_agent import CriticAgent, CriticVerdict
from vitext.agents.assembly_agent import AssemblyAgent, AssemblyResult
from vitext.renderer.manim_runner import ManimRunner, RenderResult
from vitext.cache.scene_cache import SceneCache


logger = logging.getLogger("vitext.orchestrator")


# ── Pipeline state ────────────────────────────────────────────────────

@dataclass
class SceneState:
    """Tracks the processing state of a single scene."""
    scene: SceneChunk
    status: str = "pending"          # pending, cached, coding, rendering, critiquing, passed, failed
    code: Optional[GeneratedCode] = None
    render_result: Optional[RenderResult] = None
    verdict: Optional[CriticVerdict] = None
    retry_count: int = 0
    error_message: str = ""
    cached: bool = False
    video_path: Optional[Path] = None


@dataclass
class PipelineState:
    """Overall pipeline state."""
    transcript: str
    status: str = "initializing"     # initializing, scripting, processing, assembling, done, failed
    script_output: Optional[ScriptOutput] = None
    scene_states: dict[str, SceneState] = field(default_factory=dict)
    final_result: Optional[AssemblyResult] = None
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    @property
    def progress_pct(self) -> float:
        if not self.scene_states:
            return 0.0
        done = sum(1 for s in self.scene_states.values() if s.status in ("passed", "failed", "cached"))
        return done / len(self.scene_states) * 100


# ── Progress callback type ────────────────────────────────────────────

ProgressCallback = Optional[Callable[[str, str, float], None]]
# Signature: (stage: str, message: str, progress_pct: float) -> None


# ── Orchestrator ──────────────────────────────────────────────────────

class PipelineOrchestrator:
    """
    Main pipeline coordinator — runs the full transcript → video flow.

    Usage:
        config = PipelineConfig()
        orchestrator = PipelineOrchestrator(config)

        result = await orchestrator.run(
            transcript="Today we'll explore the chain rule...",
            output_filename="chain_rule.mp4",
            on_progress=lambda stage, msg, pct: print(f"[{pct:.0f}%] {stage}: {msg}"),
        )

        if result.final_result and result.final_result.success:
            print(f"Video saved to: {result.final_result.output_path}")
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self.config.ensure_directories()

        # Initialize agents
        self.script_agent = ScriptAgent(self.config)
        self.code_agent = CodeAgent(self.config)
        self.critic_agent = CriticAgent(self.config)
        self.assembly_agent = AssemblyAgent(self.config)
        self.renderer = ManimRunner(self.config)

        # Cache (lazy-init to avoid requiring sentence-transformers for non-cached runs)
        self._cache: Optional[SceneCache] = None

    def _get_cache(self) -> Optional[SceneCache]:
        """Lazy-initialize the scene cache."""
        if self._cache is None:
            try:
                self._cache = SceneCache(self.config)
            except Exception as e:
                logger.warning(f"Cache initialization failed (will proceed without caching): {e}")
                self._cache = None
        return self._cache

    async def run(
        self,
        transcript: str,
        output_filename: str = "output.mp4",
        on_progress: ProgressCallback = None,
    ) -> PipelineState:
        """
        Execute the full pipeline.

        Args:
            transcript: Raw lecture transcript or topic description.
            output_filename: Name for the final output video.
            on_progress: Optional callback for progress updates.

        Returns:
            PipelineState with the complete execution history and result.
        """
        state = PipelineState(transcript=transcript, start_time=time.time())

        def report(stage: str, message: str):
            pct = state.progress_pct
            logger.info(f"[{pct:.0f}%] {stage}: {message}")
            if on_progress:
                on_progress(stage, message, pct)

        try:
            # ── Stage 1: Script Agent ─────────────────────────────
            state.status = "scripting"
            report("Script Agent", "Breaking transcript into scene chunks...")

            state.script_output = await self.script_agent.generate(transcript)
            report(
                "Script Agent",
                f"Generated {len(state.script_output.scenes)} scenes "
                f"(~{state.script_output.total_duration_seconds}s total)",
            )

            # Initialize scene states
            for scene in state.script_output.scenes:
                state.scene_states[scene.scene_id] = SceneState(scene=scene)

            # ── Stage 2: Process scenes concurrently ──────────────
            state.status = "processing"
            report("Processing", "Starting concurrent scene processing...")

            # Build dependency graph
            independent_scenes = []
            dependent_scenes = []
            for scene in state.script_output.scenes:
                if not scene.depends_on:
                    independent_scenes.append(scene)
                else:
                    dependent_scenes.append(scene)

            # Process independent scenes concurrently
            semaphore = asyncio.Semaphore(self.config.max_concurrent_scenes)

            async def process_with_semaphore(scene: SceneChunk):
                async with semaphore:
                    await self._process_single_scene(scene, state, report)

            if independent_scenes:
                await asyncio.gather(
                    *[process_with_semaphore(s) for s in independent_scenes]
                )

            # Process dependent scenes (in order, after their dependencies)
            for scene in dependent_scenes:
                # Wait for dependencies
                for dep_id in scene.depends_on:
                    dep_state = state.scene_states.get(dep_id)
                    if dep_state and dep_state.status not in ("passed", "cached"):
                        report(
                            "Processing",
                            f"Scene {scene.scene_id} waiting for dependency {dep_id}",
                        )
                await self._process_single_scene(scene, state, report)

            # ── Stage 3: Assembly ─────────────────────────────────
            state.status = "assembling"
            report("Assembly", "Stitching scenes together...")

            # Collect video paths in order
            scene_videos = {}
            scene_order = []
            for scene in state.script_output.scenes:
                ss = state.scene_states[scene.scene_id]
                if ss.video_path and ss.video_path.exists():
                    scene_videos[scene.scene_id] = ss.video_path
                    scene_order.append(scene.scene_id)

            if not scene_videos:
                state.status = "failed"
                report("Assembly", "No scene videos available for assembly!")
                state.end_time = time.time()
                return state

            state.final_result = await self.assembly_agent.assemble(
                scene_videos=scene_videos,
                scene_order=scene_order,
                output_filename=output_filename,
            )

            if state.final_result.success:
                state.status = "done"
                report(
                    "Done",
                    f"Video saved to {state.final_result.output_path} "
                    f"({state.final_result.total_duration:.1f}s, "
                    f"{state.final_result.scene_count} scenes)",
                )
            else:
                state.status = "failed"
                report("Assembly", f"Assembly failed: {state.final_result.error_message}")

        except Exception as e:
            state.status = "failed"
            report("Error", f"Pipeline failed: {e}")
            logger.exception("Pipeline failed")

        state.end_time = time.time()
        return state

    async def _process_single_scene(
        self,
        scene: SceneChunk,
        state: PipelineState,
        report: Callable,
    ):
        """
        Process a single scene through: cache check → code gen → render → critique.

        Includes the retry loop for critic feedback.
        """
        ss = state.scene_states[scene.scene_id]

        # ── Cache check ───────────────────────────────────────
        cache = self._get_cache()
        if cache:
            try:
                hit = cache.lookup(scene.description)
                if hit and hit.video_path and Path(hit.video_path).exists():
                    ss.status = "cached"
                    ss.cached = True
                    ss.video_path = Path(hit.video_path)
                    report("Cache", f"Cache HIT for {scene.scene_id} (similarity: {hit.similarity:.3f})")
                    return
            except Exception as e:
                logger.warning(f"Cache lookup failed for {scene.scene_id}: {e}")

        # ── Code → Render → Critique loop ─────────────────────
        critic_feedback = None

        for attempt in range(self.config.max_critic_retries + 1):
            # Code generation
            ss.status = "coding"
            report("Code Agent", f"Generating code for {scene.scene_id} (attempt {attempt + 1})")

            try:
                ss.code = await self.code_agent.generate(scene, critic_feedback=critic_feedback)
            except Exception as e:
                ss.status = "failed"
                ss.error_message = f"Code generation failed: {e}"
                report("Code Agent", ss.error_message)
                return

            if not ss.code.imports_valid:
                logger.warning(f"{scene.scene_id}: Generated code doesn't import from brand library")

            # Rendering
            ss.status = "rendering"
            report("Renderer", f"Rendering {scene.scene_id}...")

            try:
                ss.render_result = await self.renderer.render(
                    scene_id=scene.scene_id,
                    python_code=ss.code.python_code,
                    class_name=ss.code.class_name,
                )
            except Exception as e:
                ss.status = "failed"
                ss.error_message = f"Render failed: {e}"
                report("Renderer", ss.error_message)
                return

            if not ss.render_result.success:
                # Render error — feed back to Code Agent as critic feedback
                critic_feedback = (
                    f"RENDER ERROR:\n{ss.render_result.error_message}\n\n"
                    f"STDERR:\n{ss.render_result.stderr[-1000:]}"  # Last 1000 chars of stderr
                )
                ss.retry_count += 1
                report("Renderer", f"Render failed for {scene.scene_id}, retrying...")
                continue

            # Critique
            ss.status = "critiquing"
            report("Critic", f"Evaluating {scene.scene_id}...")

            if ss.render_result.frame_paths:
                try:
                    ss.verdict = await self.critic_agent.evaluate(
                        scene_chunk=scene,
                        frame_paths=ss.render_result.frame_paths,
                        retry_count=attempt,
                    )
                except Exception as e:
                    # If critic fails, accept the render as-is
                    logger.warning(f"Critic failed for {scene.scene_id}: {e}")
                    ss.status = "passed"
                    ss.video_path = ss.render_result.video_path
                    break

                if ss.verdict.passed:
                    ss.status = "passed"
                    ss.video_path = ss.render_result.video_path
                    report(
                        "Critic",
                        f"{scene.scene_id} PASSED (score: {ss.verdict.overall_score:.2f})",
                    )
                    break
                else:
                    critic_feedback = ss.verdict.get_feedback_for_code_agent()
                    ss.retry_count += 1
                    report(
                        "Critic",
                        f"{scene.scene_id} FAILED (score: {ss.verdict.overall_score:.2f}), "
                        f"retrying ({attempt + 1}/{self.config.max_critic_retries + 1})...",
                    )
            else:
                # No frames extracted — accept the render
                ss.status = "passed"
                ss.video_path = ss.render_result.video_path
                break

        # If we exhausted retries, accept the last render anyway
        if ss.status not in ("passed", "cached"):
            if ss.render_result and ss.render_result.video_path:
                ss.status = "passed"
                ss.video_path = ss.render_result.video_path
                report(
                    "Critic",
                    f"{scene.scene_id} accepted after {ss.retry_count} retries "
                    f"(best effort)",
                )
            else:
                ss.status = "failed"
                ss.error_message = f"Failed after {ss.retry_count} retries"
                report("Failed", f"{scene.scene_id}: {ss.error_message}")

        # ── Cache the result ──────────────────────────────────
        if ss.status == "passed" and ss.code and cache:
            try:
                cache.store(
                    description=scene.description,
                    manim_code=ss.code.python_code,
                    class_name=ss.code.class_name,
                    video_path=str(ss.video_path) if ss.video_path else None,
                )
            except Exception as e:
                logger.warning(f"Failed to cache {scene.scene_id}: {e}")

    def run_sync(self, transcript: str, **kwargs) -> PipelineState:
        """Synchronous wrapper for the full pipeline."""
        return asyncio.run(self.run(transcript, **kwargs))
