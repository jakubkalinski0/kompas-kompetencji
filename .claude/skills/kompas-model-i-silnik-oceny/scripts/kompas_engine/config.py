"""Ładowanie konfiguracji reguł (assets/forms_config.json) i schematu C3.

Ścieżki liczone względem pakietu, więc skill działa po skopiowaniu do
`.claude/skills/kompas-model-i-silnik-oceny/` w dowolnym repozytorium.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_DIR / "assets"
DEFAULT_CONFIG_PATH = ASSETS_DIR / "forms_config.json"
DEFAULT_SCHEMA_PATH = ASSETS_DIR / "evaluation_schema.json"


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=8)
def _cached(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def load_config(path: str | Path | None = None) -> dict:
    """Zwraca świeżą kopię konfiguracji (można ją modyfikować, np. metodę sugestii)."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    return json.loads(_cached(str(p)))


def load_schema(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_SCHEMA_PATH
    return json.loads(_cached(str(p)))


def load_model(path: str | Path) -> dict:
    """competency_model.json (kontrakt C1, agent DANE)."""
    return _read_json(Path(path))


def rule_source(config: dict, rule_id: str) -> str:
    for rule in config.get("rules", []):
        if rule["id"] == rule_id:
            return rule["source"]
    return ""


def catalog_names(config: dict) -> dict[str, str]:
    return {c["id"]: c["name"] for c in config["criteria_catalog"]}
