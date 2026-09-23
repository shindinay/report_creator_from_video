# -*- coding: utf-8 -*-
"""Создание итогового протокола встречи в формате Markdown.

Использование:
    python create_report.py --transcript <путь> --place "<переговорная>" \
        --agenda "<повестка>" --date "ДД.ММ.ГГГГ ЧЧ:ММ" --duration <мин> \
        --output <имя_отчета.md> \
        --decision "решение" --owner "ФИО" --due "ДД.ММ.ГГГГ" \
        (пары --decision/--owner/--due повторяются для каждой строки)

Если дата/длительность не переданы, берутся из метаданных видео,
путь к которому указан аргументом --video.
"""

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = PROJECT_ROOT / "artifact"
ENV_FILE = PROJECT_ROOT / ".env"


def read_env() -> dict:
    """Чтение переменных из .env в корне проекта."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def resolve_output_dir() -> Path:
    """Папка для протоколов: OUTPUT_FOLDER из .env, иначе artifact/ в проекте."""
    env = read_env()
    raw = env.get("OUTPUT_FOLDER", "").strip()
    if not raw:
        return ARTIFACT_DIR
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def from_video_meta(video: Path):
    """Дата записи и длительность из метаданных видео."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:format_tags=creation_time",
            "-of", "default=noprint_wrappers=1",
            str(video),
        ],
        capture_output=True, text=True, check=True,
    )
    duration_min, date_str = None, ""
    for line in result.stdout.splitlines():
        if line.startswith("duration="):
            duration_min = round(float(line.split("=")[1]) / 60)
        elif line.startswith("tag:creation_time="):
            raw = line.split("=", 1)[1]
            dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
            date_str = dt.strftime("%d.%m.%Y %H:%M")
    return date_str, duration_min


def main() -> int:
    p = argparse.ArgumentParser(description="Генерация протокола встречи (Markdown)")
    p.add_argument("--transcript", required=True, help="Путь к файлу расшифровки")
    p.add_argument("--place", default="", help="Место встречи (переговорная)")
    p.add_argument("--agenda", default="", help="Повестка (краткая тема встречи)")
    p.add_argument("--date", default="", help="Дата встречи ДД.ММ.ГГГГ ЧЧ:ММ")
    p.add_argument("--duration", type=int, help="Длительность в минутах")
    p.add_argument("--video", help="Путь к видео (для метаданных, если нет --date/--duration)")
    p.add_argument("--output", required=True, help="Имя итогового отчета (.md)")
    args, unknown = p.parse_known_args()

    # Решения задаются повторяющимися тройками: --decision X --owner Y --due Z
    decisions = []
    cur = None
    tokens = unknown
    for idx, tok in enumerate(tokens):
        if tok == "--decision":
            if cur:
                decisions.append(cur)
            cur = {"decision": tokens[idx + 1] if idx + 1 < len(tokens) else "", "owner": "", "due": ""}
        elif tok == "--owner" and cur is not None:
            cur["owner"] = tokens[idx + 1] if idx + 1 < len(tokens) else ""
        elif tok == "--due" and cur is not None:
            cur["due"] = tokens[idx + 1] if idx + 1 < len(tokens) else ""
    if cur:
        decisions.append(cur)

    date_str = args.date
    duration = args.duration
    if (not date_str or duration is None) and args.video:
        meta_date, meta_dur = from_video_meta(Path(args.video).resolve())
        date_str = date_str or meta_date
        duration = duration if duration is not None else meta_dur

    if not date_str:
        date_str = ""
    dur_str = str(duration) if duration is not None else ""

    rows = "| № | Принятое решение | Ответственный | Ожидаемая дата выполнения |\n"
    rows += "|---|------------------|---------------|---------------------------|\n"
    if decisions:
        for n, d in enumerate(decisions, 1):
            rows += f"| {n} | {d.get('decision', '')} | {d.get('owner') or '—'} | {d.get('due') or '—'} |\n"
    else:
        rows += "| 1 | — | — | — |\n"

    report = f"""# Протокол встречи

## Таблица с полями

| Поле | Значение |
|------|----------|
| Повестка | {args.agenda} |
| Дата встречи | {date_str} |
| Длительность | {dur_str} |
| Организатор встречи | |
| Участники встречи | |
| Место встречи | {args.place} |

## Итоги, решения, дальнейшие действия

{rows}
"""
    out_dir = resolve_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / args.output
    if out.suffix != ".md":
        out = out.with_suffix(".md")
    out.write_text(report, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
