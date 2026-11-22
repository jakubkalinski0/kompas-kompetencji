"""Publiczna kopia kodu do repozytorium zgłoszenia: bez materiałów i danych MC, bez historii gita.

Repozytorium organizacji zostaje prywatne (są w nim materialy/ i dane MC). Do publicznego repozytorium
zgłoszenia trafia kopia plików śledzonych przez git:
- bez katalogów z danymi MC (EXCLUDE_PREFIXES) i plików, które bez nich nie mają sensu (EXCLUDE_FILES),
- z raportami ewaluacji, w których napisy z tekstem MC są zastąpione znacznikiem (liczby zostają),
- sprawdzona skanem „odcisków” tekstów MC: każdy fragment modelu kompetencji albo OSP w kopii to wyciek.

Użycie (z katalogu głównego repozytorium; cel poza repozytorium, np. klon pustego repozytorium publicznego):
    python -X utf8 scripts/export_public.py ../kompas-public
Kod wyjścia: 0 – brak wycieków, 1 – teksty MC albo klucze w kopii (lista plików i linii), 2 – błąd.
Katalog docelowy musi być pusty albo pochodzić z wcześniejszego eksportu (plik .export_public); jego .git zostaje.

Odciski liczone z lokalnych, prywatnych danych deploy/processed: wskaźniki, opisy poziomów i instrukcja modelu
kompetencji (także jednostki bazy wiedzy z modelu), cel i zadania z OSP (okna 40 znaków po normalizacji
białych znaków; krótsze teksty w całości), symbole stanowisk (także w postaci sluga) i komórki organizacyjne z OSP.
Ustawy, rozporządzenia, wzory arkuszy, poradniki KPRM i Q&A z gov.pl są publiczne i nie są odciskami.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "deploy" / "processed"
MARKER = ".export_public"
EXCLUDE_PREFIXES = (
    "materialy/",          # oryginały od MC
    "pelne_tresci/",       # transkrypcja pełnej treści zadania (materiał organizatora)
    "deploy/",             # przetworzone dane MC (model, OSP, baza wiedzy z modelem) i cache z cytatami OSP
    ".claude/hn-prep/",    # research zespołu z odniesieniami do materiałów MC
    "docs/zgloszenie.md",  # robocza kopia formularza
)
EXCLUDE_FILES = {
    "docs/wewnetrzne.md",                                            # notatki zespołu (terminy, pytania do mentorów)
    ".claude/skills/kompas-analiza-osp/references/test-run.md",     # zapis uruchomienia na OSP Partnera (ich treść)
    ".claude/skills/kompas-analiza-osp/tests/test_osp_partner.py",  # testy na OSP Partnera (wymagają materialy/)
}
EXCLUDE_NAMES = {".env"}
WINDOW, STEP, MIN_EXACT = 40, 10, 20
REDACTED = "[pominięto w publicznej kopii: fragment materiału MC]"
SECRET_RX = re.compile(r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}")
MD_LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    return re.sub(r"[^a-z0-9]+", "_", "".join(c for c in t if not unicodedata.combining(c)).lower()).strip("_")


def fingerprints() -> tuple[dict[str, str], dict[str, str]]:
    """(okno 40 znaków → źródło, krótki napis szukany w całości → źródło)."""
    texts: list[tuple[str, str]] = []
    exact: list[tuple[str, str]] = []
    model = json.loads((DATA / "competency_model.json").read_text(encoding="utf-8"))
    for i, txt in enumerate(model.get("instructions") or []):
        texts.append((txt, f"model: instrukcja {i + 1}"))
    for comp in model["competencies"]:
        for ind in comp["indicators"]:
            texts.append((ind["text"], f"model: {ind['id']}"))
            for lvl, txt in ind["levels"].items():
                texts.append((txt, f"model: {ind['id']} poziom {lvl}"))
    # teksty publiczne: nazwy kryteriów (rozporządzenie), ustawa, rozporządzenia, wzory arkuszy, poradniki KPRM, Q&A gov.pl
    public = [f" {norm(c[k])} " for c in model["competencies"] for k in ("name", "name_in_model", "id")]  # ze spacjami:
    # nazwa 39-znakowa ze spacją to już okno 40 znaków
    public += [i["id"] for c in model["competencies"] for i in c["indicators"]]  # identyfikatory nadał zespół
    for line in (DATA / "kb" / "kb_chunks.jsonl").read_text(encoding="utf-8").splitlines():
        chunk = json.loads(line)
        if chunk["source_id"] == "model_kompetencji":
            texts.append((chunk["text"], f"baza wiedzy: {chunk['id']}"))
        else:
            public.append(norm(chunk["text"]))
    for f in sorted((DATA / "osp").glob("*.json")):
        osp = json.loads(f.read_text(encoding="utf-8"))
        p1, p2 = osp.get("part1") or {}, osp.get("part2") or {}
        if p2.get("purpose"):
            texts.append((p2["purpose"], f"OSP {f.stem}: cel"))
        for tasks in (p2.get("tasks") or {}).values():
            for t in tasks:
                texts.append((t["text"], f"OSP {f.stem}: zadanie {t.get('no')}"))
        if p1.get("position_symbol"):  # nazwy departamentów i wydziałów są publiczne (struktura MC w BIP) – bez odcisku
            exact.append((p1["position_symbol"], f"OSP {f.stem}: symbol stanowiska"))
            exact.append((slug(p1["position_symbol"]), f"OSP {f.stem}: symbol stanowiska (slug)"))
    public_windows = {t[i:i + WINDOW] for t in public for i in range(0, len(t) - WINDOW + 1)}
    public_text = "\n".join(public)
    windows: dict[str, str] = {}
    needles: dict[str, str] = {}
    for text, src in texts:
        t = norm(text)
        if len(t) < WINDOW:
            if len(t) >= MIN_EXACT and t not in public_text:
                needles.setdefault(t, src)
            continue
        for i in range(0, len(t) - WINDOW + 1, STEP):
            if t[i:i + WINDOW] not in public_windows:
                windows.setdefault(t[i:i + WINDOW], src)
    for text, src in exact:
        needles.setdefault(norm(text), src)
    return windows, needles


def find(text: str, windows: dict[str, str], needles: dict[str, str]) -> dict[str, str]:
    """{źródło: znaleziony fragment} dla znormalizowanego tekstu."""
    hits: dict[str, str] = {}
    for i in range(0, max(0, len(text) - WINDOW + 1)):
        w = text[i:i + WINDOW]
        if w in windows:
            hits.setdefault(windows[w], w)
    for needle, src in needles.items():
        if needle in text:
            hits.setdefault(src, needle)
    m = SECRET_RX.search(text)
    if m:
        hits.setdefault("wzorzec klucza API", m.group(0))
    return hits


def json_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from json_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from json_strings(v)


def load_json_docs(raw: str) -> list:
    try:
        return [json.loads(raw)]
    except ValueError:
        docs = []
        for line in raw.splitlines():
            try:
                docs.append(json.loads(line))
            except ValueError:
                pass
        return docs


def line_of(raw: str, fragment: str) -> int | None:
    rx = re.compile(r"\s+".join(re.escape(p) for p in fragment.split(" ") if p))
    m = rx.search(raw)
    return raw.count("\n", 0, m.start()) + 1 if m else None


def scan(dest: Path, windows, needles) -> tuple[dict[str, dict[str, int | None]], list[str]]:
    """{plik: {źródło: linia}} oraz pliki binarne, których skan nie czyta (do przejrzenia ręcznie)."""
    leaks: dict[str, dict[str, int | None]] = {}
    binary: list[str] = []
    for f in sorted(dest.rglob("*")):
        if not f.is_file() or ".git" in f.relative_to(dest).parts:
            continue
        rel = f.relative_to(dest).as_posix()
        try:
            raw = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            binary.append(rel)
            continue
        variants = [norm(raw)]
        if f.suffix in (".json", ".jsonl"):  # ą i \n w JSON nie ukryją tekstu
            variants.append(norm(" ".join(s for d in load_json_docs(raw) for s in json_strings(d))))
        hits: dict[str, int | None] = {}
        for text in variants:
            for src, frag in find(text, windows, needles).items():
                if src not in hits:
                    hits[src] = line_of(raw, frag)
        if hits:
            leaks[rel] = hits
    return leaks, binary


def redact_json(path: Path, windows, needles) -> int:
    """Raport ewaluacji: napis zawierający tekst MC → znacznik REDACTED (liczby i identyfikatory zostają)."""
    count = 0

    def walk(o):
        nonlocal count
        if isinstance(o, str):
            if find(norm(o), windows, needles):
                count += 1
                return REDACTED
            return o
        if isinstance(o, list):
            return [walk(v) for v in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o

    doc = walk(json.loads(path.read_text(encoding="utf-8")))
    if count:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def is_eval_report(rel: str) -> bool:
    return (rel.endswith(".json") and Path(rel).name.startswith("eval_")
            and rel.startswith(("docs/eval/", ".claude/skills/kompas-ewaluacja/references/")))


def dead_links(dest: Path) -> list[str]:
    """Linki w .md, których cel jest w repozytorium prywatnym, ale nie w kopii (wycięty katalog albo plik)."""
    out = []
    for md in sorted(dest.rglob("*.md")):
        if ".git" in md.relative_to(dest).parts:
            continue
        text = md.read_text(encoding="utf-8")
        for m in MD_LINK.finditer(text):
            target = m.group(1)
            if re.match(r"^[a-z]+:", target):
                continue
            rel_md = md.relative_to(dest)
            in_copy = (md.parent / target).resolve()
            in_private = (ROOT / rel_md.parent / target).resolve()
            if not in_copy.exists() and in_private.exists():
                out.append(f"{rel_md.as_posix()}:{text.count(chr(10), 0, m.start()) + 1} → {target}")
    return out


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def prepare(dest: Path) -> str | None:
    """Czyści katalog docelowy z poprzedniego eksportu (zostawia .git). Zwraca komunikat błędu albo None."""
    if ROOT in dest.parents or dest == ROOT:
        return "katalog docelowy musi być poza repozytorium."
    if not dest.exists():
        dest.mkdir(parents=True)
        return None
    content = [p for p in dest.iterdir() if p.name != ".git"]
    if content and not (dest / MARKER).exists():
        return f"{dest} zawiera pliki, ale nie pochodzi z eksportu (brak {MARKER}) – podaj pusty katalog albo klon pustego repozytorium."
    for p in content:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dest", help="katalog docelowy kopii (poza repozytorium)")
    a = ap.parse_args()
    if not (DATA / "competency_model.json").exists():
        print("BŁĄD: brak deploy/processed – odciski tekstów MC liczę z lokalnych danych.", file=sys.stderr)
        return 2
    dest = Path(a.dest).resolve()
    err = prepare(dest)
    if err:
        print(f"BŁĄD: {err}", file=sys.stderr)
        return 2
    copied = skipped = 0
    for rel in tracked_files():
        if rel.startswith(EXCLUDE_PREFIXES) or rel in EXCLUDE_FILES or Path(rel).name in EXCLUDE_NAMES:
            skipped += 1
            continue
        src = ROOT / rel
        if not src.exists():
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
        copied += 1
    (dest / MARKER).write_text("Kopia publiczna generowana przez scripts/export_public.py z prywatnego repozytorium "
                               "zespołu (bez materiałów i danych Ministerstwa Cyfryzacji).\n", encoding="utf-8")
    windows, needles = fingerprints()
    redacted = {rel: n for rel in tracked_files() if is_eval_report(rel) and (dest / rel).exists()
                and (n := redact_json(dest / rel, windows, needles))}
    leaks, binary = scan(dest, windows, needles)
    print(f"Skopiowano {copied} plików do {dest} (pominięto {skipped}: katalogi {', '.join(EXCLUDE_PREFIXES)} "
          f"i {len(EXCLUDE_FILES)} pliki spoza publicznej kopii: notatki zespołu, test-run i testy na OSP Partnera).")
    for rel, n in redacted.items():
        print(f"Raport ewaluacji {rel}: zastąpiono {n} napisów z tekstem MC znacznikiem.")
    if binary:
        print(f"Pliki binarne poza skanem (przejrzyj ręcznie): {', '.join(binary)}")
    links = dead_links(dest)
    if links:
        print(f"Martwe linki w kopii (cel wycięty) – {len(links)}:")
        for item in links:
            print(f"  {item}")
    if not leaks:
        print("Skan: brak tekstów MC i kluczy w kopii.")
        return 0
    print(f"Skan: teksty MC albo klucze w {len(leaks)} plikach – usuń je albo zastąp przykładami przed publikacją:")
    for rel, hits in leaks.items():
        shown = sorted(hits.items(), key=lambda kv: (kv[1] is None, kv[1] or 0))[:4]
        print(f"  {rel} ({len(hits)}): " + "; ".join(f"l.{ln or '?'} {src}" for src, ln in shown))
    return 1


if __name__ == "__main__":
    sys.exit(main())
