"""Walidacja tekstu wygenerowanego PDF względem dokumentu oceny (pdftotext -enc UTF-8).

Użycie:
    python validate_pdf.py arkusz.pdf --expect dokument_oceny.json [--kind arkusz|karta] [--json]

Sprawdza: polskie znaki (te z oczekiwanych tekstów), nazwisko ocenianego, nazwy kryteriów,
średnią i wynik (znak X przy POZYTYWNA/NEGATYWNA), wszystkie przypisy dosłownie z form_texts.json,
obecność/brak Części III, brak wniosków rozwojowych przy negatywnej pierwszej ocenie,
brak notatek S-D-R w oficjalnym arkuszu; dla karty – nagłówek „Dokument roboczy…” i notatki S-D-R.
Wymaga poppler (pdftotext) w PATH. Kod wyjścia: 0 – wszystko OK, 1 – co najmniej jeden błąd.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FORM_TEXTS = SKILL_DIR / "assets" / "form_texts.json"
POLISH = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
KARTA_HEADER = "Dokument roboczy przełożonego – nie włączać do akt osobowych"


def pdf_text(pdf: Path, layout: bool = False) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("Brak pdftotext (poppler) w PATH")
    cmd = [exe, "-enc", "UTF-8"] + (["-layout"] if layout else []) + [str(pdf), "-"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8")


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "")
    return s.replace(" )", ")").strip()


def squash(s: str) -> str:
    """Porównanie odporne na łamanie wierszy i odnośniki przypisów (np. 'CYWILNEJ1)')."""
    return re.sub(r"\s+", "", s or "")


def fmt_num(x) -> str:
    return f"{float(x):.2f}".replace(".", ",")


def check(pdf: Path, doc: dict, kind: str = "arkusz") -> list:
    """Zwraca listę (nazwa_testu, ok, szczegóły)."""
    raw_all = pdf_text(pdf)
    # stopki stron ("… – strona N") i nagłówek karty przerywają tekst przypisów na granicy stron
    raw = "\n".join(ln for ln in raw_all.splitlines()
                    if not re.search(r"– strona \d+\s*$", ln) and ln.strip() != KARTA_HEADER)
    flat, sq = norm(raw), squash(raw)
    layout = pdf_text(pdf, layout=True)
    results = []

    def add(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    emp = doc.get("employee") or {}
    expected_texts = [emp.get("full_name", "")] + [c.get("name", "") for c in doc.get("criteria", [])]
    form = doc.get("form")
    footnotes = {}
    if kind == "arkusz":
        footnotes = json.loads(FORM_TEXTS.read_text(encoding="utf-8"))["forms"][form]["footnotes"]
        expected_texts += list(footnotes.values())
    needed = sorted({ch for txt in expected_texts for ch in txt if ch in POLISH})
    missing = [ch for ch in needed if ch not in raw]
    add("polskie_znaki", not missing and needed, f"oczekiwane {''.join(needed)}; brak: {''.join(missing) or '-'}")
    add("brak_znakow_zastepczych", "�" not in raw and "■" not in raw, "")
    # nazwisko: w arkuszu imię i nazwisko są w osobnych polach – sprawdzamy oba człony
    name_parts = [p for p in (emp.get("full_name") or "").split() if p]
    add("nazwisko_ocenianego", name_parts and all(p in flat for p in name_parts), emp.get("full_name"))
    for c in doc.get("criteria", []):
        add(f"kryterium:{c.get('id')}", squash(c.get("name")) in sq, c.get("name"))
    if kind == "karta":
        add("naglowek_karty", squash(KARTA_HEADER) in squash(raw_all), KARTA_HEADER)
        for c in doc.get("criteria", []):
            for r in c.get("indicator_ratings", []):
                if r.get("sdr_note"):
                    add(f"sdr_w_karcie:{r['indicator_id']}", squash(r["sdr_note"]) in sq, r["sdr_note"][:40])
        return results
    # --- arkusz oficjalny
    pts = [c.get("final_points") for c in doc.get("criteria", []) if c.get("final_points") is not None]
    avg = doc.get("average")
    if avg is None and pts:
        avg = round(sum(pts) / len(pts), 2)
    add("srednia", avg is not None and fmt_num(avg) in flat, fmt_num(avg) if avg is not None else "brak")
    result = doc.get("result")
    if result:
        word = "POZYTYWNA" if result == "pozytywna" else "NEGATYWNA"
        marked = re.search(word + r"\s*\d*\)?\s+X(\s|$)", layout, re.M)
        add("wynik_zaznaczony", marked, f"{word} + X")
    for k, txt in footnotes.items():
        add(f"przypis_{k}", squash(txt) in sq, txt[:50])
    if form in ("periodic_b", "periodic_c"):
        expect3 = (emp.get("corps_status") == "urzednik_sc" and bool(doc.get("part3"))
                   and bool(doc.get("part3_requested") or (doc.get("print") or {}).get("include_part3"))
                   and result == "pozytywna")
        has3 = "CZĘŚĆ III" in raw and "WNIOSEK O PRZYZNANIE URZĘDNIKOWI" in raw
        add("czesc_III", has3 == expect3, f"oczekiwana={expect3}, jest={has3}")
    if form == "first_eval" and result != "pozytywna" and doc.get("development_conclusions"):
        add("brak_wnioskow_rozwojowych_przy_negatywnej",
            squash(doc["development_conclusions"]) not in sq, "przypis 8")
    leaked = [r["sdr_note"] for c in doc.get("criteria", []) for r in c.get("indicator_ratings", [])
              if r.get("sdr_note") and squash(r["sdr_note"]) in sq]
    add("brak_notatek_SDR_w_arkuszu", not leaked, f"wycieki: {len(leaked)}")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Walidacja PDF arkusza/karty względem dokumentu oceny")
    ap.add_argument("pdf")
    ap.add_argument("--expect", required=True, help="dokument oceny JSON (C3)")
    ap.add_argument("--kind", choices=["arkusz", "karta"], default="arkusz")
    ap.add_argument("--json", action="store_true", help="wynik jako JSON")
    args = ap.parse_args(argv)
    doc = json.loads(Path(args.expect).read_text(encoding="utf-8"))
    res = check(Path(args.pdf), doc, args.kind)
    failed = [r for r in res if not r[1]]
    if args.json:
        print(json.dumps({"pdf": args.pdf, "checks": len(res), "failed": [{"check": n, "detail": d} for n, _, d in failed]},
                         ensure_ascii=False))
    else:
        for name, ok, detail in res:
            if not ok:
                print(f"FAIL {name}: {detail}")
        print(f"{args.pdf}: {len(res) - len(failed)}/{len(res)} sprawdzeń OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
