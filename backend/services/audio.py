from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from backend.core.config import get_settings
from backend.services.utils import ffprobe_duration, get_job_directory


settings = get_settings()


class AudioService:
    def synthesize(
        self, *, job_id: str, script_text: str, scenes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        job_dir = get_job_directory(job_id)
        output_path = job_dir / "narration.wav"

        try:
            self._synthesize_with_kokoro(
                script_text=script_text, output_path=output_path
            )
        except Exception:
            output_path = job_dir / "narration.mp3"
            self._synthesize_with_edge_tts(
                script_text=script_text, output_path=output_path
            )

        duration_seconds = ffprobe_duration(output_path)
        timed_scenes = self._timestamp_scenes(
            scenes=scenes, total_duration=duration_seconds
        )

        return {
            "audio_path": str(output_path),
            "duration_seconds": duration_seconds,
            "timed_scenes": timed_scenes,
        }

    def _synthesize_with_kokoro(self, *, script_text: str, output_path: Path) -> None:
        from kokoro import KPipeline  # type: ignore

        pipeline = KPipeline(lang_code=settings.kokoro_language_code)
        generator = pipeline(script_text, voice=settings.kokoro_voice, speed=1.0)
        audio_chunks: list[np.ndarray[Any, Any]] = []
        sample_rate = 24000

        for _, _, audio in generator:
            audio_chunks.append(np.asarray(audio))

        if not audio_chunks:
            raise RuntimeError("Kokoro returned no audio chunks")

        combined = np.concatenate(audio_chunks)
        sf.write(output_path, combined, sample_rate)

    def _synthesize_with_edge_tts(self, *, script_text: str, output_path: Path) -> None:
        import edge_tts

        async def _run() -> None:
            communicator = edge_tts.Communicate(script_text, settings.edge_tts_voice)
            await communicator.save(str(output_path))

        asyncio.run(_run())

    def _timestamp_scenes(
        self, *, scenes: list[dict[str, Any]], total_duration: float
    ) -> list[dict[str, Any]]:
        if not scenes:
            return []

        total_weight = sum(
            max(len(scene.get("sentence", "").strip()), 1) for scene in scenes
        )
        cursor = 0.0
        timed_scenes: list[dict[str, Any]] = []

        for index, scene in enumerate(scenes):
            weight = max(len(scene.get("sentence", "").strip()), 1)
            if index == len(scenes) - 1:
                scene_duration = max(total_duration - cursor, 0.5)
            else:
                scene_duration = max((weight / total_weight) * total_duration, 0.75)

            start_seconds = round(cursor, 3)
            end_seconds = round(min(cursor + scene_duration, total_duration), 3)
            cursor = end_seconds

            timed_scene = dict(scene)
            timed_scene["start_seconds"] = start_seconds
            timed_scene["end_seconds"] = end_seconds
            timed_scenes.append(timed_scene)

        if timed_scenes:
            timed_scenes[-1]["end_seconds"] = round(total_duration, 3)

        return timed_scenes
