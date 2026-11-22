"""Źródła bazy wiedzy wgrywane przez administratora (rola HR): tekst → jednostki z cytowaniem → indeks asystenta.

Pkt 5 treści zadania: asystent korzysta ze „wskazanej bazy wiedzy”. Bazę z materiałów MC buduje `build_data.py`;
tu urząd dopisuje własne dokumenty (np. zarządzenie dyrektora generalnego o harmonogramie ocen, wytyczne kadr).

- Formaty: PDF (pypdf, BSD-3), DOCX (zipfile + XML, bez zależności), TXT, MD. Skany bez warstwy tekstu – odmowa.
- Podział: jeśli tekst ma co najmniej 3 jednostki „§ N.” albo „Art. N.”, jednostką jest paragraf/artykuł
  (cytat „§ 3 – <tytuł>”); w innym razie fragmenty do ok. 1200 znaków na granicach akapitów (cytat z numerem strony).
- Dane osobowe: privacy_shield maskuje PESEL, e-maile, telefony, adresy i imiona z nazwiskami przed zapisem;
  administrator widzi liczbę zamian. Oryginał pliku nie jest przechowywany.
- Wstrzykiwanie poleceń: znaczniki <zrodlo> w tekście są neutralizowane (nie da się podrobić identyfikatora źródła),
  a prompt asystenta traktuje treść źródeł jako dane.
"""
from __future__ import annotations

import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

from .skills import privacy_shield

ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}
MAX_CHARS = 400_000          # ok. 200 stron tekstu
MAX_UNITS = 400
MAX_SOURCES_PER_SESSION = 10
TARGET_CHARS = 1200
DOC_TYPES = {"wewnetrzne": "akt wewnętrzny urzędu", "wytyczne": "wytyczne / instrukcja", "inne": "inny dokument"}
PROCESS_SCOPES = {"oba": ["periodic", "first"], "okresowa": ["periodic"], "pierwsza": ["first"]}

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_LEGAL_RX = re.compile(r"(?m)^\s*(§\s*\d+[a-z]?|Art\.\s*\d+[a-z]?)\.?(?=\s)")


class UploadError(ValueError):
    """Komunikat dla administratora (zły format, pusty plik, skan bez tekstu)."""


def slugify(text: str, limit: int = 40) -> str:
    s = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:limit].strip("_") or "dokument"


# ------------------------------------------------------------------ ekstrakcja tekstu
def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise UploadError("To nie jest poprawny plik .docx.") from exc
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for el in p.iter():
            if el.tag == f"{_W}t" and el.text:
                parts.append(el.text)
            elif el.tag in (f"{_W}tab",):
                parts.append(" ")
            elif el.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            paras.append(line)
    return "\n".join(paras)


