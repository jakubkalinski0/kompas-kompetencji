"""Import klocków ze skilli `.claude/skills/kompas-*` (jedno źródło prawdy, testy skilli pilnują logiki).

Skrypty skilli nie są pakietami pip, więc dodajemy ich katalogi do sys.path w jednym miejscu.
"""
from __future__ import annotations

import sys

from .settings import SKILLS_DIR

_SCRIPT_DIRS = [
    "kompas-model-i-silnik-oceny/scripts",
    "kompas-analiza-osp/scripts",
    "kompas-dokumenty-i-terminy/scripts",
    "kompas-asystent-ai/scripts",
]
for _sub in _SCRIPT_DIRS:
    _p = str(SKILLS_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kompas_engine as engine  # noqa: E402  silnik oceny (sugestia, wynik, ślad, strażnik)
import osp_parser  # noqa: E402  OSP .docx → JSON bez danych osobowych
import propose_form  # noqa: E402  propozycja arkusza B/C i kandydaci na kryteria dodatkowe
import render_pdf  # noqa: E402  PDF arkuszy wg wzorów z rozporządzeń
import rbac  # noqa: E402  widok dokumentu wg roli
import deadlines  # noqa: E402  terminy z podstawą prawną, statusy
import llm_provider  # noqa: E402  Ollama | API zgodne z OpenAI (Groq)
import privacy_shield  # noqa: E402  maskowanie danych osobowych przed wysłaniem do modelu
import behavior_match  # noqa: E402  opis zachowań → propozycje poziomów wskaźników z dosłownym dowodem
from assistant import Assistant  # noqa: E402  asystent formalny i rozmowy

__all__ = ["engine", "osp_parser", "propose_form", "render_pdf", "rbac", "deadlines", "llm_provider", "privacy_shield",
           "behavior_match", "Assistant"]
