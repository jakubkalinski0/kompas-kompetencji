"""Wspólne fikstury testów kompas-analiza-osp.

KOMPAS_MATERIALY = katalog z materiałami Partnera (np. `materialy/` w repo rozwiązania albo
`KompasKompetencji/HackNation`); testy na prawdziwych OSP szukają w nim `OSP_word.zip` i są
pomijane, gdy zmiennej lub pliku brak.
"""
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from osp_parser import iter_docx_inputs, parse_osp_docx  # noqa: E402


@pytest.fixture(scope="session")
def partner_osps():
    root = os.environ.get("KOMPAS_MATERIALY")
    if not root or not Path(root).exists():
        pytest.skip("Brak KOMPAS_MATERIALY – pomijam testy na OSP Partnera")
    zips = sorted(Path(root).rglob("OSP_word.zip"))
    if not zips:
        pytest.skip("Nie znaleziono OSP_word.zip w KOMPAS_MATERIALY")
    out = {}
    for name, data in iter_docx_inputs(zips[0]):
        res = parse_osp_docx(data, filename=name)
        low = name.lower()
        key = "naczelnik" if "naczelnik" in low else "radca" if "radca" in low else "specjalista" if "specjalista" in low else name
        out[key] = res
    return out


@pytest.fixture()
def tiny_model():
    """Minimalny competency_model (kontrakt C1) z tekstami zastępczymi do testów walidatora LLM."""
    def comp(cid, name, text):
        return {"name": name, "indicators": [{"id": f"{cid}.1", "text": f"Przykładowy wskaźnik: {text}."}]}

    return {
        "myslenie_analityczne": comp("myslenie_analityczne", "Myślenie analityczne", "porządkowanie informacji przed decyzją"),
        "negocjowanie": comp("negocjowanie", "Negocjowanie", "przygotowanie stanowiska do rozmów"),
        "zarzadzanie_ludzmi": comp("zarzadzanie_ludzmi", "Zarządzanie ludźmi", "podział zadań w zespole"),
        "komunikacja": comp("komunikacja", "Komunikacja", "uważne słuchanie rozmówcy"),
    }
