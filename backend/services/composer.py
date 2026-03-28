from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.services.utils import ffprobe_duration, get_job_directory, run_command


settings = get_settings()


class ComposerService:
    def compose(
        self,
        *,
        job_id: str,
        scenes: list[dict[str, Any]],
        visual_manifest: list[dict[str, Any]],
        narration_path: str | Path,
        subtitles_path: str | Path,
        orientation: str,
        overlay_text: str | None = None,
    ) -> dict[str, Any]:
        job_dir = get_job_directory(job_id).resolve()
        composed_dir = (job_dir / "composed").resolve()
        composed_dir.mkdir(parents=True, exist_ok=True)

        narration = Path(narration_path).resolve()
        subtitles = Path(subtitles_path).resolve()
        dimensions = (1080, 1920) if orientation == "portrait" else (1920, 1080)
        total_duration = ffprobe_duration(narration)
        if orientation == "portrait":
            total_duration = min(total_duration, 59.0)

        segment_paths: list[Path] = []
        for index, asset in enumerate(visual_manifest, start=1):
            scene = scenes[index - 1] if index - 1 < len(scenes) else {}
            start_seconds = min(float(scene.get("start_seconds", 0.0)), total_duration)
            if start_seconds >= max(total_duration - 0.05, 0.0):
                break
            end_seconds = min(
                float(scene.get("end_seconds", total_duration)), total_duration
            )
            duration = max(end_seconds - start_seconds, 0.75)
            source_path = Path(asset["local_path"]).resolve()
            segment_path = composed_dir / f"segment_{index:02d}.mp4"
            self._normalize_clip(source_path, segment_path, duration, dimensions)
            segment_paths.append(segment_path.resolve())

        if not segment_paths:
            raise RuntimeError(
                "No normalized video segments were produced for composition."
            )

        concat_list_path = (composed_dir / "concat.txt").resolve()
        concat_list_path.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in segment_paths),
            encoding="utf-8",
        )

        stitched_path = (composed_dir / "stitched.mp4").resolve()
        run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                str(stitched_path),
            ],
            cwd=composed_dir,
        )

        mixed_audio_path = (composed_dir / "mixed_audio.m4a").resolve()
        self._mix_audio(
            narration=narration,
            mixed_audio_path=mixed_audio_path,
            total_duration=total_duration,
        )

        final_path = (job_dir / "final_video.mp4").resolve()
        subtitle_filter_path = self._escape_subtitle_path(subtitles)
        filter_chain: list[str] = []
        hook_text_path = None
        prepared_overlay_text = self._prepare_overlay_text(
            overlay_text or "", dimensions
        )
        if prepared_overlay_text:
            hook_text_path = (composed_dir / "hook_text.txt").resolve()
            hook_text_path.write_text(prepared_overlay_text, encoding="utf-8")
        intro_filter = self._build_intro_overlay_filter(
            overlay_text_path=hook_text_path,
            dimensions=dimensions,
        )
        if intro_filter:
            filter_chain.extend(intro_filter)
        filter_chain.append(f"subtitles='{subtitle_filter_path}'")

        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(stitched_path),
                "-i",
                str(mixed_audio_path),
                "-vf",
                ",".join(filter_chain),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(final_path),
            ],
            cwd=job_dir,
        )

        return {
            "stitched_path": str(stitched_path),
            "mixed_audio_path": str(mixed_audio_path),
            "final_video_path": str(final_path),
        }

    def _normalize_clip(
        self,
        source_path: Path,
        output_path: Path,
        duration: float,
        dimensions: tuple[int, int],
    ) -> None:
        width, height = dimensions
        source_path = source_path.resolve()
        output_path = output_path.resolve()
        zoom_width = int(width * 1.08)
        zoom_height = int(height * 1.08)
        fade_out_start = max(duration - 0.24, 0.0)
        filter_graph = (
            f"scale={zoom_width}:{zoom_height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},eq=saturation=1.12:contrast=1.05:brightness=0.02,"
            f"unsharp=5:5:0.45:5:5:0.0,fade=t=in:st=0:d=0.16,"
            f"fade=t=out:st={fade_out_start:.3f}:d=0.24,format=yuv420p,fps=30"
        )
        run_command(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(source_path),
                "-t",
                f"{duration:.3f}",
                "-vf",
                filter_graph,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                str(output_path),
            ]
        )

    def _mix_audio(
        self, *, narration: Path, mixed_audio_path: Path, total_duration: float
    ) -> None:
        narration = narration.resolve()
        mixed_audio_path = mixed_audio_path.resolve()
        background_track = settings.generic_background_music_path.resolve()
        if background_track.exists():
            background_input = ["-stream_loop", "-1", "-i", str(background_track)]
        else:
            background_input = [
                "-f",
                "lavfi",
                "-t",
                f"{total_duration:.3f}",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
            ]

        run_command(
            [
                "ffmpeg",
                "-y",
                *background_input,
                "-i",
                str(narration),
                "-filter_complex",
                f"[0:a]atrim=0:{total_duration:.3f},volume=0.10[bg];[1:a]volume=1.0[vo];[bg][vo]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map",
                "[aout]",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(mixed_audio_path),
            ]
        )

    @staticmethod
    def _escape_subtitle_path(path: Path) -> str:
        normalized = path.as_posix().replace("'", r"\'").replace(":", r"\:")
        return normalized

    def _build_intro_overlay_filter(
        self, *, overlay_text_path: Path | None, dimensions: tuple[int, int]
    ) -> list[str]:
        if overlay_text_path is None:
            return []

        _, height = dimensions
        box_y = 96 if height >= 1500 else 56
        box_h = 210 if height >= 1500 else 150
        font_size = 58 if height >= 1500 else 40
        escaped_path = self._escape_filter_path(overlay_text_path)
        return [
            (
                f"drawbox=x=70:y={box_y}:w=iw-140:h={box_h}:color=black@0.38:t=fill:enable='lt(t\\,2.6)'"
            ),
            (
                "drawtext="
                "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"textfile='{escaped_path}':reload=0:fontcolor=white:fontsize={font_size}:line_spacing=10:"
                f"x=(w-text_w)/2:y={box_y + 38}:enable='lt(t\\,2.6)'"
            ),
        ]

    @staticmethod
    def _prepare_overlay_text(text: str, dimensions: tuple[int, int]) -> str:
        cleaned = " ".join(text.upper().split())
        if not cleaned:
            return ""

        max_chars = 18 if dimensions[1] >= 1500 else 28
        words = cleaned.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
            if len(lines) == 1 and len(current) > max_chars:
                break
        if current:
            lines.append(current)
        return "\n".join(lines[:2])[: max_chars * 2 + 2]

    @staticmethod
    def _escape_filter_path(path: Path) -> str:
        return path.as_posix().replace("'", r"\'").replace(":", r"\:")
