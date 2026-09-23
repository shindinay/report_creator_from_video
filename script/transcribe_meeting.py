# -*- coding: utf-8 -*-
"""Распознавание речи из видеозаписи встречи.

Использование:
    python transcribe_meeting.py <путь_к_видео> [--model medium]

Результат:
    artifact/<имя_видео>_transcript.md — расшифровка с таймкодами.
    В stdout печатает JSON: {"duration_minutes": N, "transcript": "<путь>"}

Требует: ffmpeg (в PATH), пакет openai-whisper.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Позволяет использовать ffmpeg, установленный пакетом imageio-ffmpeg
_FFMPEG_EXE = shutil.which("ffmpeg")
if not _FFMPEG_EXE:
    try:
        import imageio_ffmpeg
        _FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
        # Whisper вызывает "ffmpeg" по имени — бинарник imageio-ffmpeg имеет
        # длинное имя, поэтому копируем его как ffmpeg.exe и добавляем в PATH
        bin_dir = Path(__file__).resolve().parent.parent / "temp" / "ffmpeg-bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_exe = bin_dir / "ffmpeg.exe"
        if not ffmpeg_exe.exists():
            shutil.copy(_FFMPEG_EXE, ffmpeg_exe)
        _FFMPEG_EXE = str(ffmpeg_exe)
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]
    except ImportError:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = PROJECT_ROOT / "temp"
ARTIFACT_DIR = PROJECT_ROOT / "artifact"

SUPPORTED_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4a", ".wav", ".mp3"}


def get_duration_seconds(path: Path) -> float:
    """Длительность файла через ffprobe (или fallback на ffmpeg)."""
    if _FFMPEG_EXE and shutil.which("ffprobe") is None:
        # ffprobe отсутствует — получаем длительность через ffmpeg -i
        result = subprocess.run(
            [_FFMPEG_EXE, "-i", str(path)],
            capture_output=True, text=True,
        )
        import re
        m = re.search(r"Duration: (\d+):(\d+):(\d+)", result.stderr)
        if not m:
            raise RuntimeError("Не удалось определить длительность видео")
        h, mi, s = map(int, m.groups())
        return h * 3600 + mi * 60 + s
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def extract_audio(video: Path, wav_out: Path) -> None:
    """Извлечение аудиодорожки в mono 16 kHz (требование Whisper)."""
    subprocess.run(
        [
            _FFMPEG_EXE or "ffmpeg", "-y", "-i", str(video),
            "-vn", "-ac", "1", "-ar", "16000",
            str(wav_out),
        ],
        capture_output=True, text=True, check=True,
    )


def transcribe(wav: Path, model_name: str) -> list:
    """Распознавание речи, возвращает список сегментов [{start, end, text}]."""
    import whisper  # локальный Whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(str(wav), language="ru", verbose=False)
    return result["segments"]


def fmt_ts(seconds: float) -> str:
    t = datetime.timedelta(seconds=int(seconds))
    return str(t)


def write_transcript(segments: list, out_path: Path) -> None:
    lines = ["# Расшифровка встречи", ""]
    for seg in segments:
        lines.append(f"[{fmt_ts(seg['start'])} - {fmt_ts(seg['end'])}] {seg['text'].strip()}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Распознавание речи из видео встречи")
    parser.add_argument("video", help="Путь к файлу видео")
    parser.add_argument("--model", default="medium", help="Модель Whisper (default: medium)")
    args = parser.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print(f"Файл не найден: {video}", file=sys.stderr)
        return 1
    if video.suffix.lower() not in SUPPORTED_EXT:
        print(f"Неподдерживаемый формат: {video.suffix}", file=sys.stderr)
        return 1

    TEMP_DIR.mkdir(exist_ok=True)
    ARTIFACT_DIR.mkdir(exist_ok=True)

    duration = get_duration_seconds(video)
    wav = TEMP_DIR / (video.stem + ".wav")
    print(f"Извлечение аудио: {wav}", file=sys.stderr)
    extract_audio(video, wav)

    print(f"Распознавание (модель {args.model}), это может занять несколько минут...", file=sys.stderr)
    segments = transcribe(wav, args.model)

    transcript_path = ARTIFACT_DIR / f"{video.stem}_transcript.md"
    write_transcript(segments, transcript_path)

    # Временный wav больше не нужен
    wav.unlink(missing_ok=True)

    print(json.dumps({
        "duration_minutes": round(duration / 60),
        "transcript": str(transcript_path),
        "video_modified": datetime.datetime.fromtimestamp(video.stat().st_mtime).strftime("%d.%m.%Y %H:%M"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
