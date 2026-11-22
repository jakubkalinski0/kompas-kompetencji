"""Ustawienia: ścieżki i zmienne środowiskowe.

Lokalnie wartości mogą pochodzić z pliku `.env` (ignorowanego przez git); na Render – ze zmiennych usługi.
Zmienne już ustawione w środowisku mają pierwszeństwo przed `.env`.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / ".claude" / "skills"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if os.environ.get("KOMPAS_NO_DOTENV") != "1":
    _load_dotenv(ROOT / ".env")


def _path(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    if not raw:
        return default
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


# Przetworzone dane (build_data.py). Na Render nie ma pdftotext, więc aplikacja czyta kopię
# zapisaną w repozytorium (deploy/processed) – decyzja opisana w README, sekcja „Wdrożenie”.
DATA_DIR = _path("KOMPAS_DATA_DIR", ROOT / "deploy" / "processed")
DB_PATH = _path("KOMPAS_DB", ROOT / "var" / "kompas.sqlite3")
CACHE_DIR = _path("KOMPAS_CACHE_DIR", ROOT / ".cache")
PERSONAS_PATH = SKILLS_DIR / "kompas-demo-i-pitch" / "assets" / "personas.json"
FONTS_DIR = SKILLS_DIR / "kompas-dokumenty-i-terminy" / "assets" / "fonts"

SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
ON_RENDER = bool(os.environ.get("RENDER"))
TIMEZONE = "Europe/Warsaw"
OFFICE_NAME = os.environ.get("KOMPAS_OFFICE_NAME", "Ministerstwo Cyfryzacji (dane fikcyjne – demo)")

# Retrieval: embeddingi wymagają Ollamy (nomic-embed-text). Na Render jej nie ma → sam BM25.
USE_EMBEDDINGS = os.environ.get("KOMPAS_EMBEDDINGS", "0") == "1"
# Ochrona darmowego limitu Groq (8000 tokenów/min, 200 tys./dzień): wywołania LLM na minutę dla całej
# instancji i na sesję na godzinę. Odpowiedzi z FAQ i odmowy regułą nie liczą się do limitu.
LLM_CALLS_PER_MIN = int(os.environ.get("KOMPAS_LLM_PER_MIN", "4"))
LLM_CALLS_PER_SESSION_HOUR = int(os.environ.get("KOMPAS_LLM_PER_SESSION_HOUR", "30"))
