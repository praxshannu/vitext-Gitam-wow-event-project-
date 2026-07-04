"""
Manim Runner — subprocess-based Manim rendering with frame extraction.

Handles:
- Writing generated code to temporary .py files
- Running `manim render` as a subprocess
- Capturing stdout/stderr for error detection
- Extracting keyframes from rendered .mp4 for the Critic Agent
- Cleaning up temporary files
"""

import asyncio
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from vitext.config import PipelineConfig, default_config


@dataclass
class RenderResult:
    """Result of a Manim render attempt."""
    scene_id: str
    success: bool
    video_path: Optional[Path] = None       # Path to rendered .mp4
    frame_paths: list[Path] = field(default_factory=list)  # Extracted keyframes
    error_message: str = ""
    stdout: str = ""
    stderr: str = ""
    render_time_seconds: float = 0.0


class ManimRunner:
    """
    Renders Manim scenes in a subprocess and extracts frames.

    Usage:
        runner = ManimRunner(config)
        result = await runner.render(scene_id, python_code, class_name)
        if result.success:
            print(f"Video at: {result.video_path}")
            print(f"Frames: {result.frame_paths}")
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self.config.ensure_directories()

    def _write_scene_file(self, scene_id: str, code: str) -> Path:
        """Write generated Python code to a .py file in the workspace."""
        scene_dir = self.config.workspace_dir / "scenes"
        scene_dir.mkdir(parents=True, exist_ok=True)
        file_path = scene_dir / f"{scene_id}.py"
        file_path.write_text(code, encoding="utf-8")
        return file_path

    async def render(
        self,
        scene_id: str,
        python_code: str,
        class_name: str,
    ) -> RenderResult:
        """
        Render a Manim scene.

        Args:
            scene_id: Unique identifier for this scene.
            python_code: Complete Python source code defining the scene.
            class_name: The Scene subclass name to render.

        Returns:
            RenderResult with paths to video and frames, or error info.
        """
        import time
        start_time = time.monotonic()

        # Write the code to a file
        scene_file = self._write_scene_file(scene_id, python_code)

        # Build the Manim command
        quality_flag = self.config.render.manim_quality_flag
        output_dir = self.config.workspace_dir / "renders"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "manim", "render",
            quality_flag,
            "--fps", str(self.config.render.fps),
            "--media_dir", str(output_dir),
            "--disable_caching",
            str(scene_file),
            class_name,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.config.workspace_dir),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=120,  # 2-minute timeout per scene
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

        except asyncio.TimeoutError:
            return RenderResult(
                scene_id=scene_id,
                success=False,
                error_message="Render timed out after 120 seconds.",
                render_time_seconds=time.monotonic() - start_time,
            )
        except FileNotFoundError:
            return RenderResult(
                scene_id=scene_id,
                success=False,
                error_message=(
                    "Manim executable not found. Install with: pip install manim"
                ),
                render_time_seconds=time.monotonic() - start_time,
            )

        elapsed = time.monotonic() - start_time

        if process.returncode != 0:
            return RenderResult(
                scene_id=scene_id,
                success=False,
                error_message=f"Manim exited with code {process.returncode}",
                stdout=stdout,
                stderr=stderr,
                render_time_seconds=elapsed,
            )

        # Find the output video
        video_path = self._find_rendered_video(output_dir, class_name)

        if not video_path:
            return RenderResult(
                scene_id=scene_id,
                success=False,
                error_message="Render completed but no .mp4 file found in output.",
                stdout=stdout,
                stderr=stderr,
                render_time_seconds=elapsed,
            )

        # Extract keyframes for the Critic
        frame_paths = await self._extract_keyframes(scene_id, video_path)

        return RenderResult(
            scene_id=scene_id,
            success=True,
            video_path=video_path,
            frame_paths=frame_paths,
            stdout=stdout,
            stderr=stderr,
            render_time_seconds=elapsed,
        )

    def _find_rendered_video(self, media_dir: Path, class_name: str) -> Optional[Path]:
        """Search the Manim media directory for the rendered .mp4."""
        # Manim outputs to: media_dir/videos/<filename>/<quality>/<ClassName>.mp4
        for mp4 in media_dir.rglob(f"{class_name}.mp4"):
            return mp4

        # Fallback: find any recently created .mp4
        mp4_files = sorted(media_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        return mp4_files[0] if mp4_files else None

    async def _extract_keyframes(self, scene_id: str, video_path: Path) -> list[Path]:
        """
        Extract keyframes from a rendered video using FFmpeg.

        Extracts: final frame + frames at 25%, 50%, 75% of duration.
        """
        frames_dir = self.config.workspace_dir / "frames" / scene_id
        frames_dir.mkdir(parents=True, exist_ok=True)

        frame_paths = []

        # Get video duration using ffprobe
        duration = await self._get_video_duration(video_path)
        if duration <= 0:
            # Fallback: just extract the last frame
            return await self._extract_single_frame(
                video_path, frames_dir, "final", seek_end=True
            )

        # Extract frames at key positions
        positions = {
            "frame_25pct": duration * 0.25,
            "frame_50pct": duration * 0.50,
            "frame_75pct": duration * 0.75,
            "frame_final": max(0, duration - 0.1),
        }

        for name, timestamp in positions.items():
            output_path = frames_dir / f"{name}.png"
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{timestamp:.2f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(output_path),
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                if output_path.exists():
                    frame_paths.append(output_path)
            except (asyncio.TimeoutError, FileNotFoundError):
                pass

        return frame_paths

    async def _extract_single_frame(
        self, video_path: Path, frames_dir: Path, name: str, seek_end: bool = False
    ) -> list[Path]:
        """Extract a single frame from the video."""
        output_path = frames_dir / f"{name}.png"
        cmd = ["ffmpeg", "-y"]
        if seek_end:
            cmd.extend(["-sseof", "-0.1"])
        cmd.extend([
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(output_path),
        ])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            if output_path.exists():
                return [output_path]
        except (asyncio.TimeoutError, FileNotFoundError):
            pass
        return []

    async def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return float(stdout.decode().strip())
        except (asyncio.TimeoutError, FileNotFoundError, ValueError):
            return 0.0

    def render_sync(self, scene_id: str, python_code: str, class_name: str) -> RenderResult:
        """Synchronous wrapper."""
        return asyncio.run(self.render(scene_id, python_code, class_name))
