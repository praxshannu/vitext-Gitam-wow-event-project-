"""
FFmpeg utility functions for the Vitext pipeline.

Provides helpers for:
- Video concatenation with transitions
- Frame extraction
- Audio overlay
- Video duration queries
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Optional


async def get_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
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


async def concat_videos_simple(
    video_paths: list[Path],
    output_path: Path,
) -> bool:
    """
    Concatenate videos using FFmpeg's concat demuxer (no re-encoding, fast).

    All input videos must have the same codec, resolution, and frame rate.
    """
    # Write the concat list file
    list_file = output_path.parent / f"{output_path.stem}_concat_list.txt"
    with open(list_file, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        # Clean up the list file
        list_file.unlink(missing_ok=True)
        return proc.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError):
        list_file.unlink(missing_ok=True)
        return False


async def concat_videos_with_crossfade(
    video_paths: list[Path],
    output_path: Path,
    crossfade_duration: float = 0.5,
) -> bool:
    """
    Concatenate videos with crossfade transitions using FFmpeg's xfade filter.

    This re-encodes the video, so it's slower but produces seamless transitions.
    """
    if len(video_paths) == 0:
        return False
    if len(video_paths) == 1:
        # Single video — just copy
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return True

    # Get durations for calculating xfade offsets
    durations = []
    for vp in video_paths:
        dur = await get_duration(vp)
        durations.append(dur)

    # Build the complex filter graph for chained xfade
    # For N videos, we need N-1 xfade filters
    inputs = []
    for i, vp in enumerate(video_paths):
        inputs.extend(["-i", str(vp)])

    filter_parts = []
    current_label = "[0:v]"

    cumulative_offset = 0.0
    for i in range(1, len(video_paths)):
        offset = cumulative_offset + durations[i - 1] - crossfade_duration
        if offset < 0:
            offset = cumulative_offset + durations[i - 1]  # Skip crossfade if too short

        out_label = f"[v{i}]" if i < len(video_paths) - 1 else "[outv]"
        filter_parts.append(
            f"{current_label}[{i}:v]xfade=transition=fade:duration={crossfade_duration}:offset={offset:.3f}{out_label}"
        )
        current_label = out_label
        cumulative_offset = offset

    filter_str = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[outv]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        str(output_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        return proc.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError):
        return False


async def overlay_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    audio_volume: float = 1.0,
) -> bool:
    """
    Overlay an audio track onto a video.

    The audio is trimmed to match the video duration.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[1:a]volume={audio_volume}[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-shortest",
        str(output_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        return proc.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError):
        return False


async def extract_frame(
    video_path: Path,
    output_path: Path,
    timestamp: float = 0.0,
) -> bool:
    """Extract a single frame from a video at a given timestamp."""
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
        return output_path.exists()
    except (asyncio.TimeoutError, FileNotFoundError):
        return False
