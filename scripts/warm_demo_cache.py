"""Rozgrzewa cache odpowiedzi asystenta na pytania demo (przyciski przykładowe + pytanie spoza bazy).

Na Render cache w .llm_cache ginie przy każdym uśpieniu instancji, więc odpowiedzi demo zapisujemy w repozytorium
(deploy/llm_cache, LLM_CACHE_DIR w render.yaml). Klucz cache = skrót całego zapytania (model, prompt, kontekst),
więc trafia tylko dokładnie to samo pytanie w tym samym kontekście procesu. Pliki zawierają odpowiedź modelu
i liczniki tokenów – bez klucza API.

Użycie (klucz z .env, wywołania rozłożone w czasie ze względu na limit 8000 tokenów/min darmowego Groq):
    python -X utf8 scripts/warm_demo_cache.py [--pause 30]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("LLM_CACHE", "1")
os.environ.setdefault("LLM_CACHE_DIR", "deploy/llm_cache")
os.environ["KOMPAS_LLM_PER_MIN"] = "100"
os.environ["KOMPAS_LLM_PER_SESSION_HOUR"] = "100"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from app import assistant_service  # noqa: E402  (ładuje .env przez app.settings)

# (kontekst procesu w panelu, pytanie) – kontekst zmienia retrieval, więc i klucz cache
DEMO = [
    ("", "W jakim terminie oceniany może wnieść sprzeciw od oceny okresowej?"),
    ("", "Co zrobić, gdy nie miałem okazji zaobserwować danego zachowania pracownika?"),
    ("periodic", "W jakim terminie oceniany może wnieść sprzeciw od oceny okresowej?"),
    ("periodic", "Co zrobić, gdy nie miałem okazji zaobserwować danego zachowania pracownika?"),
    ("first", "Kiedy pierwsza ocena jest negatywna?"),
    ("first", "Kogo nie dotyczy egzamin ze służby przygotowawczej przy pierwszej ocenie?"),
    ("first", "Co zrobić, gdy nie miałem okazji zaobserwować danego zachowania pracownika?"),
    ("first", "W jakim terminie przełożony przeprowadza rozmowę wstępną w ramach pierwszej oceny?"),
    ("periodic", "Ile kryteriów dodatkowych mogę wybrać w ocenie okresowej?"),
    ("periodic", "Kiedy ocena okresowa jest negatywna?"),
    ("", "Ile wynosi płaca minimalna w 2026 roku?"),
    # pełny widok /asystent: przykładowe pytania, które nie mają gotowej odpowiedzi w FAQ (idą do modelu)
    ("", "Kiedy pierwsza ocena jest negatywna?"),
    ("", "Co jeśli pracownik nie zgadza się z oceną?"),
    ("", "Pracownik nie zgadza się z oceną okresową – co dalej?"),
]


def osp_demo() -> list[tuple[str, str, str]]:
    """(OSP z danych, arkusz, persona) dla OSP z propozycją arkusza C, jak w demo.

    Klucz cache nie zależy od osoby, bo OSP nie zawiera jej nazwiska. Nazw plików OSP nie zapisujemy w kodzie:
    pochodzą z dokumentów MC, których nie ma w publicznej kopii repozytorium.
    """
    import json

    from app import settings
    from app.skills import propose_form
    out = []
    for f in sorted((settings.DATA_DIR / "osp").glob("*.json")):
        osp = json.loads(f.read_text(encoding="utf-8"))
        if propose_form.propose_form(osp)["proposed_form"] == "periodic_c":
            out.append((f.stem, "periodic_c", "Jan Testowy"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=30.0, help="przerwa po wywołaniu modelu (s)")
    ap.add_argument("--prune", action="store_true", help="usuń z katalogu cache pliki, których pytania demo już nie używają")
    a = ap.parse_args()
    provider = assistant_service.get_assistant().llm
    used: set[Path] = set()
    original_path = provider._cache_path

    def tracking_path(kind, payload):
        p = original_path(kind, payload)
        used.add(p.resolve())
        return p

    provider._cache_path = tracking_path
    info = assistant_service.describe()
    print(f"dostawca={info['provider']} model={info['model']} klucz_ustawiony={info['api_key_set']} "
          f"cache={info['cache']} katalog={os.environ['LLM_CACHE_DIR']} retrieval={info['retrieval']}", flush=True)
    for process, q in DEMO:
        res = assistant_service.ask_formal(q, process or None, session_key=None)
        llm = res.get("llm") or {}
        cites = [c["id"] for c in res.get("citations") or []]
        print(f"[{process or 'pulpit':8s}] {res.get('source'):4s} refused={res['refused']!s:5s} cached={llm.get('cached')} "
              f"tokens={llm.get('prompt_tokens')}+{llm.get('completion_tokens')} {res['latency_s']:.1f}s "
              f"cites={cites[:3]} | {q}", flush=True)
        if res.get("source") == "llm" and not llm.get("cached"):
            time.sleep(a.pause)
    # propozycje kryteriów dodatkowych z zadań OSP (przycisk „Zaproponuj kryteria z zadań (AI)”) dla przykładowych OSP MC
    import json

    from app import settings
    for slug, form, employee in osp_demo():
        osp = json.loads((settings.DATA_DIR / "osp" / f"{slug}.json").read_text(encoding="utf-8"))
        out = assistant_service.osp_ai_candidates(osp, form, employee, "Marek Kierownik-Demo", None)
        llm = out.get("llm") or {}
        print(f"[osp-ai  ] {slug} {form} error={out.get('error') is not None} cached={llm.get('cached')} "
              f"przyjęte={[c['criterion_id'] for c in out.get('accepted', [])]} odrzucone={len(out.get('rejected', []))}", flush=True)
        if not out.get("error") and not llm.get("cached"):
            time.sleep(a.pause)
    if a.prune:
        cache_dir = Path(os.environ["LLM_CACHE_DIR"])
        for f in sorted(cache_dir.glob("chat_*.json")):
            if f.resolve() not in used:
                f.unlink()
                print(f"usunięto nieużywany wpis cache: {f.name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