def _pdf_pages(data: bytes) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - zależność w requirements.txt
        raise UploadError("Brak biblioteki pypdf – wgraj dokument jako .docx albo .txt.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # pypdf zgłasza różne wyjątki dla uszkodzonych plików
        raise UploadError("Nie udało się odczytać pliku PDF.") from exc


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    """Lista (numer strony albo None, tekst)."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise UploadError("Obsługiwane formaty: PDF, DOCX, TXT, MD.")
    if ext == ".pdf":
        pages = [(i + 1, t) for i, t in enumerate(_pdf_pages(data))]
    elif ext == ".docx":
        pages = [(None, _docx_text(data))]
    else:
        for enc in ("utf-8-sig", "cp1250"):
            try:
                pages = [(None, data.decode(enc))]
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UploadError("Nie rozpoznano kodowania pliku tekstowego (użyj UTF-8).")
    if sum(len(t.strip()) for _, t in pages) < 200:
        raise UploadError("Plik nie zawiera tekstu do odczytania (skan bez warstwy tekstowej albo pusty dokument).")
    return pages


# ------------------------------------------------------------------ podział na jednostki
def _clean(text: str) -> str:
    text = text.replace("\r", "").replace("­", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)        # dzielenie wyrazów na końcu linii (PDF)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"</?\s*zr[oó]d", "‹zrod", text, flags=re.I)  # nie da się podrobić bloku <zrodlo id=…>
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _paragraph_units(pages: list[tuple[int | None, str]]) -> list[tuple[str, str]]:
    units: list[tuple[str, str]] = []
    buf, buf_pages = "", []

    def flush():
        nonlocal buf, buf_pages
        if buf.strip():
            ps = sorted({p for p in buf_pages if p})
            where = (f"s. {ps[0]}" if len(ps) == 1 else f"s. {ps[0]}–{ps[-1]}") if ps else ""
            units.append((f"fragment {len(units) + 1}" + (f", {where}" if where else ""), buf.strip()))
        buf, buf_pages = "", []

    for page, text in pages:
        for para in re.split(r"\n\s*\n|\n(?=[A-ZĄĆĘŁŃÓŚŹŻ0-9•\-–])", _clean(text)):
            para = " ".join(para.split())
            if not para:
                continue
            if len(buf) + len(para) > TARGET_CHARS and buf:
                flush()
            while len(para) > TARGET_CHARS * 1.5:  # bardzo długi akapit: tniemy na zdaniach
                cut = para.rfind(". ", 0, TARGET_CHARS) + 1 or TARGET_CHARS
                buf += (" " if buf else "") + para[:cut]
                buf_pages.append(page)
                flush()
                para = para[cut:].strip()
            buf += (" " if buf else "") + para
            buf_pages.append(page)
    flush()
    return units


def _legal_units(text: str) -> list[tuple[str, str]] | None:
    marks = list(_LEGAL_RX.finditer(text))
    if len(marks) < 3:
        return None
    units = []
    preamble = text[: marks[0].start()].strip()
    if len(preamble) > 30:
        units.append(("wstęp", " ".join(preamble.split())))
    for i, m in enumerate(marks):
        body = text[m.start(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        label = re.sub(r"\s+", " ", m.group(1)).replace("Art.", "art.").replace("§", "§ ").replace("  ", " ").strip()
        units.append((label, " ".join(body.split())))
    return units


def build_source(*, filename: str, data: bytes, title: str, doc_type: str, scope: str, added_by: str,
                 existing_ids: set[str]) -> dict:
    """Plik → źródło z jednostkami w formacie kb_chunks (kontrakt C1) + raport maskowania."""
    title = " ".join((title or "").split())[:160]
    if len(title) < 3:
        raise UploadError("Podaj tytuł dokumentu (np. „Zarządzenie nr 12 Dyrektora Generalnego w sprawie ocen”).")
    if doc_type not in DOC_TYPES:
        raise UploadError("Wybierz rodzaj dokumentu.")
    if scope not in PROCESS_SCOPES:
        raise UploadError("Wybierz, której oceny dotyczy dokument.")
    pages = extract_pages(filename, data)
    total = sum(len(t) for _, t in pages)
    if total > MAX_CHARS:
        raise UploadError(f"Dokument jest za długi ({total // 1000} tys. znaków, limit {MAX_CHARS // 1000} tys.).")
    full = _clean("\n".join(t for _, t in pages))
    raw_units = _legal_units(full) or _paragraph_units(pages)
    if len(raw_units) > MAX_UNITS:
        raise UploadError(f"Dokument dzieli się na {len(raw_units)} jednostek (limit {MAX_UNITS}).")

    base = "wlasne_" + slugify(title, 32)
    source_id, n = base, 2
    while source_id in existing_ids:
        source_id, n = f"{base}_{n}", n + 1

    masked_counts: dict[str, int] = {}
    chunks, used = [], set()
    for label, text in raw_units:
        res = privacy_shield.mask(text, privacy_shield.ShieldContext())
        for k, v in res.counts.items():
            key = "osoba" if k.startswith("Osoba") else k
            masked_counts[key] = masked_counts.get(key, 0) + v
        suffix = slugify(label.replace("§", "par").replace("art.", "art"), 24)
        cid, i = f"{source_id}:{suffix}", 2
        while cid in used:
            cid, i = f"{source_id}:{suffix}_{i}", i + 1
        used.add(cid)
        chunks.append({
            "id": cid, "source_id": source_id, "doc_type": "wlasne", "title": title, "unit": label,
            "citation": f"{label} – {title}", "heading_path": [title], "page_from": None, "page_to": None,
            "process": PROCESS_SCOPES[scope], "text": res.text, "source_file": filename[-120:],
        })
    return {"source_id": source_id, "title": title, "doc_type": doc_type, "doc_type_label": DOC_TYPES[doc_type],
            "scope": scope, "filename": filename[-120:], "chars": total, "units": len(chunks),
            "masked": masked_counts, "added_by": added_by,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "chunks": chunks}
