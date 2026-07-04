"""
Assembly Agent — final video stitching from rendered scene chunks.

After all scenes pass the Critic, the Assembly Agent:
1. Collects all scene .mp4 chunks in order
2. Applies transitions (cut, crossfade, or dissolve)
3. Concatenates into a single final .mp4
4. Optionally overlays background audio
5. Outputs to the user's configured save location
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from vitext.config import PipelineConfig, default_config
from vitext.utils.ffmpeg_utils import (
    concat_videos_simple,
    concat_videos_with_crossfade,
    overlay_audio,
    get_duration,
)


@dataclass
class AssemblyResult:
    """Result of the Assembly Agent's work."""
    success: bool
    output_path: Optional[Path] = None
    total_duration: float = 0.0
    scene_count: int = 0
    error_message: str = ""


class AssemblyAgent:
    """
    Concatenates rendered scene videos into a single final output.

    Usage:
        agent = AssemblyAgent(config)
        result = await agent.assemble(
            scene_videos={"scene_01": Path("s1.mp4"), "scene_02": Path("s2.mp4")},
            scene_order=["scene_01", "scene_02"],
            output_filename="chain_rule_explained.mp4",
        )
        print(f"Final video: {result.output_path}")
    """

    def __init__(self, config: PipelineConfig = None):
        self.config = config or default_config
        self.config.ensure_directories()

    async def assemble(
        self,
        scene_videos: dict[str, Path],
        scene_order: list[str],
        output_filename: str = "final_output.mp4",
        audio_path: Optional[Path] = None,
    ) -> AssemblyResult:
        """
        Assemble all scene videos into a single final video.

        Args:
            scene_videos: Map of scene_id → rendered .mp4 path.
            scene_order: Ordered list of scene_ids for the final sequence.
            output_filename: Name for the output file.
            audio_path: Optional background audio track to overlay.

        Returns:
            AssemblyResult with the final video path and metadata.
        """
        # Validate all scenes are available
        missing = [sid for sid in scene_order if sid not in scene_videos]
        if missing:
            return AssemblyResult(
                success=False,
                error_message=f"Missing scene videos: {missing}",
            )

        # Order the video paths
        ordered_paths = [scene_videos[sid] for sid in scene_order]

        # Validate all files exist
        not_found = [str(p) for p in ordered_paths if not p.exists()]
        if not_found:
            return AssemblyResult(
                success=False,
                error_message=f"Video files not found: {not_found}",
            )

        output_path = self.config.output_dir / output_filename
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        # Choose concatenation method based on config
        transition = self.config.transition_type

        if transition == "cut":
            success = await concat_videos_simple(ordered_paths, output_path)
        elif transition in ("crossfade", "dissolve"):
            success = await concat_videos_with_crossfade(
                ordered_paths,
                output_path,
                crossfade_duration=self.config.transition_duration,
            )
        else:
            # Default to simple concat
            success = await concat_videos_simple(ordered_paths, output_path)

        if not success:
            return AssemblyResult(
                success=False,
                error_message="FFmpeg concatenation failed. Check that all scenes have matching resolution/codec.",
                scene_count=len(ordered_paths),
            )

        # If audio track is provided, overlay it
        if audio_path and audio_path.exists():
            audio_output = output_path.with_stem(f"{output_path.stem}_with_audio")
            audio_success = await overlay_audio(output_path, audio_path, audio_output)
            if audio_success:
                # Replace the original with the audio version
                output_path.unlink()
                audio_output.rename(output_path)

        # Get total duration
        total_dur = await get_duration(output_path)

        return AssemblyResult(
            success=True,
            output_path=output_path,
            total_duration=total_dur,
            scene_count=len(ordered_paths),
        )

    def assemble_sync(self, **kwargs) -> AssemblyResult:
        """Synchronous wrapper."""
        return asyncio.run(self.assemble(**kwargs))
