#!/usr/bin/env python
"""Kompas Kompetencji - deterministyczna budowa danych z materialow Partnera (MC).

Uzycie (repo rozwiazania):
    python .claude/skills/kompas-dane-i-zrodla/scripts/build_data.py --input materialy --output data/processed

Wejscie: katalog z materialami Partnera (pliki szukane rekurencyjnie wzorcami nazw).
Wyjscie (kontrakt C1): competency_model.json, annex1_criteria.json, forms/*.json,
kb/kb_chunks.jsonl, kb/sources.json, osp/<slug>.json, build_report.json.

Zaleznosci: tylko biblioteka standardowa Pythona (>=3.10) + program `pdftotext` (poppler).
Dwa uruchomienia na tych samych wejsciach daja identyczne pliki (brak znacznikow czasu).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILLS_DIR = SKILL_DIR.parent
DEFAULT_USTAWA = SKILL_DIR / "assets" / "ustawa_sc" / "ustawa_o_sluzbie_cywilnej.txt"
OSP_PARSER_DIR = SKILLS_DIR / "kompas-analiza-osp" / "scripts"

EXPECTED_COMPETENCIES = 14
EXPECTED_INDICATORS = 49
EXPECTED_LEVELS = 5

# Nazwy kryteriow w brzmieniu zalacznika nr 1 do rozp. PRM z 4.04.2016 (Dz. U. poz. 470)
# zapisane wielka litera tylko na poczatku (jak w arkuszach B i C). Kolejnosc = zalacznik nr 1.
CANONICAL_CRITERIA = [
    "Komunikacja",
    "Kreatywność",
    "Negocjowanie",
    "Organizacja pracy i orientacja na osiąganie celów",
    "Orientacja na klienta/interesanta",
    "Podejmowanie decyzji i odpowiedzialność",
    "Radzenie sobie w sytuacjach kryzysowych",
    "Rzetelność",
    "Myślenie analityczne",
    "Wykorzystywanie wiedzy i doskonalenie zawodowe",
    "Współpraca",
    "Wystąpienia publiczne",
    "Zarządzanie ludźmi",
    "Zarządzanie strategiczne",
]

SCALE = [
    (1, "znacznie_ponizej", "Znacznie poniżej oczekiwań"),
    (2, "ponizej", "Poniżej oczekiwań"),
    (3, "na_poziomie", "Na poziomie oczekiwań"),
    (4, "powyzej", "Powyżej oczekiwań"),
    (5, "znacznie_powyzej", "Znacznie powyżej oczekiwań"),
]

# Wzorce nazw plikow wejsciowych (dopasowanie do nazwy "zlozonej": bez polskich znakow, male litery).
INPUT_PATTERNS = {
    "model_xlsx": r"model.?kompetencji.*\.xlsx$",
    "form_b_docx": r"arkusz\W+oceny\W+b\b.*\.docx$",
    "form_c_docx": r"arkusz\W+oceny\W+c\b.*\.docx$",
    "form_first_docx": r"arkusz\W+pierwszej\W+oceny.*\.docx$",
    "rozp2016_pdf": r"rozporzadzenie.*ocen\w*\W+okresow.*2016.*\.pdf$",
    "rozp2015_pdf": r"rozporzadzenie.*pierwszej\W+ocen.*2015.*\.pdf$",
    "poradnik_okresowa_pdf": r"poradnik.*ocen\w*\W+okresow.*\.pdf$",
    "poradnik_pierwsza_pdf": r"pierwsza\W+ocena.*poradnik.*\.pdf$",
    "osp_zip": r"osp.*\.zip$",
}

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class BuildError(RuntimeError):
    pass


# --------------------------------------------------------------------------- utils
def fold(s: str) -> str:
    """Male litery bez polskich znakow (do dopasowan, nie do tresci)."""
    s = s.replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(s)).strip("_")


_WS_RE = re.compile(r"[\s   ]+")


def norm_ws(s: str) -> str:
    """Laczy lamania wierszy i wielokrotne spacje; slow nie zmienia."""
    return _WS_RE.sub(" ", s or "").strip()


def norm_cmp(s: str) -> str:
    """Normalizacja do porownan (biale znaki, rodzaje myslnikow, spacja po ukosniku)."""
    s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("‐", "-")
    s = norm_ws(s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)
    return s.strip(" .").lower()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name


class Report:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.inputs: dict = {}
        self.counts: dict = {}
        self.checks: dict = {}

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)
        print("OSTRZEZENIE:", msg, file=sys.stderr)


# --------------------------------------------------------------------------- input discovery
def find_inputs(root: Path, report: Report) -> dict:
    files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix())
    found: dict = {}
    for key, pattern in INPUT_PATTERNS.items():
        rx = re.compile(pattern)
        cands = [p for p in files if rx.search(fold(p.name))]
        # usuwamy duplikaty o tej samej tresci
        uniq, seen = [], set()
        for p in cands:
            h = sha256_file(p)
            if h not in seen:
                seen.add(h)
                uniq.append(p)
        found[key] = uniq
    # dwa PDF rozp. 2016: pelny akt i wyciag z zalacznikiem nr 1 (3 strony)
    r16 = found.get("rozp2016_pdf", [])
    found["annex1_pdf"] = []
    if r16:
        pages = {p: pdf_page_count(p) for p in r16}
        r16_sorted = sorted(r16, key=lambda p: (-pages[p], p.as_posix()))
        found["rozp2016_pdf"] = [r16_sorted[0]]
        short = [p for p in r16_sorted[1:] if pages[p] <= 5]
        found["annex1_pdf"] = short[:1] or [r16_sorted[0]]
    out = {}
    for key, lst in found.items():
        if not lst:
            out[key] = None
            report.warn(f"Nie znaleziono pliku wejsciowego '{key}' (wzorzec {INPUT_PATTERNS.get(key, 'rozp2016')}).")
            continue
        if len(lst) > 1:
            report.warn(f"Wiele kandydatow dla '{key}': {[rel(p, root) for p in lst]} - uzyto pierwszego.")
        out[key] = lst[0]
        report.inputs[key] = {"file": rel(lst[0], root), "sha256": sha256_file(lst[0])}
    return out


# --------------------------------------------------------------------------- PDF
_PDFTOTEXT: str | None = None


def pdftotext_bin() -> str:
    global _PDFTOTEXT
    if _PDFTOTEXT is None:
        env = os.environ.get("PDFTOTEXT")
        exe = (env if env and Path(env).is_file() else None) if env else shutil.which("pdftotext")
        if not exe:
            raise BuildError(
                "Brak programu 'pdftotext' (poppler). Zainstaluj poppler-utils "
                "(Linux: apt install poppler-utils; macOS: brew install poppler; Windows: Git for Windows "
                "zawiera pdftotext w usr/bin) albo wskaz sciezke w zmiennej PDFTOTEXT."
            )
        _PDFTOTEXT = exe
    return _PDFTOTEXT


def pdf_pages(path: Path, layout: bool = False) -> list[str]:
    cmd = [pdftotext_bin(), "-enc", "UTF-8"]
    if layout:
        cmd.append("-layout")
    cmd += [str(path), "-"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        raise BuildError(f"pdftotext zwrocil {res.returncode} dla {path}: {res.stderr.decode('utf-8', 'replace')}")
    text = res.stdout.decode("utf-8", "replace").replace("﻿", "").replace("\r\n", "\n")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def pdf_page_count(path: Path) -> int:
    return len(pdf_pages(path))


# --------------------------------------------------------------------------- XLSX
def _col_row(ref: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return m.group(1), int(m.group(2))


def read_xlsx(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{{{NS_MAIN}}}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {}
        for r in rels.findall(f"{{{NS_PKG_REL}}}Relationship"):
            t = r.get("Target")
            t = t[1:] if t.startswith("/") else "xl/" + t
            relmap[r.get("Id")] = t
        sheets = []
        for s in wb.iter(f"{{{NS_MAIN}}}sheet"):
            target = relmap[s.get(f"{{{NS_REL}}}id")]
            root = ET.fromstring(z.read(target))
            cells: dict[str, str] = {}
            for c in root.iter(f"{{{NS_MAIN}}}c"):
                t = c.get("t")
                v = c.find(f"{{{NS_MAIN}}}v")
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{NS_MAIN}}}t"))
                else:
                    val = v.text if v is not None else None
                if val is not None and str(val).strip() != "":
                    cells[c.get("r")] = val
            sheets.append({"name": s.get("name"), "cells": cells})
    return sheets


def _rows(cells: dict) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for ref, val in cells.items():
        col, row = _col_row(ref)
        rows.setdefault(row, {})[col] = val
    return rows


def canonical_name(raw: str, report: Report) -> str:
    key = norm_cmp(fold(raw))
    for name in CANONICAL_CRITERIA:
        if norm_cmp(fold(name)) == key:
            return name
    report.warn(f"Nazwa kompetencji '{raw}' nie odpowiada zadnemu kryterium z zalacznika nr 1 - uzyto zapisu zdaniowego.")
    s = norm_ws(raw).lower()
    return s[:1].upper() + s[1:]


def build_competency_model(xlsx: Path, mat_root: Path, report: Report, strict: bool = True) -> dict:
    sheets = read_xlsx(xlsx)
    summary = None
    for s in sheets:
        a1 = s["cells"].get("A1", "")
        if "MODEL KOMPETENCJI" in a1.upper() or fold(s["name"]) == "model kompetencji":
            summary = s
            break
    if summary is None:
        raise BuildError("Nie znaleziono arkusza zbiorczego 'Model kompetencji'.")
    srows = _rows(summary["cells"])
    header_row = next((r for r in sorted(srows) if norm_ws(srows[r].get("A", "")) == "Lp."), None)
    if header_row is None:
        raise BuildError("Arkusz zbiorczy: brak wiersza naglowka 'Lp.'.")
    instructions = [norm_ws(srows[r]["A"]) for r in sorted(srows) if 4 <= r < header_row and srows[r].get("A")]
    summary_line = norm_ws(srows.get(3, {}).get("A", ""))
    table = []
    for r in sorted(srows):
        if r <= header_row or not srows[r].get("B"):
            continue
        table.append({
            "lp": int(float(srows[r].get("A", "0"))),
            "name_in_model": norm_ws(srows[r]["B"]),
            "declared_indicators": int(float(srows[r].get("C", "0"))),
        })
    by_key = {norm_cmp(fold(t["name_in_model"])): t for t in table}

    competencies = []
    level_labels_seen = set()
    for s in sheets:
        if s is summary:
            continue
        rows = _rows(s["cells"])
        full_name = norm_ws(rows.get(1, {}).get("A", ""))
        hdr = rows.get(3, {})
        labels = tuple(norm_ws(hdr.get(c, "")) for c in "BCDEF")
        level_labels_seen.add(labels)
        if labels != tuple(x[2] for x in SCALE):
            report.warn(f"Arkusz '{s['name']}': naglowki poziomow {labels} rozne od oczekiwanych.")
        indicators = []
        r = 4
        while r in rows and rows[r].get("A"):
            row = rows[r]
            indicators.append({
                "text": norm_ws(row["A"]),
                "levels": {str(i + 1): norm_ws(row.get(c, "")) for i, c in enumerate("BCDEF")},
            })
            r += 1
        name = canonical_name(full_name, report)
        cid = slugify(name)
        for i, ind in enumerate(indicators, 1):
            ind["id"] = f"{cid}.{i}"
            for lvl, txt in ind["levels"].items():
                if not txt:
                    report.warn(f"{cid}.{i}: pusty opis poziomu {lvl}.")
        summary_entry = by_key.get(norm_cmp(fold(full_name)))
        if summary_entry is None:
            report.warn(f"Kompetencja '{full_name}' (arkusz '{s['name']}') nie wystepuje w arkuszu zbiorczym.")
        elif summary_entry["declared_indicators"] != len(indicators):
            raise BuildError(
                f"'{full_name}': arkusz zbiorczy deklaruje {summary_entry['declared_indicators']} wskaznikow, "
                f"arkusz kompetencji ma {len(indicators)}."
            )
        competencies.append({
            "id": cid,
            "name": name,
            "name_in_model": full_name,
            "sheet": s["name"],
            "lp": summary_entry["lp"] if summary_entry else None,
            "indicators": [{"id": i["id"], "text": i["text"], "levels": i["levels"]} for i in indicators],
        })
    competencies.sort(key=lambda c: (c["lp"] is None, c["lp"] or 0, c["id"]))

    n_comp = len(competencies)
    n_ind = sum(len(c["indicators"]) for c in competencies)
    n_lvl = len(SCALE) if len(level_labels_seen) == 1 else -1
    report.counts.update({"competencies": n_comp, "indicators": n_ind, "levels": n_lvl})
    m = re.match(r"(\d+)\D+(\d+)\D+(\d+)", summary_line)
    if m and (int(m.group(1)), int(m.group(2)), int(m.group(3))) != (n_comp, n_ind, n_lvl):
        raise BuildError(f"Naglowek arkusza zbiorczego '{summary_line}' niezgodny z odczytem: {n_comp}/{n_ind}/{n_lvl}.")
    expected = (EXPECTED_COMPETENCIES, EXPECTED_INDICATORS, EXPECTED_LEVELS)
    if (n_comp, n_ind, n_lvl) != expected:
        msg = f"Model kompetencji: {n_comp} kompetencji / {n_ind} wskaznikow / {n_lvl} poziomow, oczekiwano {expected}."
        if strict:
            raise BuildError(msg + " (uzyj --allow-model-change, jesli Partner zmienil model)")
        report.warn(msg)
    ids = [c["id"] for c in competencies]
    if len(set(ids)) != len(ids):
        raise BuildError(f"Zdublowane id kompetencji: {ids}")
    return {
        "source": {"file": rel(xlsx, mat_root), "sha256": sha256_file(xlsx)},
        "summary_line": summary_line,
        "scale": [{"level": lvl, "key": key, "label": label} for lvl, key, label in SCALE],
        "instructions": instructions,
        "competencies": competencies,
    }


# --------------------------------------------------------------------------- DOCX
class Numbering:
    """Minimalny resolver numeracji Worda (numbering.xml) - potrzebny do dokladnych przypisow."""

    BULLET = "–"

    def __init__(self, z: zipfile.ZipFile) -> None:
        self.fmt: dict[tuple[str, str], tuple[str, str]] = {}
        self.counters: dict[tuple[str, str], int] = {}
        if "word/numbering.xml" not in z.namelist():
            return
        root = ET.fromstring(z.read("word/numbering.xml"))
        abstract = {}
        for a in root.findall(W + "abstractNum"):
            lv = {}
            for l in a.findall(W + "lvl"):
                nf = l.find(W + "numFmt")
                lt = l.find(W + "lvlText")
                lv[l.get(W + "ilvl")] = (nf.get(W + "val") if nf is not None else "decimal",
                                         lt.get(W + "val") if lt is not None else "%1.")
            abstract[a.get(W + "abstractNumId")] = lv
        for n in root.findall(W + "num"):
            aid = n.find(W + "abstractNumId").get(W + "val")
            for ilvl, v in abstract.get(aid, {}).items():
                self.fmt[(n.get(W + "numId"), ilvl)] = v

    def label(self, p) -> str:
        ppr = p.find(W + "pPr")
        numpr = ppr.find(W + "numPr") if ppr is not None else None
        if numpr is None:
            return ""
        nid = numpr.find(W + "numId")
        il = numpr.find(W + "ilvl")
        key = (nid.get(W + "val") if nid is not None else "0", il.get(W + "val") if il is not None else "0")
        if key[0] == "0" or key not in self.fmt:
            return ""
        fmt, text = self.fmt[key]
        self.counters[key] = self.counters.get(key, 0) + 1
        n = self.counters[key]
        if fmt == "bullet":
            return self.BULLET + " "
        if fmt == "lowerLetter":
            val = chr(ord("a") + n - 1)
        elif fmt == "upperRoman":
            val = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][n - 1] if n <= 10 else str(n)
        else:
            val = str(n)
        return text.replace("%1", val).replace("%2", val) + " "


def _ptext(p, with_refs: bool = True) -> tuple[str, list[int]]:
    out, refs = [], []
    for el in p.iter():
        if el.tag == W + "t":
            out.append(el.text or "")
        elif el.tag in (W + "tab",):
            out.append(" ")
        elif el.tag in (W + "br", W + "cr"):
            out.append(" ")
        elif el.tag == W + "footnoteReference":
            fid = int(el.get(W + "id"))
            refs.append(fid)
            if with_refs:
                out.append(f"[^{fid}]")
    return "".join(out), refs


def read_footnotes(z: zipfile.ZipFile) -> dict[int, str]:
    if "word/footnotes.xml" not in z.namelist():
        return {}
    root = ET.fromstring(z.read("word/footnotes.xml"))
    numbering = Numbering(z)
    notes = {}
    for f in root.findall(W + "footnote"):
        if f.get(W + "type") in ("separator", "continuationSeparator", "continuationNotice"):
            continue
        fid = int(f.get(W + "id"))
        paras = []
        for i, p in enumerate(f.findall(W + "p")):
            txt, _ = _ptext(p, with_refs=False)
            txt = norm_ws(txt)
            if i == 0:
                txt = re.sub(r"^\)\s*", "", txt)  # znak ")" po numerze przypisu
            lab = numbering.label(p)
            if txt:
                paras.append((lab + txt).strip())
        notes[fid] = "\n".join(paras)
    return notes


def _iter_blocks(body):
    for ch in body:
        if ch.tag in (W + "p", W + "tbl"):
            yield ch
        elif ch.tag == W + "sdt":
            content = ch.find(W + "sdtContent")
            if content is not None:
                yield from _iter_blocks(content)


def read_docx_blocks(z: zipfile.ZipFile) -> list[dict]:
    doc = ET.fromstring(z.read("word/document.xml"))
    blocks = []
    for el in _iter_blocks(doc.find(W + "body")):
        if el.tag == W + "p":
            txt, refs = _ptext(el)
            txt = norm_ws(txt)
            if txt:
                blocks.append({"type": "paragraph", "text": txt, "footnote_refs": refs})
        else:
            rows, refs = [], []
            for tr in el.findall(W + "tr"):
                cells = []
                for tc in tr.findall(W + "tc"):
                    parts = []
                    for p in tc.iter(W + "p"):
                        t, r = _ptext(p)
                        refs.extend(r)
                        t = norm_ws(t)
                        if t:
                            parts.append(t)
                    cells.append(" ".join(parts))
                rows.append(cells)
            blocks.append({"type": "table", "rows": rows, "footnote_refs": refs})
    return blocks


_REF_RE = re.compile(r"\[\^(\d+)\]\)?")


def strip_refs(s: str) -> str:
    return norm_ws(_REF_RE.sub("", s))


PART_RE = re.compile(r"^CZĘŚĆ\s+(I{1,3}|OGÓLNA)\b")


def _is_heading(text: str) -> bool:
    t = strip_refs(text)
    letters = [ch for ch in t if ch.isalpha()]
    return bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) > 0.9 and len(t) < 200


def _footnote_role(anchor: str) -> str | None:
    a = fold(anchor)
    rules = [
        ("czesci iii", "part3"), ("wniosek jest wypelniany", "part3"),
        ("pozytywna", "result_positive"), ("negatywna", "result_negative"),
        ("uzasadnienie", "justification"), ("wnioski dotyczace", "development_conclusions"),
        ("ocena laczna", "total_score"), ("nie dotyczy", "exam_not_applicable"),
        ("kryteria dodatkowe", "additional_criteria"), ("elementy oceny", "first_eval_elements"),
        ("ocena czastkowa", "partial_score"), ("od", "period_from"),
    ]
    for key, role in rules:
        if key == "od":
            if a.strip(" :") in ("od",):
                return role
            continue
        if key in a:
            return role
    if a.strip(" :") == "do":
        return "period_to"
    return None


def build_form(docx: Path, form_id: str, mat_root: Path, report: Report) -> dict:
    with zipfile.ZipFile(docx) as z:
        blocks = read_docx_blocks(z)
        notes = read_footnotes(z)
    title_lines, parts = [], []
    current_part = None
    current_section = None
    anchors: dict[int, dict] = {}

    def ensure_part(heading: str):
        nonlocal current_part, current_section
        pid = {"I": "part1", "II": "part2", "III": "part3", "OGÓLNA": "general"}.get(
            PART_RE.match(heading).group(1), slugify(heading))
        current_part = {"id": pid, "heading": heading, "notes": [], "sections": []}
        parts.append(current_part)
        current_section = None

    def new_section(heading: str):
        nonlocal current_section
        if current_part is None:
            ensure_part("CZĘŚĆ OGÓLNA")
        current_section = {"heading": strip_refs(heading), "footnote_refs": [], "fields": []}
        current_part["sections"].append(current_section)

    for b in blocks:
        part_name = current_part["id"] if current_part else None
        if b["type"] == "paragraph":
            text = b["text"]
            for fid in b["footnote_refs"]:
                anchors.setdefault(fid, {"part": part_name, "anchor": strip_refs(text)})
            if PART_RE.match(text):
                ensure_part(strip_refs(text))
                continue
            if current_part is None:
                title_lines.append(strip_refs(text))
                continue
            if _is_heading(text):
                new_section(text)
                current_section["footnote_refs"] = b["footnote_refs"]
            else:
                current_part["notes"].append({"text": strip_refs(text), "footnote_refs": b["footnote_refs"]})
            continue
        # tabela
        if current_part is None:
            ensure_part("CZĘŚĆ OGÓLNA")
        if current_section is None:
            new_section(current_part["heading"])
        for row in b["rows"]:
            for cell in row:
                for m in _REF_RE.finditer(cell):
                    anchors.setdefault(int(m.group(1)), {"part": current_part["id"], "anchor": strip_refs(cell)})
        current_section["fields"].append({"rows": [[strip_refs(c) for c in row] for row in b["rows"]],
                                          "footnote_refs": b["footnote_refs"]})
    # przypisy z numerami i kotwicami
    footnotes = []
    for fid in sorted(notes):
        a = anchors.get(fid, {})
        footnotes.append({
            "number": fid,
            "marker": f"{fid})",
            "text": notes[fid],
            "anchor": a.get("anchor"),
            "part": a.get("part"),
            "role": _footnote_role(a.get("anchor") or "") if a else None,
        })
    # role zalezne od pozycji: przypis w tytule arkusza = zakres stosowania arkusza
    for fn in footnotes:
        if fn["part"] is None and fn["anchor"] and fn["anchor"] in title_lines:
            fn["role"] = "applies_to"
    form = {
        "form": form_id,
        "source": {"file": rel(docx, mat_root), "sha256": sha256_file(docx)},
        "annex": next((t for t in title_lines if t.lower().startswith("załącznik")), None),
        "title_lines": title_lines,
        "parts": parts,
        "footnotes": footnotes,
    }
    form.update(extract_form_semantics(form, blocks, report))
    return form


def _points(cell: str) -> int | None:
    m = re.match(r"\s*(\d+)\s*punkt", cell)
    return int(m.group(1)) if m else None


def extract_form_semantics(form: dict, blocks: list[dict], report: Report) -> dict:
    """Kryteria obowiazkowe/elementy oceny, skala punktowa, przedzialy poziomu ogolnego."""
    out: dict = {"mandatory_criteria": [], "scale": [], "overall_levels": [], "additional_criteria_max": None}
    tables = [b["rows"] for b in blocks if b["type"] == "table"]
    # 1) kryteria obowiazkowe (Czesc I arkuszy B/C) albo elementy oceny (pierwsza ocena)
    for rows in tables:
        head = strip_refs(rows[0][0]) if rows and rows[0] else ""
        if fold(head).startswith("kryteria obowiazkowe") and len(rows[0]) == 2 and not any(
                _points(c) for r in rows for c in r):
            out["mandatory_criteria"] = [strip_refs(r[0]) for r in rows[1:] if r and strip_refs(r[0])]
            m = re.search(r"nie więcej niż (\d+)", strip_refs(rows[0][1]))
            if m:
                out["additional_criteria_max"] = int(m.group(1))
            break
    score_table = None
    for rows in tables:
        if any(_points(c) for r in rows for c in r):
            score_table = rows
            break
    if score_table:
        hdr_i = next(i for i, r in enumerate(score_table) if any(_points(c) for c in r))
        labels = score_table[hdr_i - 1]
        pts = score_table[hdr_i]
        for lab, pt in zip(labels[1:], pts[1:]):
            p = _points(pt)
            if p is None:
                continue
            key = next((k for _, k, l in SCALE if norm_cmp(l) == norm_cmp(lab)), slugify(lab))
            level = next((lv for lv, k, _ in SCALE if k == key), None)
            out["scale"].append({"level": level, "key": key, "label": strip_refs(lab), "points": p})
        if not out["mandatory_criteria"]:
            names = []
            for r in score_table[hdr_i + 1:]:
                n = strip_refs(r[0]) if r else ""
                if not n or len(r) < 3 or fold(n).startswith("ocena laczna"):
                    continue
                names.append(n)
            out["mandatory_criteria"] = names
    # 2) przedzialy ogolnego poziomu (tabela "PRZYZNANIE OCENY")
    for rows in tables:
        if rows and len(rows[0]) >= 3 and fold(rows[0][1]).startswith("liczba punktow"):
            for r in rows[1:]:
                if len(r) < 3:
                    continue
                m = re.match(r"(od|powyżej)\s+(\d+)\s+punkt\w*\s+do\s+(\d+)\s+punkt", strip_refs(r[1]))
                if not m:
                    continue
                label = strip_refs(r[2])
                key = next((k for _, k, l in SCALE if norm_cmp(l) == norm_cmp(label)), slugify(label))
                out["overall_levels"].append({
                    "min": int(m.group(2)), "min_inclusive": m.group(1) == "od", "max": int(m.group(3)),
                    "max_inclusive": True, "key": key, "label": label, "text": strip_refs(r[1]),
                })
    crit = []
    for name in out["mandatory_criteria"]:
        c = canonical_name(name, report)
        crit.append({"id": slugify(c), "name": c, "name_in_form": name})
    out["mandatory_criteria"] = crit
    out["criteria_kind"] = "first_eval_element" if form["form"] == "first_eval" else "mandatory"
    if not crit:
        report.warn(f"{form['form']}: nie odczytano kryteriow obowiazkowych.")
    return out


# --------------------------------------------------------------------------- main
def run(input_dir: Path, output_dir: Path, ustawa: Path | None, strict: bool) -> Report:
    report = Report()
    if not input_dir.is_dir():
        raise BuildError(f"Katalog wejsciowy nie istnieje: {input_dir}")
    pdftotext_bin()
    inputs = find_inputs(input_dir, report)
    output_dir.mkdir(parents=True, exist_ok=True)

    model = None
    if inputs.get("model_xlsx"):
        model = build_competency_model(inputs["model_xlsx"], input_dir, report, strict=strict)

    forms = {}
    for form_id, key in (("periodic_b", "form_b_docx"), ("periodic_c", "form_c_docx"), ("first_eval", "form_first_docx")):
        if inputs.get(key):
            forms[form_id] = build_form(inputs[key], form_id, input_dir, report)
            write_json(output_dir / "forms" / f"{form_id}.json", forms[form_id])
            report.counts[f"footnotes_{form_id}"] = len(forms[form_id]["footnotes"])

    if model is not None:
        for c in model["competencies"]:
            c["mandatory_in"] = [fid for fid, f in forms.items() if c["id"] in {m["id"] for m in f["mandatory_criteria"]}]
        write_json(output_dir / "competency_model.json", model)

    stage2(inputs, input_dir, output_dir, model, forms, ustawa, report)

    build = {
        "builder": "kompas-dane-i-zrodla/scripts/build_data.py",
        "inputs": report.inputs,
        "counts": report.counts,
        "checks": report.checks,
        "warnings": report.warnings,
    }
    write_json(output_dir / "build_report.json", build)
    return report


def stage2(inputs, input_dir, output_dir, model, forms, ustawa, report) -> None:
    """Zalacznik nr 1, baza wiedzy (KB), OSP."""
    annex1 = None
    if inputs.get("annex1_pdf"):
        annex1 = build_annex1(inputs["annex1_pdf"], input_dir, report, model)
        if model is not None:
            annex1["model_check"] = check_model_vs_annex1(model, annex1, report)
        write_json(output_dir / "annex1_criteria.json", annex1)
    if inputs.get("rozp2015_pdf") and "first_eval" in forms:
        try:
            a15 = build_annex1(inputs["rozp2015_pdf"], input_dir, report, model, start_rx=r"^ELEMENT OCENY\s+OPIS$",
                               stop_rx=r"Załącznik nr 2", title=ANNEX1_2015_TITLE, expected=5,
                               label="Zalacznik nr 1 rozp. 2015")
            forms["first_eval"]["element_descriptions"] = a15
            write_json(output_dir / "forms" / "first_eval.json", forms["first_eval"])
        except Exception as e:  # noqa: BLE001 - dodatek, nie przerywa budowy
            report.warn(f"Zalacznik nr 1 rozp. 2015: blad {type(e).__name__}: {e}")
    chunks, sources = build_kb(inputs, input_dir, model, forms, annex1, ustawa, report)
    kb_dir = output_dir / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    with open(kb_dir / "kb_chunks.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")
    write_json(kb_dir / "sources.json", sources)
    report.counts["kb_chunks"] = len(chunks)
    by_src: dict[str, int] = {}
    for ch in chunks:
        by_src[ch["source_id"] + "/" + ch["doc_type"]] = by_src.get(ch["source_id"] + "/" + ch["doc_type"], 0) + 1
    report.counts["kb_chunks_by_source"] = dict(sorted(by_src.items()))
    doubled = [c["id"] for c in chunks if has_doubled_chars(c["text"])]
    report.checks["kb_doubled_char_chunks"] = doubled
    if doubled:
        report.warn(f"KB: {len(doubled)} fragmentow z podwojonymi znakami: {doubled[:5]}")
    try:
        build_osp(inputs, input_dir, output_dir, report)
    except Exception as e:  # noqa: BLE001 - OSP jest opcjonalne, nie przerywa budowy
        report.warn(f"OSP: nieoczekiwany blad {type(e).__name__}: {e} - pominieto osp/*.json.")


# --------------------------------------------------------------------------- PDF cleaning
_DOUBLED_TOKEN = re.compile(r"[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]{6,}")


def _is_doubled(tok: str) -> bool:
    return len(tok) >= 6 and len(tok) % 2 == 0 and tok[0::2] == tok[1::2]


def has_doubled_chars(text: str) -> bool:
    """Wykrywa artefakt ekstrakcji wzorow arkuszy: 'UUZZAASSAADDNNIIEENNIIEE'."""
    return any(_is_doubled(t) for t in _DOUBLED_TOKEN.findall(text))


_HEADER_LINE = re.compile(
    r"^(﻿?\s*Dziennik Ustaw|–\s*\d+\s*–|-\s*\d+\s*-|Poz\.\s*\d+|www\.rcl\.gov\.pl|Dokument podpisany przez.*"
    r"|DZIENNIK USTAW|RZECZYPOSPOLITEJ POLSKIEJ|Warszawa, dnia .*)$")


def pdf_lines(pages: list[str], drop_page_numbers: bool = False) -> list[tuple[int, str]]:
    """(numer strony 1.., linia) bez naglowkow Dz. U.; z laczeniem wyrazow przenoszonych z lacznikiem."""
    out: list[tuple[int, str]] = []
    for pno, page in enumerate(pages, 1):
        for raw in page.split("\n"):
            line = raw.replace("﻿", "").strip()
            if not line or _HEADER_LINE.match(line):
                continue
            if drop_page_numbers and re.fullmatch(r"\d{1,3}", line):
                continue
            if out and re.search(r"[a-ząćęłńóśźż]-$", out[-1][1]) and re.match(r"[a-ząćęłńóśźż]", line):
                out[-1] = (out[-1][0], out[-1][1][:-1] + line)
                continue
            out.append((pno, line))
    return out


def words(s: str) -> int:
    return len(s.split())


# --------------------------------------------------------------------------- regulations
SOURCE_META = {
    "rozp2016": {
        "doc_type": "rozporzadzenie",
        "title": "Rozporządzenie Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu "
                 "przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej "
                 "(Dz. U. poz. 470)",
        "cite": "rozporządzenia Prezesa Rady Ministrów z 4 kwietnia 2016 r. (Dz. U. poz. 470)",
        "short": "rozp. 2016 (oceny okresowe)",
        "process": ["periodic"],
        "url": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20160000470",
    },
    "rozp2015": {
        "doc_type": "rozporzadzenie",
        "title": "Rozporządzenie Prezesa Rady Ministrów z dnia 23 lipca 2015 r. w sprawie szczegółowych warunków "
                 "i sposobu dokonywania pierwszej oceny w służbie cywilnej (Dz. U. poz. 1144)",
        "cite": "rozporządzenia Prezesa Rady Ministrów z 23 lipca 2015 r. (Dz. U. poz. 1144)",
        "short": "rozp. 2015 (pierwsza ocena)",
        "process": ["first"],
        "url": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20150001144",
    },
    "poradnik_okresowa_2016": {
        "doc_type": "poradnik",
        "title": "Oceny okresowe w służbie cywilnej – poradnik, Kancelaria Prezesa Rady Ministrów, "
                 "Departament Służby Cywilnej, wrzesień 2016",
        "cite": "poradnika KPRM „Oceny okresowe w służbie cywilnej” (wrzesień 2016)",
        "short": "poradnik KPRM – oceny okresowe (2016)",
        "process": ["periodic"],
        "url": None,
    },
    "poradnik_pierwsza_2016": {
        "doc_type": "poradnik",
        "title": "Pierwsza ocena w służbie cywilnej – poradnik, Kancelaria Prezesa Rady Ministrów, "
                 "Departament Służby Cywilnej, wrzesień 2016",
        "cite": "poradnika KPRM „Pierwsza ocena w służbie cywilnej” (wrzesień 2016)",
        "short": "poradnik KPRM – pierwsza ocena (2016)",
        "process": ["first"],
        "url": None,
    },
    "model_kompetencji": {
        "doc_type": "model_kompetencji",
        "title": "Model kompetencji – służba cywilna (materiał Partnera: Ministerstwo Cyfryzacji, Model_kompetencji.xlsx)",
        "cite": "modelu kompetencji MC (Model_kompetencji.xlsx)",
        "short": "model kompetencji MC",
        "process": ["periodic", "first"],
        "url": None,
    },
}

_PAR_RE = re.compile(r"^§\s*(\d+[a-z]*)\.\s*(.*)$")
_UST_RE = re.compile(r"^(\d+[a-z]*)\.\s+(.*)$")


def _chunk(source_id, doc_type, title, unit, citation, heading_path, page_from, page_to, process, text,
           source_file, cid) -> dict:
    return {
        "id": cid, "source_id": source_id, "doc_type": doc_type, "title": title, "unit": unit,
        "citation": citation, "heading_path": heading_path, "page_from": page_from, "page_to": page_to,
        "process": process, "text": text, "source_file": source_file,
    }


def kb_regulation(pdf: Path, source_id: str, mat_root: Path, report: Report, long_words: int = 300) -> list[dict]:
    meta = SOURCE_META[source_id]
    pages = pdf_pages(pdf)
    doubled_pages = [i for i, p in enumerate(pages, 1) if has_doubled_chars(p)]
    report.checks[f"{source_id}_pages_with_doubled_chars"] = doubled_pages
    lines = pdf_lines(pages)
    # tresc normatywna: od "§ 1." do podpisu / pierwszego zalacznika
    start = next(i for i, (_, l) in enumerate(lines) if _PAR_RE.match(l))
    preamble = [l for _, l in lines[:start] if l.startswith("Na podstawie")]
    end = len(lines)
    footnotes = []
    for i in range(start, len(lines)):
        l = lines[i][1]
        if l.startswith("Prezes Rady Ministrów:") or re.match(r"^Załącznik", l):
            end = i
            # przypisy aktu tuz po podpisie
            for j in range(i + 1, len(lines)):
                lj = lines[j][1]
                if re.match(r"^Załącznik", lj):
                    break
                if re.match(r"^\d\)\s", lj):
                    footnotes.append(lines[j])
            break
    pars: list[dict] = []
    for pno, l in lines[start:end]:
        if has_doubled_chars(l):
            continue
        m = _PAR_RE.match(l)
        if m:
            pars.append({"num": m.group(1), "lines": [(pno, l)]})
        elif pars:
            pars[-1]["lines"].append((pno, l))
    sf = rel(pdf, mat_root)
    chunks = []
    if preamble:
        p0 = lines[0][0]
        chunks.append(_chunk(source_id, meta["doc_type"], meta["title"], "podstawa prawna",
                             f"podstawa prawna {meta['cite']}", [meta["short"], "podstawa prawna"], p0, p0,
                             meta["process"], norm_ws(" ".join(preamble)), sf, f"{source_id}:preambula"))
    for par in pars:
        num = par["num"]
        text = norm_ws(" ".join(l for _, l in par["lines"]))
        # podzial na ustepy
        usts: list[dict] = []
        first = _PAR_RE.match(par["lines"][0][1]).group(2)
        m1 = _UST_RE.match(first)
        if m1:
            usts.append({"num": m1.group(1), "lines": [(par["lines"][0][0], par["lines"][0][1])]})
            for pno, l in par["lines"][1:]:
                mu = _UST_RE.match(l)
                if mu and int(re.match(r"\d+", mu.group(1)).group(0)) == len(usts) + 1:
                    usts.append({"num": mu.group(1), "lines": [(pno, l)]})
                else:
                    usts[-1]["lines"].append((pno, l))
        if words(text) > long_words and len(usts) > 1:
            for u in usts:
                ut = norm_ws(" ".join(l for _, l in u["lines"]))
                if u is not usts[0]:
                    ut = f"§ {num}. {ut}"
                unit = f"§ {num} ust. {u['num']}"
                chunks.append(_chunk(source_id, meta["doc_type"], meta["title"], unit, f"{unit} {meta['cite']}",
                                     [meta["short"], f"§ {num}", f"ust. {u['num']}"], u["lines"][0][0],
                                     u["lines"][-1][0], meta["process"], ut, sf,
                                     f"{source_id}:par{num}:ust{u['num']}"))
        else:
            unit = f"§ {num}"
            chunks.append(_chunk(source_id, meta["doc_type"], meta["title"], unit, f"{unit} {meta['cite']}",
                                 [meta["short"], unit], par["lines"][0][0], par["lines"][-1][0], meta["process"],
                                 text, sf, f"{source_id}:par{num}"))
    for pno, l in footnotes:
        n = re.match(r"^(\d)\)", l).group(1)
        chunks.append(_chunk(source_id, meta["doc_type"], meta["title"], f"przypis {n})",
                             f"przypis {n}) do {meta['cite']}", [meta["short"], f"przypis {n})"], pno, pno,
                             meta["process"], norm_ws(l), sf, f"{source_id}:przypis{n}"))
    report.counts[f"{source_id}_paragraphs"] = len(pars)
    return chunks


# --------------------------------------------------------------------------- guides (poradniki KPRM)
_TOC_NUM = re.compile(r"(\d+(?:\.\d+)*\.)\s+(.+?)\s*[.…]{3,}\s*(\d+)")
_TOC_ANNEX = re.compile(r"(Załącznik nr \d+)\s*[–-]?\s*(.+?)\s*[.…]{3,}\s*(\d+)")


def parse_toc(pages: list[str]) -> tuple[int, list[dict]]:
    for idx, page in enumerate(pages[:6]):
        if "Spis treści" in page:
            flat = norm_ws(page.replace("Spis treści", " "))
            entries = []
            pos = 0
            rx = re.compile(_TOC_NUM.pattern + "|" + _TOC_ANNEX.pattern + r"|([A-ZŁŚŻ][^.…]{5,120}?\?)\s*[.…]{3,}\s*(\d+)")
            for m in rx.finditer(flat, pos):
                if m.group(1):
                    entries.append({"num": m.group(1).rstrip("."), "title": norm_ws(m.group(2)), "page": int(m.group(3))})
                elif m.group(4):
                    entries.append({"num": m.group(4), "title": norm_ws(m.group(5)), "page": int(m.group(6))})
                else:
                    entries.append({"num": None, "title": norm_ws(m.group(7)), "page": int(m.group(8))})
            return idx + 1, entries
    return 0, []


def kb_guide(pdf: Path, source_id: str, mat_root: Path, report: Report,
             min_words: int = 300, max_words: int = 1200) -> list[dict]:
    meta = SOURCE_META[source_id]
    pages = pdf_pages(pdf)
    toc_page, toc = parse_toc(pages)
    lines = [(p, l) for p, l in pdf_lines(pages, drop_page_numbers=True) if p > toc_page]
    # lokalizacja naglowkow z spisu tresci w tekscie (po kolei)
    heads = []
    cursor = 0
    for e in toc:
        key = fold(e["title"])[:25]
        found = None
        for i in range(cursor, len(lines)):
            lf = fold(lines[i][1])
            if e["num"] and e["num"].startswith("Załącznik"):
                ok = lf.startswith(fold(e["num"]))
            elif e["num"]:
                ok = lf.startswith(e["num"] + ". ") and lf[len(e["num"]) + 2:].startswith(key[: max(8, len(key) // 2)])
            else:
                ok = lf.startswith(key)
            if ok:
                found = i
                break
        if found is None:
            report.warn(f"{source_id}: nie znaleziono w tekscie naglowka ze spisu tresci: {e['num'] or ''} {e['title']}")
            continue
        heads.append((found, e))
        cursor = found + 1
    report.counts[f"{source_id}_toc_entries"] = len(toc)
    report.counts[f"{source_id}_headings_found"] = len(heads)
    # sekcje
    sections = []
    for k, (i, e) in enumerate(heads):
        j = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = [(p, l) for p, l in lines[i:j] if not has_doubled_chars(l)]
        num = e["num"]
        level = num.count(".") + 1 if num and num[0].isdigit() else (1 if num else 9)
        sections.append({"num": num, "title": e["title"], "level": level, "lines": body})
    # sciezki naglowkow
    stack: list[dict] = []
    for s in sections:
        while stack and stack[-1]["level"] >= s["level"]:
            stack.pop()
        label = f"{s['num']}. {s['title']}" if s["num"] and s["num"][0].isdigit() else (
            f"{s['num']} – {s['title']}" if s["num"] else s["title"])
        s["path"] = [x["label"] for x in stack] + [label]
        s["label"] = label
        s["top"] = (stack[0]["num"] if stack else s["num"]) or s["title"]
        stack.append(s)
    # grupowanie w chunki 300-1200 slow (bez przekraczania rozdzialu 1. poziomu)
    sf = rel(pdf, mat_root)
    def gwords(g):
        return sum(words(" ".join(l for _, l in x["lines"])) for x in g)

    groups: list[list[dict]] = []
    for s in sections:
        if groups and (gwords(groups[-1]) < 30 or (groups[-1][0]["top"] == s["top"] and gwords(groups[-1]) < min_words)):
            groups[-1].append(s)
        else:
            groups.append([s])
    # maly ogon rozdzialu dolaczamy do poprzedniej grupy z tego samego rozdzialu
    merged: list[list[dict]] = []
    for g in groups:
        if merged and gwords(g) < min_words and merged[-1][0]["top"] == g[0]["top"]:
            merged[-1].extend(g)
        else:
            merged.append(g)
    groups = merged
    chunks = []
    for g in groups:
        all_lines = [pl for s in g for pl in s["lines"]]
        parts: list[list[tuple[int, str]]] = [[]]
        for pl in all_lines:
            if words(" ".join(l for _, l in parts[-1])) >= max_words * 0.75 and words(" ".join(l for _, l in parts[-1] + [pl])) > max_words * 0.75:
                parts.append([])
            parts[-1].append(pl)
        if len(parts) > 1 and words(" ".join(l for _, l in parts[-1])) < min_words // 2:
            tail = parts.pop()
            parts[-1].extend(tail)
        nums = [s["num"] or s["title"] for s in g]
        span = nums[0] if len(nums) == 1 else f"{nums[0]}–{nums[-1]}"
        unit_base = span if str(nums[0]).startswith("Załącznik") else "rozdz. " + span
        for pi, part in enumerate(parts):
            if not part:
                continue
            unit = unit_base + (f" (cz. {pi + 1})" if len(parts) > 1 else "")
            pf, pt = part[0][0], part[-1][0]
            pages_txt = f"s. {pf}" if pf == pt else f"s. {pf}–{pt}"
            cid = f"{source_id}:{slugify(nums[0])}" + (f"-{slugify(nums[-1])}" if len(nums) > 1 else "") + (
                f":cz{pi + 1}" if len(parts) > 1 else "")
            chunks.append(_chunk(source_id, meta["doc_type"], meta["title"], unit,
                                 f"{meta['cite']}, {unit}, {pages_txt}", g[0]["path"], pf, pt, meta["process"],
                                 norm_ws(" ".join(l for _, l in part)), sf, cid))
    return chunks


# --------------------------------------------------------------------------- act (ustawa)
FIRST_ARTS = {"35", "36", "37", "38"}
PERIODIC_ARTS = {"71", "81", "82", "83", "86", "89"}


def kb_ustawa(txt: Path, report: Report, max_words: int = 1200) -> tuple[list[dict], dict | None]:
    meta_path = txt.with_name(txt.name.replace(".txt", ".meta.json"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    title = meta.get("title") or "Ustawa z dnia 21 listopada 2008 r. o służbie cywilnej"
    dz = meta.get("dz_u") or ""
    cite = "ustawy z dnia 21 listopada 2008 r. o służbie cywilnej" + (f" ({dz.split(' (')[0]})" if dz else "")
    raw = txt.read_text(encoding="utf-8").replace("\r\n", "\n")
    body_lines = [l for l in raw.split("\n") if not l.startswith("[przypis]")]
    text = "\n".join(body_lines)
    # tokenizacja: naglowki rozdzialow i artykuly moga byc w tej samej linii
    tok = re.compile(r"(?:(?<=\n)|(?<=^)|(?<=[.;:”)]\s))(Rozdział \d+[a-z]*\s+[^\n]*?(?=\s+Art\.\s|\n|$)|Art\.\s+(\d+[a-z]*)\.(?:\d{1,3}\))?\s)")
    pieces = []
    last = 0
    marks = list(tok.finditer(text))
    chapter = None
    arts = []
    for k, m in enumerate(marks):
        if m.group(0).startswith("Rozdział"):
            chapter = norm_ws(m.group(0))
            continue
        nxt = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        atext = norm_ws(text[m.start():nxt])
        atext = re.sub(r"^(Art\.\s+\d+[a-z]*\.)\d{1,3}\)", r"\1", atext)  # znacznik przypisu przy numerze
        arts.append({"num": m.group(2), "chapter": chapter, "text": atext})
    chunks = []
    total: dict[str, int] = {}
    for a in arts:
        total[a["num"]] = total.get(a["num"], 0) + 1
    dups = sorted((n for n, k in total.items() if k > 1), key=lambda n: (int(re.match(r"\d+", n).group(0)), n))
    if dups:
        report.warn(f"ustawa: artykuly w kilku wersjach w tekscie jednolitym (np. przed i po zmianie): "
                    f"{', '.join('art. ' + n for n in dups)} - zapisane osobno z sufiksem id ':vN' i adnotacja w 'unit'.")
    report.checks["ustawa_multi_version_articles"] = dups
    seen: dict[str, int] = {}
    for a in arts:
        num = a["num"]
        seen[num] = seen.get(num, 0) + 1
        vsuf = f":v{seen[num]}" if total[num] > 1 else ""
        vlab = f" (wersja {seen[num]} z {total[num]} w tekście jednolitym)" if total[num] > 1 else ""
        proc = ["first"] if num in FIRST_ARTS else (["periodic"] if num in PERIODIC_ARTS else ["periodic", "first"])
        hp = [x for x in (a["chapter"], f"Art. {num}") if x]
        if words(a["text"]) > max_words:
            # podzial na ustepy
            segs = re.split(r"\s(?=\d+[a-z]?\.\s+[A-ZŁŚŻŹĆ])", a["text"])
            buf, part = [], 1
            for sgm in segs + [None]:
                if sgm is None or (buf and words(" ".join(buf + [sgm])) > max_words):
                    unit = f"art. {num} (cz. {part}){vlab}"
                    chunks.append(_chunk("ustawa_sc", "ustawa", title, unit, f"art. {num} {cite}", hp,
                                         None, None, proc, (f"Art. {num}. (cz. {part}) " if part > 1 else "") + " ".join(buf),
                                         rel_ustawa(txt), f"ustawa_sc:art{num}{vsuf}:cz{part}"))
                    buf, part = [], part + 1
                if sgm is not None:
                    buf.append(sgm)
        else:
            unit = f"art. {num}{vlab}"
            chunks.append(_chunk("ustawa_sc", "ustawa", title, unit, f"art. {num} {cite}", hp, None, None, proc,
                                 a["text"], rel_ustawa(txt), f"ustawa_sc:art{num}{vsuf}"))
    report.counts["ustawa_articles"] = len(total)
    report.counts["ustawa_article_versions"] = len(arts)
    return chunks, meta


def kb_kprm_qa(qa_dir: Path, report: Report) -> tuple[list[dict], dict | None]:
    """Opcjonalne Q&A KPRM: assets/kprm_qa/*.json = lista {id, question, answer, process, url, accessed}."""
    files = sorted(f for f in qa_dir.glob("*.json") if not f.name.endswith(".meta.json")) if qa_dir.is_dir() else []
    metas = {}
    for f in files:
        mp = f.with_name(f.name[:-5] + ".meta.json")
        if mp.exists():
            try:
                metas[f.name] = json.loads(mp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                report.warn(f"kprm_qa: nieczytelny {mp.name}")
    if not files:
        report.warn("Brak zestawu pytan i odpowiedzi KPRM (assets/kprm_qa/*.json) - pkt 5 tresci zadania wymienia "
                    "'przygotowany zestaw pytan i odpowiedzi'; KB bez Q&A.")
        return [], None
    chunks, hashes = [], {}
    for f in files:
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            report.warn(f"kprm_qa: nie mozna wczytac {f.name}: {e}")
            continue
        if isinstance(items, dict):
            items = items.get("items", [])
        hashes[f.name] = sha256_file(f)
        for n, it in enumerate(items, 1):
            if not isinstance(it, dict) or not it.get("question") or not it.get("answer"):
                report.warn(f"kprm_qa: {f.name} pozycja {n} bez pytania/odpowiedzi - pominieta")
                continue
            mnum = re.search(r"(\d+)$", str(it.get("id") or ""))
            qid = mnum.group(1) if mnum else (str(it.get("id")) if it.get("id") else str(n))
            proc = it.get("process") or ["periodic", "first"]
            proc = [proc] if isinstance(proc, str) else proc
            src_txt = f" (źródło: {it['url']}, dostęp {it.get('accessed', '?')})" if it.get("url") else ""
            qa_title = metas.get(f.name, {}).get("title") or "Pytania i odpowiedzi – Oceny pracownicze (Serwis Służby Cywilnej, gov.pl)"
            chunks.append(_chunk("kprm_qa_oceny", "kprm_qa", qa_title,
                                 f"Q&A KPRM nr {qid}", f"Q&A KPRM nr {qid}{src_txt}", ["Q&A KPRM", f"nr {qid}"],
                                 None, None, proc, f"Pytanie: {norm_ws(it['question'])}\nOdpowiedź: {norm_ws(it['answer'])}",
                                 f"assets/kprm_qa/{f.name}", f"kprm_qa_oceny:{slugify(qid) or n}"))
    report.counts["kprm_qa_items"] = len(chunks)
    return chunks, {"source_id": "kprm_qa_oceny", "doc_type": "kprm_qa",
                    "title": next((m.get("title") for m in metas.values() if m.get("title")),
                                  "Pytania i odpowiedzi – Oceny pracownicze (Serwis Służby Cywilnej, gov.pl)"),
                    "short_title": "Q&A KPRM",
                    "process": ["periodic", "first"],
                    "url": next((m.get("url") for m in metas.values() if m.get("url")), None),
                    "accessed": next((m.get("accessed") for m in metas.values() if m.get("accessed")), None),
                    "license": next((m.get("license_text") for m in metas.values() if m.get("license_text")), None),
                    "file": [f"assets/kprm_qa/{k}" for k in sorted(hashes)], "sha256": hashes}


def rel_ustawa(txt: Path) -> str:
    try:
        return txt.resolve().relative_to(SKILLS_DIR.parent.parent.resolve()).as_posix()
    except ValueError:
        return "assets/ustawa_sc/" + txt.name


# --------------------------------------------------------------------------- model + forms -> KB
def kb_model(model: dict) -> list[dict]:
    meta = SOURCE_META["model_kompetencji"]
    scale = {str(s["level"]): s["label"] for s in model["scale"]}
    out = []
    for c in model["competencies"]:
        parts = [f"Kompetencja: {c['name']} (w modelu: {c['name_in_model']})."]
        for ind in c["indicators"]:
            parts.append(f"Wskaźnik {ind['id']}: {ind['text']}")
            for lvl in sorted(ind["levels"]):
                parts.append(f"– {scale[lvl]}: {ind['levels'][lvl]}")
        out.append(_chunk("model_kompetencji", "model_kompetencji", meta["title"], f"kompetencja: {c['name']}",
                          f"{meta['cite']}, kompetencja „{c['name']}”", [meta["short"], c["name"]], None, None,
                          meta["process"], "\n".join(parts), model["source"]["file"], f"model_kompetencji:{c['id']}"))
    out.append(_chunk("model_kompetencji", "model_kompetencji", meta["title"], "instrukcja",
                      f"{meta['cite']}, instrukcja (arkusz „Model kompetencji”)", [meta["short"], "instrukcja"], None,
                      None, meta["process"], "\n".join([model.get("summary_line", "")] + model["instructions"]).strip(),
                      model["source"]["file"], "model_kompetencji:instrukcja"))
    return out


FORM_META = {
    "periodic_b": ("rozp2016", "arkusz B", "załącznik nr 3 do", ["periodic"]),
    "periodic_c": ("rozp2016", "arkusz C", "załącznik nr 4 do", ["periodic"]),
    "first_eval": ("rozp2015", "arkusz pierwszej oceny", "załącznik nr 2 do", ["first"]),
}
PART_LABEL = {"part1": "część I", "part2": "część II", "part3": "część III", "general": None}


def kb_forms(forms: dict) -> list[dict]:
    out = []
    for fid, form in forms.items():
        src, name, annex, proc = FORM_META[fid]
        meta = SOURCE_META[src]
        for fn in form["footnotes"]:
            where = PART_LABEL.get(fn.get("part") or "", None)
            anchor = fn.get("anchor") or ""
            short = anchor if len(anchor) <= 80 else anchor[:80].rsplit(" ", 1)[0] + " …"
            ctx = f" (pole „{short}”" + (f", {where}" if where else "") + ")" if anchor else ""
            unit = f"{name}, przypis {fn['number']})"
            loc = {"periodic_b": "arkuszu B", "periodic_c": "arkuszu C", "first_eval": "arkuszu pierwszej oceny"}[fid]
            text = f"Przypis {fn['number']}) w {loc}{ctx}: {fn['text']}"
            out.append(_chunk(src, "arkusz", f"{name[:1].upper()}{name[1:]} – wzór ({annex} {meta['cite']})", unit,
                              f"przypis {fn['number']}) {name} ({annex} {meta['cite']})",
                              [meta["short"], name, f"przypis {fn['number']})"], None, None, proc, text,
                              form["source"]["file"], f"{fid}:przypis{fn['number']}"))
    return out


def kb_annex1(annex1: dict) -> list[dict]:
    meta = SOURCE_META["rozp2016"]
    out = []
    for c in annex1["criteria"]:
        text = f"Kryterium oceny {c['no']}. {c['name']} – opis (załącznik nr 1): " + " ".join(f"− {d}" for d in c["description"])
        unit = f"zał. nr 1, kryterium {c['no']}"
        out.append(_chunk("rozp2016", "rozporzadzenie", meta["title"], unit,
                          f"załącznik nr 1 (wykaz kryteriów oceny), kryterium {c['no']} „{c['name']}” do {meta['cite']}",
                          [meta["short"], "załącznik nr 1 – wykaz kryteriów oceny", c["name"]], c.get("page"),
                          c.get("page"), ["periodic"], text, annex1["source"]["file"], f"rozp2016:zal1:{c['id']}"))
    return out


def build_kb(inputs, input_dir, model, forms, annex1, ustawa, report):
    chunks: list[dict] = []
    sources = []

    def add_source(sid, path: Path | None, extra=None):
        meta = SOURCE_META.get(sid, {})
        entry = {"source_id": sid, "doc_type": meta.get("doc_type"), "title": meta.get("title"),
                 "short_title": meta.get("short"), "process": meta.get("process"), "url": meta.get("url"),
                 "file": rel(path, input_dir) if path else None, "sha256": sha256_file(path) if path else None}
        if extra:
            entry.update(extra)
        sources.append(entry)

    if ustawa and Path(ustawa).exists():
        uc, umeta = kb_ustawa(Path(ustawa), report)
        chunks += uc
        sources.append({"source_id": "ustawa_sc", "doc_type": "ustawa", "title": umeta.get("title"),
                        "short_title": "ustawa o służbie cywilnej", "process": ["periodic", "first"],
                        "url": umeta.get("url"), "eli": umeta.get("eli"), "dz_u": umeta.get("dz_u"),
                        "stan_prawny_na": umeta.get("stan_prawny_na"), "accessed": umeta.get("accessed"),
                        "file": rel_ustawa(Path(ustawa)), "sha256": sha256_file(Path(ustawa))})
        report.inputs["ustawa_txt"] = {"file": rel_ustawa(Path(ustawa)), "sha256": sha256_file(Path(ustawa))}
    else:
        report.warn("Brak tekstu ustawy o sluzbie cywilnej (assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt) - "
                    "KB bez ustawy; pkt 5 i 7 tresci zadania wymagaja ustawy w bazie wiedzy.")
    for sid, key in (("rozp2016", "rozp2016_pdf"), ("rozp2015", "rozp2015_pdf")):
        if inputs.get(key):
            chunks += kb_regulation(inputs[key], sid, input_dir, report)
            add_source(sid, inputs[key])
    if annex1:
        chunks += kb_annex1(annex1)
    a15 = (forms or {}).get("first_eval", {}).get("element_descriptions")
    if a15:
        meta15 = SOURCE_META["rozp2015"]
        for c in a15["criteria"]:
            if not c["description"]:
                continue
            chunks.append(_chunk("rozp2015", "rozporzadzenie", meta15["title"], f"zał. nr 1, element {c['no']}",
                                 f"załącznik nr 1 (opisy elementów oceny), element {c['no']} „{c['name']}” do {meta15['cite']}",
                                 [meta15["short"], "załącznik nr 1 – opisy elementów oceny", c["name"]], c.get("page"),
                                 c.get("page"), ["first"],
                                 f"Element pierwszej oceny {c['no']}. {c['name']} – opis (załącznik nr 1): "
                                 + " ".join(f"− {d}" for d in c["description"]),
                                 a15["source"]["file"], f"rozp2015:zal1:{c['id']}"))
    for sid, key in (("poradnik_okresowa_2016", "poradnik_okresowa_pdf"), ("poradnik_pierwsza_2016", "poradnik_pierwsza_pdf")):
        if inputs.get(key):
            chunks += kb_guide(inputs[key], sid, input_dir, report)
            add_source(sid, inputs[key])
    if model:
        chunks += kb_model(model)
        add_source("model_kompetencji", inputs.get("model_xlsx"))
    qa_chunks, qa_source = kb_kprm_qa(SKILL_DIR / "assets" / "kprm_qa", report)
    chunks += qa_chunks
    if qa_source:
        sources.append(qa_source)
    if forms:
        chunks += kb_forms(forms)
        for fid, f in forms.items():
            sources.append({"source_id": FORM_META[fid][0], "doc_type": "arkusz",
                            "title": f"{FORM_META[fid][1]} – {FORM_META[fid][2]} {SOURCE_META[FORM_META[fid][0]]['cite']}",
                            "short_title": FORM_META[fid][1], "process": FORM_META[fid][3], "url": None,
                            "file": f["source"]["file"], "sha256": f["source"]["sha256"], "form": fid})
    ids = [c["id"] for c in chunks]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise BuildError(f"Zdublowane id fragmentow KB: {dup[:10]}")
    return chunks, sources


# --------------------------------------------------------------------------- annex 1 (wykaz kryteriow)
_BULLETS = ("−", "–", "-")
_NAME_TOKEN = re.compile(r"^(\d+\.|[A-ZĄĆĘŁŃÓŚŹŻ/]+[A-ZĄĆĘŁŃÓŚŹŻ/.,]*)$")


def _split_columns(line: str) -> tuple[str, str]:
    """Lewa kolumna = poczatkowe slowa pisane WERSALIKAMI (nazwa kryterium), prawa = reszta (opis)."""
    toks = list(re.finditer(r"\S+", line))
    k = 0
    while k < len(toks) and toks[k].group(0) not in _BULLETS and _NAME_TOKEN.match(toks[k].group(0)):
        k += 1
    left = " ".join(t.group(0) for t in toks[:k])
    right = line[toks[k].start():].strip() if k < len(toks) else ""
    return left, right


def parse_criteria_table(pages: list[str], start_rx: str, stop_rx: str | None, page_offset: int = 0) -> tuple[list, list]:
    """Parsuje tabele 'KRYTERIUM | OPIS' z tekstu pdftotext -layout. Zwraca (kryteria, punkty opisu)."""
    crits, bullets = [], []
    started = False
    for pno, page in enumerate(pages, 1):
        for raw in page.split("\n"):
            line = raw.replace("﻿", "").replace("www.rcl.gov.pl", " " * 14).rstrip()
            st = line.strip()
            if not started:
                if re.search(start_rx, st):
                    started = True
                continue
            if stop_rx and re.search(stop_rx, st):
                return crits, bullets
            if not st or _HEADER_LINE.match(st) or re.fullmatch(r"(–\s*\d+\s*–\s*)?Poz\.\s*\d+", st) or st.startswith("Dziennik Ustaw"):
                continue
            left, right = _split_columns(st)
            if left:
                m = re.match(r"^(\d+)\.\s*(.*)$", left)
                if m:
                    crits.append({"no": int(m.group(1)), "name_parts": [m.group(2)], "page": pno + page_offset,
                                  "line_bullets_before": len(bullets)})
                elif crits:
                    crits[-1]["name_parts"].append(left)
            if right:
                if right[0] in _BULLETS:
                    for piece in re.split(r"\s(?=[−]\s)", right):
                        bullets.append({"text": piece.lstrip("".join(_BULLETS)).strip(), "page": pno + page_offset,
                                        "crit_index": len(crits) - 1})
                elif bullets:
                    bullets[-1]["text"] += " " + right
    return crits, bullets


ANNEX1_2016_TITLE = ("Załącznik nr 1 do rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. "
                     "(Dz. U. poz. 470) – Wykaz kryteriów oceny")
ANNEX1_2015_TITLE = ("Załącznik nr 1 do rozporządzenia Prezesa Rady Ministrów z dnia 23 lipca 2015 r. "
                     "(Dz. U. poz. 1144) – Opisy elementów oceny")


def build_annex1(pdf: Path, mat_root: Path, report: Report, model: dict | None = None,
                 start_rx: str = r"^KRYTERIUM\s+OPIS$", stop_rx: str = r"^Załącznik nr 2\b",
                 title: str = ANNEX1_2016_TITLE, expected: int | None = 14, label: str = "Zalacznik nr 1") -> dict:
    pages = pdf_pages(pdf, layout=True)
    # wyciag 3-stronicowy albo pelne rozporzadzenie: start od naglowka tabeli, stop na zalaczniku nr 2
    crits, bullets = parse_criteria_table(pages, start_rx, stop_rx)
    for c in crits:
        c["name_in_annex"] = norm_ws(" ".join(c["name_parts"]))
        c["name"] = canonical_name(c["name_in_annex"], report)
        c["id"] = slugify(c["name"])
        c["bullets"] = []
    # wykrycie stron, na ktorych nazwy kryteriow sa "stloczone" (brak punktow miedzy kolejnymi nazwami)
    stacked_pages = set()
    for i, c in enumerate(crits):
        nxt = crits[i + 1]["line_bullets_before"] if i + 1 < len(crits) else len(bullets)
        if nxt - c["line_bullets_before"] == 0:
            stacked_pages.add(c["page"])
    model_by_id = {mc["id"]: mc for mc in (model or {}).get("competencies", [])}
    for b in bullets:
        b["text"] = norm_ws(b["text"])
    for c in crits:
        c["assignment"] = "layout"
    for page in sorted(stacked_pages):
        page_crits = [c for c in crits if c["page"] == page]
        pool = [b for b in bullets if b["page"] == page]
        for b in pool:
            b["crit_index"] = None
        exp_texts = [ind["text"] for c in page_crits for ind in model_by_id.get(c["id"], {}).get("indicators", [])]
        if model_by_id and [norm_cmp(x) for x in exp_texts] == [norm_cmp(b["text"]) for b in pool]:
            pos = 0
            for c in page_crits:
                n = len(model_by_id[c["id"]]["indicators"])
                c["bullets"] = [b["text"] for b in pool[pos:pos + n]]
                c["assignment"] = "sequence_match_with_model"
                pos += n
            report.warn(f"{label}, s. {page}: uklad PDF nie wiaze nazw kryteriow z opisami "
                        f"({', '.join(c['name'] for c in page_crits)}); granice opisow ustalono przez zgodnosc "
                        f"sekwencji punktow z modelem - nie jest to niezalezna weryfikacja przydzialu.")
        else:
            for c in page_crits:
                c["assignment"] = "ambiguous_layout"
            report.warn(f"{label}, s. {page}: nie da sie jednoznacznie przypisac opisow do kryteriow "
                        f"{[c['name'] for c in page_crits]} (pula {len(pool)} punktow).")
    for b in bullets:
        if b["crit_index"] is not None and b["crit_index"] >= 0 and crits[b["crit_index"]]["assignment"] == "layout":
            crits[b["crit_index"]]["bullets"].append(b["text"])
    out_crits = [{"no": c["no"], "id": c["id"], "name": c["name"], "name_in_annex": c["name_in_annex"],
                  "description": c["bullets"], "page": c["page"], "assignment": c["assignment"]} for c in crits]
    key = "annex1" if label == "Zalacznik nr 1" else slugify(label)
    report.counts[f"{key}_criteria"] = len(out_crits)
    report.counts[f"{key}_description_items"] = sum(len(c["description"]) for c in out_crits)
    if expected is not None and len(out_crits) != expected:
        report.warn(f"{label}: odczytano {len(out_crits)} kryteriow, oczekiwano {expected}.")
    return {
        "source": {"file": rel(pdf, mat_root), "sha256": sha256_file(pdf)},
        "title": title,
        "criteria": out_crits,
    }


def check_model_vs_annex1(model: dict, annex1: dict, report: Report) -> dict:
    """Kazdy wskaznik modelu musi wystapic (po normalizacji) w opisie wlasciwego kryterium zal. nr 1."""
    by_id = {c["id"]: c for c in annex1["criteria"]}
    mismatches, checked, extra = [], 0, []
    for comp in model["competencies"]:
        crit = by_id.get(comp["id"])
        desc = [norm_cmp(d) for d in (crit or {}).get("description", [])]
        joined = " ".join(desc)
        for ind in comp["indicators"]:
            checked += 1
            t = norm_cmp(ind["text"])
            if crit is None:
                mismatches.append({"indicator_id": ind["id"], "text": ind["text"], "problem": "brak kryterium w zał. nr 1"})
            elif t not in desc and t not in joined:
                best = max(desc, key=lambda d: len(os.path.commonprefix([d, t])), default="")
                mismatches.append({"indicator_id": ind["id"], "text": ind["text"],
                                   "problem": "brak w opisie kryterium", "closest_annex_text": best})
        if crit:
            model_texts = {norm_cmp(i["text"]) for i in comp["indicators"]}
            for d in crit.get("description", []):
                if norm_cmp(d) not in model_texts:
                    extra.append({"criterion": crit["id"], "annex_text": d})
    for m in mismatches:
        report.warn(f"Model vs zal. nr 1: {m['indicator_id']} - {m['problem']}: {m['text'][:80]}")
    for e in extra:
        report.warn(f"Zal. nr 1: punkt opisu bez odpowiednika w modelu ({e['criterion']}): {e['annex_text'][:80]}")
    report.checks["model_vs_annex1"] = {"checked": checked, "mismatches": len(mismatches), "annex_extra": len(extra)}
    return {"checked": checked, "mismatches": mismatches, "annex_items_not_in_model": extra,
            "normalization": "białe znaki, rodzaje myślników, spacje wokół '/', kropka końcowa, wielkość liter"}


# --------------------------------------------------------------------------- OSP
def build_osp(inputs, input_dir, output_dir, report) -> None:
    """OSP przez parser z kompas-analiza-osp (kontrakt C4). Brak parsera = ostrzezenie, nie blad."""
    report.counts["osp_files"] = 0
    zpath = inputs.get("osp_zip")
    if not zpath:
        return
    parser_dir = Path(os.environ.get("KOMPAS_OSP_PARSER_DIR") or OSP_PARSER_DIR)
    if str(parser_dir) not in sys.path:
        sys.path.insert(0, str(parser_dir))
    try:
        from osp_parser import parse_osp_docx  # type: ignore
    except Exception as e:  # noqa: BLE001 - kazdy blad importu = ostrzezenie
        report.warn(f"Parser OSP niedostepny ({parser_dir / 'osp_parser.py'}: {type(e).__name__}: {e}) - pominieto osp/*.json.")
        return
    osp_dir = output_dir / "osp"
    # rozpakowanie do katalogu tymczasowego (bez sciezek z archiwum - ochrona przed zip-slip)
    with tempfile.TemporaryDirectory(prefix="kompas_osp_") as tmp, zipfile.ZipFile(zpath) as zf:
        members = list(i for i in zf.infolist()
                         if i.filename.lower().endswith(".docx") and "__MACOSX" not in i.filename
                         and not Path(i.filename).name.startswith("~$"))
        for info in sorted(members, key=lambda i: i.filename):
            name = Path(info.filename).name
            local = Path(tmp) / f"{len(list(Path(tmp).iterdir())):03d}.docx"
            local.write_bytes(zf.read(info))
            try:
                data = parse_osp_docx(str(local), filename=name)
            except Exception as e:  # noqa: BLE001
                report.warn(f"OSP {name}: blad parsera {type(e).__name__}: {e}")
                continue
            slug = slugify(Path(name).stem)
            write_json(osp_dir / f"{slug}.json", data)
            report.inputs[f"osp:{name}"] = {"file": f"{rel(zpath, input_dir)}!{info.filename}",
                                            "sha256": hashlib.sha256(zf.read(info)).hexdigest()}
            report.counts["osp_files"] += 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Buduje dane Kompasu Kompetencji z materialow Partnera (kontrakt C1).")
    ap.add_argument("--input", required=True, help="katalog materialow Partnera (np. materialy/)")
    ap.add_argument("--output", required=True, help="katalog wyjsciowy (np. data/processed)")
    ap.add_argument("--ustawa", default=os.environ.get("KOMPAS_USTAWA_TXT"),
                    help="tekst ustawy o sluzbie cywilnej (domyslnie assets/ustawa_sc/ustawa_o_sluzbie_cywilnej.txt)")
    ap.add_argument("--allow-model-change", action="store_true",
                    help="nie przerywaj, gdy model ma inna liczbe kompetencji/wskaznikow niz 14/49")
    args = ap.parse_args(argv)
    try:
        report = run(Path(args.input), Path(args.output),
                     Path(args.ustawa) if args.ustawa else DEFAULT_USTAWA, strict=not args.allow_model_change)
    except BuildError as e:
        print(f"BLAD: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"counts": report.counts, "warnings": len(report.warnings)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
