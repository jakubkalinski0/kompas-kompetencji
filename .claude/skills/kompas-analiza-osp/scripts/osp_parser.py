#!/usr/bin/env python3
"""Parser opisu stanowiska pracy (OSP) w formacie DOCX -> dict / JSON.

Tylko biblioteka standardowa (zipfile + xml.etree). Czyta tabele DOCX komórka
po komórce, łączy runy, zachowuje znaki pól wyboru (☒/☐) i rozpoznaje pola
wyboru `w14:checkbox` (SDT), `w:sym` (Wingdings) oraz starsze FORMCHECKBOX.

Sekcje rozpoznaje po etykietach, nie po pozycjach tabel, bo szablony OSP
różnią się układem (np. w OSP radcy część I i „miejsce w strukturze” są
w jednej tabeli, a zadania dominujące i pozostałe w jednej tabeli).

Minimalizacja danych: parser nie czyta metadanych (docProps), nie zwraca
imion, nazwisk ani podpisów – pola osobowe zamienia na „[osoba]”.

Użycie jako biblioteki (kontrakt C4):
    from osp_parser import parse_osp_docx
    data = parse_osp_docx("OSP.docx")

CLI:
    python osp_parser.py <plik.docx|katalog|plik.zip> [--out KATALOG]
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Iterator

__all__ = [
    "parse_osp_docx",
    "iter_docx_inputs",
    "match_soft_competencies",
    "slugify",
    "COMPETENCIES",
    "OspParseError",
    "SCHEMA_VERSION",
]

SCHEMA_VERSION = "1.0"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"

MAX_DOCX_BYTES = 30 * 1024 * 1024
MAX_XML_BYTES = 25 * 1024 * 1024

CHECKED_GLYPH = "☒"  # ☒
UNCHECKED_GLYPH = "☐"  # ☐
GLYPH_STATE = {"☒": True, "☑": True, "☐": False}
# Wingdings / Wingdings 2 (w:sym w:char): pola zaznaczone / puste
SYM_STATE = {
    "F078": True, "F0FE": True, "F0FD": True, "F054": True, "F052": True,
    "F0A8": False, "F06F": False, "F071": False, "F0A3": False, "F0A1": False,
}
SYM_TEXT = {"F0B7": "•", "F02D": "-", "F0A7": "•"}

PLACEHOLDERS = {
    "wybierz element.",
    "wybierz element",
    "kliknij lub naciśnij tutaj, aby wprowadzić tekst.",
    "kliknij tutaj, aby wprowadzić tekst.",
    "choose an item.",
    "click or tap here to enter text.",
}

# 14 kryteriów z załącznika nr 1 do rozporządzenia z 2016 r.; id wg kontraktu C1.
COMPETENCIES: dict[str, str] = {
    "komunikacja": "Komunikacja",
    "kreatywnosc": "Kreatywność",
    "negocjowanie": "Negocjowanie",
    "organizacja_pracy_i_orientacja_na_osiaganie_celow": "Organizacja pracy i orientacja na osiąganie celów",
    "orientacja_na_klienta_interesanta": "Orientacja na klienta/interesanta",
    "podejmowanie_decyzji_i_odpowiedzialnosc": "Podejmowanie decyzji i odpowiedzialność",
    "radzenie_sobie_w_sytuacjach_kryzysowych": "Radzenie sobie w sytuacjach kryzysowych",
    "rzetelnosc": "Rzetelność",
    "myslenie_analityczne": "Myślenie analityczne",
    "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe": "Wykorzystywanie wiedzy i doskonalenie zawodowe",
    "wspolpraca": "Współpraca",
    "wystapienia_publiczne": "Wystąpienia publiczne",
    "zarzadzanie_ludzmi": "Zarządzanie ludźmi",
    "zarzadzanie_strategiczne": "Zarządzanie strategiczne",
}
# Skrócone / potoczne brzmienia spotykane w OSP innych urzędów (dopasowanie „alias” = do potwierdzenia).
SOFT_ALIASES: dict[str, str] = {
    "orientacja na klienta": "orientacja_na_klienta_interesanta",
    "orientacja na interesanta": "orientacja_na_klienta_interesanta",
    "podejmowanie decyzji": "podejmowanie_decyzji_i_odpowiedzialnosc",
    "organizacja pracy": "organizacja_pracy_i_orientacja_na_osiaganie_celow",
    "orientacja na osiaganie celow": "organizacja_pracy_i_orientacja_na_osiaganie_celow",
    "orientacja na cele": "organizacja_pracy_i_orientacja_na_osiaganie_celow",
    "wykorzystywanie wiedzy": "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe",
    "doskonalenie zawodowe": "wykorzystywanie_wiedzy_i_doskonalenie_zawodowe",
    "radzenie sobie w sytuacjach kryzysowych": "radzenie_sobie_w_sytuacjach_kryzysowych",
    "radzenie sobie ze stresem": "radzenie_sobie_w_sytuacjach_kryzysowych",
    "zarzadzanie zespolem": "zarzadzanie_ludzmi",
    "myslenie strategiczne": "zarzadzanie_strategiczne",
}

# Kody przedziałów „Liczba podległych pracowników” (kolejność jak w szablonie MC).
SUBORDINATE_CODES = [
    ("brak podleglych", "none"),
    ("do 4", "up_to_4"),
    ("od 5 do 9", "5_to_9"),
    ("powyzej 9", "above_9"),
    ("podlegaja osoby kierujace", "manages_managers"),
]

CONTACT_ORDER = ["kilka razy dziennie", "kilka razy w tygodniu", "kilka razy w miesiacu", "kilka razy w roku"]

SECTION_HEADERS = [
    ("opis stanowiska pracy", "title"),
    ("miejsce stanowiska pracy w strukturze", "part1"),
    ("zapoznanie pracownika z opisem", "acknowledgement"),
    ("cel istnienia stanowiska", "purpose"),
    ("liczba podleglych pracownikow", "subordinates"),
    ("glowne zadania realizowane", "tasks"),
    ("zadania dominujace", "tasks_dominant"),
    ("pozostale zadania", "tasks_other"),
    ("upowaznienia i pelnomocnictwa", "authorizations"),
    ("zlozonosc i kreatywnosc", "complexity_creativity"),
    ("niezbedna samodzielnosc i inicjatywa", "independence_initiative"),
    ("samodzielnosc i inicjatywa", "independence_initiative"),
    ("horyzont czasowy planowania", "planning_horizon"),
    ("kontakty zewnetrzne", "external_contacts"),
    ("czynniki szczegolnie utrudniajace", "hindering_factors"),
    ("wymagane kompetencje", "required_competencies"),
]
PART_HEADERS = {"czesc i": 1, "czesc ii": 2, "czesc iii": 3}

PART1_LABELS = [
    ("nazwa urzedu", "office"),
    ("nazwa komorki organizacyjnej", "org_unit"),
    ("nazwa stanowiska pracy", "position_name"),
    ("stanowisko do spraw", "position_specialization"),
    ("symbol stanowiska pracy", "position_symbol"),
    ("stanowisko pracy posrednio nadzorujace", "supervisor_indirect"),
    ("stanowisko pracy bezposrednio nadzorujace", "supervisor_direct"),
]

_PL_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
_PL_LOWER = "a-ząćęłńóśźż"
_NAME_RE = re.compile(
    rf"\b[{_PL_UPPER}][{_PL_LOWER}]+(?:-[{_PL_UPPER}][{_PL_LOWER}]+)?"
    rf"(?:\s+[{_PL_UPPER}][{_PL_LOWER}]+(?:-[{_PL_UPPER}][{_PL_LOWER}]+)?){{1,2}}\b"
)
_NOT_NAME_FIRST = {
    "Kierujący", "Osoba", "Zatwierdzam", "Dyrektor", "Naczelnik", "Ministerstwo", "Departament",
    "Wydział", "Biuro", "Zastępca", "Minister", "Sekretarz", "Podsekretarz", "Kierownik", "Główny",
}
_MARKER_RE = re.compile(r"^\s*([/\-–(\[]).*([/\-–)\]])\s*$")


class OspParseError(ValueError):
    """Plik nie jest poprawnym DOCX z opisem stanowiska pracy."""


# --------------------------------------------------------------------------- utils

def _norm(s: str) -> str:
    """Małe litery ASCII bez diakrytyków, znaki niealfanumeryczne -> spacja."""
    s = (s or "").replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def slugify(s: str) -> str:
    """ASCII snake_case, np. 'OSP DXX WYY 1 naczelnik wydziału' -> 'osp_dxx_wyy_1_naczelnik_wydzialu'."""
    return _norm(s).replace(" ", "_") or "osp"


def _clean(s: str) -> str:
    s = (s or "").replace(" ", " ").replace("\t", " ")
    lines = [re.sub(r"[ ]{2,}", " ", ln).strip() for ln in s.split("\n")]
    out = "\n".join(ln for ln in lines if ln)
    return "" if out.lower() in PLACEHOLDERS else out


def _is_upper_label(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def redact_names(text: str) -> str:
    """Heurystyka: 2–3 kolejne wyrazy z wielkiej litery (poza słownikiem ról) -> „[osoba]”."""
    def repl(m: re.Match) -> str:
        first = m.group(0).split()[0]
        return m.group(0) if first in _NOT_NAME_FIRST else "[osoba]"
    return _NAME_RE.sub(repl, text or "")


# --------------------------------------------------------------------------- XML -> komórki

def _sdt_props(sdt: ET.Element):
    pr = sdt.find(W + "sdtPr")
    if pr is None:
        return None, False
    return pr.find(W14 + "checkbox"), pr.find(W + "showingPlcHdr") is not None


def _para_tokens(p: ET.Element) -> list[tuple]:
    tokens: list[tuple] = []

    def emit_text(s: str) -> None:
        buf: list[str] = []
        for ch in s:
            if ch in GLYPH_STATE:
                if buf:
                    tokens.append(("t", "".join(buf)))
                    buf = []
                tokens.append(("cb", GLYPH_STATE[ch], "glyph"))
            else:
                buf.append(ch)
        if buf:
            tokens.append(("t", "".join(buf)))

    def walk_run(r: ET.Element) -> None:
        for ch in r:
            tag = ch.tag
            if tag == W + "t":
                emit_text(ch.text or "")
            elif tag == W + "tab":
                tokens.append(("t", " "))
            elif tag in (W + "br", W + "cr"):
                tokens.append(("t", "\n"))
            elif tag == W + "noBreakHyphen":
                tokens.append(("t", "-"))
            elif tag == W + "sym":
                code = (ch.get(W + "char") or "").upper()
                if code in SYM_STATE:
                    tokens.append(("cb", SYM_STATE[code], "w:sym"))
                elif code in SYM_TEXT:
                    tokens.append(("t", SYM_TEXT[code]))
            elif tag == W + "fldChar" and ch.get(W + "fldCharType") == "begin":
                ff = ch.find(W + "ffData")
                cbx = ff.find(W + "checkBox") if ff is not None else None
                if cbx is not None:
                    chk = cbx.find(W + "checked")
                    if chk is not None:
                        state = (chk.get(W + "val") or "1").lower() not in ("0", "false", "off")
                    else:
                        d = cbx.find(W + "default")
                        state = d is not None and (d.get(W + "val") or "0").lower() not in ("0", "false", "off")
                    tokens.append(("cb", state, "formcheckbox"))
            # w:instrText, w:delText, w:rPr – pomijane

    def walk(el: ET.Element) -> None:
        for ch in el:
            tag = ch.tag
            if tag == W + "r":
                walk_run(ch)
            elif tag == W + "sdt":
                cb, plc = _sdt_props(ch)
                if cb is not None:
                    c = cb.find(W14 + "checked")
                    val = c.get(W14 + "val") if c is not None else None
                    if val is None:
                        shown = "".join(t.text or "" for t in ch.iter(W + "t"))
                        state = any(GLYPH_STATE.get(x, False) for x in shown)
                    else:
                        state = val.lower() in ("1", "true", "on")
                    tokens.append(("cb", state, "w14:checkbox"))
                    continue
                if plc:
                    continue
                content = ch.find(W + "sdtContent")
                if content is not None:
                    walk(content)
            elif tag in (W + "del", W + "moveFrom", W + "pPr", W + "rPr", W + "sdtPr"):
                continue
            else:  # w:hyperlink, w:ins, w:smartTag, w:fldSimple, w:customXml, w:moveTo
                walk(ch)

    walk(p)
    return tokens


def _para_info(p: ET.Element) -> tuple[str, list[dict]]:
    parts: list[str] = []
    cbs: list[dict] = []
    cur = None
    for tok in _para_tokens(p):
        if tok[0] == "cb":
            parts.append((CHECKED_GLYPH if tok[1] else UNCHECKED_GLYPH) + " ")
            cur = {"checked": tok[1], "source": tok[2], "label_parts": []}
            cbs.append(cur)
        else:
            parts.append(tok[1])
            if cur is not None:
                cur["label_parts"].append(tok[1])
    text = _clean("".join(parts))
    boxes = [
        {"label": _clean("".join(c["label_parts"])).replace("\n", " "), "checked": c["checked"], "source": c["source"]}
        for c in cbs
    ]
    return text, boxes


def _iter_paragraphs(el: ET.Element, placeholder: bool = False) -> Iterator[ET.Element]:
    for ch in el:
        if ch.tag == W + "p":
            if not placeholder:
                yield ch
        elif ch.tag == W + "sdt":
            _, plc = _sdt_props(ch)
            content = ch.find(W + "sdtContent")
            if content is not None:
                yield from _iter_paragraphs(content, placeholder or plc)
        elif ch.tag == W + "tbl":
            for tc in ch.iter(W + "tc"):
                yield from _iter_paragraphs(tc, placeholder)
        elif ch.tag == W + "customXml":
            yield from _iter_paragraphs(ch, placeholder)


def _cell_info(container: ET.Element, placeholder: bool = False) -> dict:
    paras: list[str] = []
    boxes: list[dict] = []
    pending_label: list[dict] = []
    para_has_box: list[bool] = []
    for p in _iter_paragraphs(container, placeholder):
        text, cbs = _para_info(p)
        if pending_label and text and not cbs:
            for b in pending_label:
                b["label"] = text
            pending_label = []
        for b in cbs:
            if not b["label"]:
                pending_label.append(b)
        if text:
            paras.append(text)
            para_has_box.append(bool(cbs))
        boxes.extend(cbs)
    return {"paras": paras, "text": "\n".join(paras), "checkboxes": boxes, "para_has_box": para_has_box}


def _row_cells(tr: ET.Element) -> list[dict]:
    cells: list[dict] = []

    def walk(el: ET.Element, plc: bool) -> None:
        for ch in el:
            if ch.tag == W + "tc":
                cells.append(_cell_info(ch, plc))
            elif ch.tag == W + "sdt":
                _, p = _sdt_props(ch)
                content = ch.find(W + "sdtContent")
                if content is not None:
                    walk(content, plc or p)
            elif ch.tag == W + "customXml":
                walk(ch, plc)

    walk(tr, False)
    return cells


def _stream(el: ET.Element) -> Iterator[dict]:
    for ch in el:
        if ch.tag == W + "p":
            info = _cell_info_from_para(ch)
            if info["text"]:
                yield {"kind": "p", "cells": [info]}
        elif ch.tag == W + "tbl":
            for tr in ch.iter(W + "tr"):
                yield {"kind": "row", "cells": _row_cells(tr)}
        elif ch.tag == W + "sdt":
            _, plc = _sdt_props(ch)
            content = ch.find(W + "sdtContent")
            if content is not None and not plc:
                yield from _stream(content)
        elif ch.tag == W + "customXml":
            yield from _stream(ch)


def _cell_info_from_para(p: ET.Element) -> dict:
    text, cbs = _para_info(p)
    return {"paras": [text] if text else [], "text": text, "checkboxes": cbs, "para_has_box": [bool(cbs)] if text else []}


# --------------------------------------------------------------------------- sekcje

def _match_header(text: str):
    n = _norm(text.split("\n")[0])
    if n in PART_HEADERS:
        return "part", PART_HEADERS[n]
    for key, sec in SECTION_HEADERS:
        if n.startswith(key):
            return "section", sec
    return None


def _nonempty(cells: list[dict]) -> list[dict]:
    return [c for c in cells if c["text"]]


def _split_sections(body: ET.Element) -> tuple[dict, str | None]:
    sections: dict[str, list[list[dict]]] = {}
    title = None
    part = 1
    section = "part1"
    for item in _stream(body):
        cells = item["cells"]
        ne = _nonempty(cells)
        if not ne:
            continue
        hit = _match_header(ne[0]["text"])
        if hit and hit[0] == "part":
            part = hit[1]
            section = {1: "part1", 2: None, 3: "part3"}[part]
            continue
        if hit and hit[0] == "section":
            if hit[1] == "title":
                title = title or ne[0]["text"].replace("\n", " ")
                continue
            section = hit[1]
            rest = ne[1:]
            if rest:
                sections.setdefault(section, []).append(rest)
            continue
        key = section or f"unassigned_part{part}"
        sections.setdefault(key, []).append(cells)
    return sections, title


def _all_boxes(rows: list[list[dict]]) -> list[dict]:
    return [b for row in rows for c in row for b in c["checkboxes"]]


def _plain_text(rows: list[list[dict]], skip_labels: tuple[str, ...] = ()) -> str:
    """Tekst z akapitów bez pól wyboru (np. przykłady), bez etykiet kolumn."""
    out: list[str] = []
    for row in rows:
        for c in row:
            for t, has_box in zip(c["paras"], c["para_has_box"]):
                if has_box or _norm(t) in skip_labels:
                    continue
                if any(b["label"] == t for b in c["checkboxes"]):
                    continue
                out.append(t)
    return "\n".join(out)


def _options(boxes: list[dict]) -> dict:
    opts = [{"label": b["label"], "checked": b["checked"]} for b in boxes]
    return {"options": opts, "selected": [o["label"] for o in opts if o["checked"]]}


def _desc_examples(rows: list[list[dict]], header_first: str) -> dict:
    desc, ex = [], []
    for row in rows:
        ne = _nonempty(row)
        if not ne:
            continue
        if _norm(ne[0]["text"]) == header_first:
            continue
        desc.append(ne[0]["text"])
        ex.extend(c["text"] for c in ne[1:])
    return {"description": "\n".join(desc) or None, "examples": "\n".join(ex) or None}


def _parse_part1(rows: list[list[dict]], warnings: list[str]) -> dict:
    out: dict = {
        "office": None, "org_unit": None, "org_subunits": [], "org_unit_path": None,
        "position_name": None, "position_specialization": None, "position_symbol": None,
        "supervisor_indirect": None, "supervisor_direct": None, "other_fields": {},
    }
    last = None
    for row in rows:
        ne = _nonempty(row)
        if not ne:
            continue
        first = ne[0]
        label_n = _norm(first["paras"][0])
        key = next((k for lab, k in PART1_LABELS if label_n.startswith(lab)), None)
        value = " ".join(c["text"].replace("\n", " ") for c in ne[1:]) or None
        if key:
            out[key] = value
            last = key
        elif not _is_upper_label(first["paras"][0]) and last in ("org_unit", "org_subunit"):
            out["org_subunits"].append(" ".join(c["text"].replace("\n", " ") for c in ne))
            last = "org_subunit"
        elif _is_upper_label(first["paras"][0]):
            out["other_fields"][first["text"].replace("\n", " ")] = value
            last = None
        else:
            out["other_fields"].setdefault("_bez_etykiety", []).append(" ".join(c["text"] for c in ne))
    path = [x for x in [out["org_unit"], *out["org_subunits"]] if x]
    out["org_unit_path"] = " / ".join(path) or None
    for k in ("office", "org_unit", "position_name", "position_symbol"):
        if not out[k]:
            warnings.append(f"Część I: brak pola {k}")
    return out


def _parse_acknowledgement(rows: list[list[dict]]) -> dict:
    cols: dict[str, int] = {}
    entries = []
    for row in rows:
        texts = [c["text"] for c in row]
        norms = [_norm(t) for t in texts]
        if any(n.startswith("imie i nazwisko") for n in norms):
            for i, n in enumerate(norms):
                if n.startswith("symbol"):
                    cols["symbol"] = i
                elif n.startswith("imie i nazwisko"):
                    cols["name"] = i
                elif n.startswith("data i podpis") or "podpis" in n:
                    cols["sign"] = i
            continue
        if not any(texts):
            continue

        def get(k):
            i = cols.get(k)
            return texts[i] if i is not None and i < len(texts) else ""

        sign = get("sign")
        entries.append({
            "position_symbol": get("symbol") or None,
            "employee": "[osoba]" if get("name") else None,
            "acceptance": (sign if _MARKER_RE.match(sign) else "[podpis/data]") if sign else None,
        })
    return {"present": bool(rows), "entries": entries}


def _parse_subordinates(rows: list[list[dict]], warnings: list[str]) -> dict:
    boxes = _all_boxes(rows)
    opts = []
    for b in boxes:
        n = _norm(b["label"])
        code = next((c for key, c in SUBORDINATE_CODES if key in n), "other")
        opts.append({"code": code, "label": b["label"], "checked": b["checked"]})
    selected = [o for o in opts if o["checked"]]
    if not opts:
        status = "not_found"
        warnings.append("Liczba podległych pracowników: nie znaleziono pól wyboru")
    elif not selected:
        status = "none_selected"
        warnings.append("Liczba podległych pracowników: żadne pole nie jest zaznaczone")
    elif len(selected) > 1:
        status = "multiple_selected"
        warnings.append("Liczba podległych pracowników: zaznaczono więcej niż jedno pole")
    else:
        status = "ok"
    return {
        "options": opts,
        "selected_codes": [o["code"] for o in selected],
        "selected_code": selected[0]["code"] if len(selected) == 1 else None,
        "status": status,
        "wording_manages_or_coordinates": any("koordynuje" in _norm(o["label"]) for o in selected),
        "raw": "\n".join(c["text"] for row in rows for c in row if c["text"]),
    }


_TASK_RE = re.compile(r"^\s*Zadanie\s*(\d+)\s*[:.)\-–]?\s*", re.IGNORECASE)


def _parse_tasks(rows: list[list[dict]]) -> list[dict]:
    tasks: list[dict] = []
    for row in rows:
        for c in _nonempty(row):
            for para in c["paras"]:
                m = _TASK_RE.match(para)
                if m:
                    tasks.append({"no": int(m.group(1)), "text": para[m.end():].strip()})
                elif tasks and not _is_upper_label(para):
                    tasks[-1]["text"] = (tasks[-1]["text"] + "\n" + para).strip()
                elif not _is_upper_label(para):
                    tasks.append({"no": None, "text": para})
    return tasks


def _parse_contacts(rows: list[list[dict]]) -> list[dict]:
    out = []
    for row in rows:
        for c in row:
            if not c["checkboxes"]:
                continue
            b = c["checkboxes"][0]
            desc = [t for t, hb in zip(c["paras"], c["para_has_box"]) if not hb]
            out.append({"frequency": b["label"], "checked": b["checked"], "description": "\n".join(desc) or None})
    rank = {k: i for i, k in enumerate(CONTACT_ORDER)}
    out.sort(key=lambda x: rank.get(_norm(x["frequency"]), 99))
    return out


def match_soft_competencies(raw: str) -> dict:
    """Dzieli listę „Kompetencje miękkie” i mapuje pozycje na id kryteriów (kontrakt C1)."""
    names_n = {cid: _norm(name) for cid, name in COMPETENCIES.items()}
    by_len = sorted(names_n.items(), key=lambda kv: -len(kv[1]))
    items_out, unmatched = [], []
    for item in re.split(r"[,;\n•·]+", raw or ""):
        item = re.sub(r"^[\s\-–—*]+|[\s.]+$", "", item)
        n = _norm(item)
        if not n:
            continue
        hits = []
        masked = f" {n} "
        for cid, nn in by_len:
            pat = re.compile(rf"(?<![a-z0-9]){re.escape(nn)}(?![a-z0-9])")
            m = pat.search(masked)
            if m:
                hits.append((m.start(), cid, "exact" if n == nn else "contains"))
                masked = pat.sub(lambda mm: " " * len(mm.group(0)), masked)
        if not hits:
            for alias, cid in sorted(SOFT_ALIASES.items(), key=lambda kv: -len(kv[0])):
                m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", masked)
                if m:
                    hits.append((m.start(), cid, "alias"))
                    break
        if not hits:
            close = difflib.get_close_matches(n, list(names_n.values()), n=1, cutoff=0.85)
            if close:
                cid = next(k for k, v in names_n.items() if v == close[0])
                hits.append((0, cid, "fuzzy"))
        if not hits:
            unmatched.append(item)
            continue
        for _, cid, kind in sorted(hits):
            items_out.append({"text": item, "id": cid, "name": COMPETENCIES[cid], "match": kind})
    ids: list[str] = []
    for it in items_out:
        if it["id"] not in ids:
            ids.append(it["id"])
    return {"raw": raw, "items": items_out, "ids": ids, "unmatched": unmatched}


def _extract_soft(text: str) -> str | None:
    """Tekst po „Kompetencje miękkie:” do końca komórki albo do kolejnego nagłówka „Xxx:”."""
    paras = text.split("\n")
    for i, para in enumerate(paras):
        m = re.search(r"kompetencje\s+mi[eę]kkie\s*:?", para, re.IGNORECASE)
        if not m:
            continue
        chunk = [para[m.end():].strip()]
        for nxt in paras[i + 1:]:
            if re.match(rf"^[{_PL_UPPER}][^,:]{{0,40}}:\s*$", nxt.strip()):
                break
            chunk.append(nxt.strip())
        return "\n".join(x for x in chunk if x)
    return None


def _req_pair(cells: list[dict]) -> dict:
    vals = [c["text"] or None for c in cells[1:3]]
    vals += [None] * (2 - len(vals))
    return {"required": vals[0], "additional": vals[1]}


def _strip_prefix(s: str | None, prefix: str) -> str | None:
    if not s:
        return None
    s = re.sub(rf"^\s*{prefix}\s*:?\s*", "", s, flags=re.IGNORECASE).replace("\n", " ").strip()
    return s or None


def _parse_competencies(rows: list[list[dict]], warnings: list[str]) -> dict:
    out: dict = {
        "education": None, "education_details": [], "training": None, "special_permissions": None,
        "languages": [], "other_knowledge": None, "soft_competencies": None,
        "experience": {"length": None, "kind": None, "kind_details": []},
    }
    last = None
    for row in rows:
        if not _nonempty(row):
            continue
        label = _norm(row[0]["text"]) if row else ""
        if label.startswith("kompetencje") and "wymagania" in _norm(" ".join(c["text"] for c in row)):
            continue
        if label.startswith("doswiadczenie zawodowe"):
            last = "experience_header"
            continue
        if label.startswith("wyksztalcenie"):
            out["education"] = _req_pair(row)
            last = "education"
        elif label.startswith("przeszkolenie"):
            out["training"] = _req_pair(row)
            last = None
        elif label.startswith("szczegolne uprawnienia"):
            out["special_permissions"] = _req_pair(row)
            last = None
        elif label.startswith("znajomosc jezykow"):
            vals = [c["text"] for c in row[1:]]
            for i in range(0, len(vals), 2):
                lang = _strip_prefix(vals[i], "Język obcy")
                level = _strip_prefix(vals[i + 1] if i + 1 < len(vals) else None, "Poziom")
                if lang or level:
                    out["languages"].append({"language": lang, "level": level,
                                             "requirement": "required" if i == 0 else "additional"})
            last = None
        elif label.startswith("inne kompetencje"):
            pair = _req_pair(row)
            out["other_knowledge"] = pair
            softs = []
            for req in ("required", "additional"):
                raw = _extract_soft(pair[req] or "")
                if raw is not None:
                    res = match_soft_competencies(raw)
                    res["requirement"] = req
                    softs.append(res)
            if softs:
                main = softs[0]
                if len(softs) > 1:
                    main = dict(main)
                    main["additional"] = softs[1]
                out["soft_competencies"] = main
            last = None
        elif label.startswith("dlugosc"):
            out["experience"]["length"] = _req_pair(row)
            last = None
        elif label.startswith("rodzaj doswiadczenia"):
            out["experience"]["kind"] = _req_pair(row)
            last = "experience_kind"
        elif not label:
            pair = _req_pair(row)
            if last == "education" and any(pair.values()):
                out["education_details"].append(pair)
            elif last == "experience_kind" and any(pair.values()):
                out["experience"]["kind_details"].append(pair)
    if out["soft_competencies"] is None:
        warnings.append("Nie znaleziono listy „Kompetencje miękkie” w sekcji wymaganych kompetencji")
    elif out["soft_competencies"]["unmatched"]:
        warnings.append("Kompetencje miękkie: nierozpoznane pozycje: " + "; ".join(out["soft_competencies"]["unmatched"]))
    return out


def _parse_part3(rows: list[list[dict]]) -> dict:
    approvals: list[dict] = []
    cur = None
    for row in rows:
        ne = _nonempty(row)
        if not ne:
            continue
        paras = [t for c in ne for t in c["paras"]]
        captions = [t for t in paras if t.startswith("(") and t.endswith(")")]
        markers = [t for t in paras if _MARKER_RE.match(t) and t not in captions]
        others = [t for t in paras if t not in captions and t not in markers]
        if len(ne) == 1 and not captions and not markers:
            cur = {"role": redact_names(ne[0]["text"].replace("\n", " ")), "person": None, "signature_markers": []}
            approvals.append(cur)
            continue
        if cur is None:
            cur = {"role": None, "person": None, "signature_markers": []}
            approvals.append(cur)
        if others:
            cur["person"] = "[osoba]"
        cur["signature_markers"].extend(markers)
    return {"approvals": approvals}


# --------------------------------------------------------------------------- API

def _read_input(path) -> tuple[bytes, str]:
    if isinstance(path, (bytes, bytearray)):
        return bytes(path), "osp.docx"
    if hasattr(path, "read"):
        return path.read(), os.path.basename(getattr(path, "name", "osp.docx"))
    p = Path(path)
    return p.read_bytes(), p.name


def parse_osp_docx(path, *, filename: str | None = None) -> dict:
    """Parsuje OSP (DOCX). `path`: ścieżka, bytes albo obiekt plikowy. Zwraca dict (assets/osp_schema.json)."""
    data, name = _read_input(path)
    name = filename or name
    if len(data) > MAX_DOCX_BYTES:
        raise OspParseError(f"Plik za duży ({len(data)} B > {MAX_DOCX_BYTES} B)")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise OspParseError("To nie jest plik DOCX (brak struktury ZIP)") from exc
    warnings: list[str] = []
    with zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise OspParseError("Brak word/document.xml – to nie jest dokument Word")
        if "word/vbaProject.bin" in names:
            warnings.append("Dokument zawiera makra (vbaProject.bin) – makra zignorowano")
        if zf.getinfo("word/document.xml").file_size > MAX_XML_BYTES:
            raise OspParseError("word/document.xml za duży")
        xml = zf.read("word/document.xml")
    if re.search(rb"<!DOCTYPE|<!ENTITY", xml):
        raise OspParseError("document.xml zawiera DTD/ENTITY – odrzucono ze względów bezpieczeństwa")
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    if body is None:
        raise OspParseError("Brak w:body w document.xml")
    if root.find(f".//{W}del") is not None or root.find(f".//{W}ins") is not None:
        warnings.append("Dokument zawiera śledzone zmiany – użyto tekstu po zmianach (bez usuniętych fragmentów)")

    sections, title = _split_sections(body)
    if not title or "opis stanowiska pracy" not in _norm(title):
        warnings.append("Nie rozpoznano tytułu „OPIS STANOWISKA PRACY…” – szablon może być inny niż w MC")
    for sec in ("purpose", "subordinates", "required_competencies"):
        if sec not in sections:
            warnings.append(f"Nie znaleziono sekcji: {sec}")

    def rows(key):
        return sections.get(key, [])

    tasks_dom = _parse_tasks(rows("tasks_dominant"))
    tasks_other = _parse_tasks(rows("tasks_other"))
    tasks_unclassified = _parse_tasks(rows("tasks"))
    if not (tasks_dom or tasks_other or tasks_unclassified):
        warnings.append("Nie znaleziono zadań stanowiska")

    purpose = "\n".join(c["text"] for row in rows("purpose") for c in row if c["text"]) or None
    authorizations = _options(_all_boxes(rows("authorizations")))
    extra_auth = _plain_text(rows("authorizations"))
    if extra_auth:
        authorizations["other_text"] = extra_auth
    planning = _options(_all_boxes(rows("planning_horizon")))
    planning["examples"] = _plain_text(rows("planning_horizon"), ("planowanie", "przyklady")) or None
    hindering = _options(_all_boxes(rows("hindering_factors")))
    hindering["examples"] = _plain_text(rows("hindering_factors"), ("przyklady",)) or None

    result = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "file": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "template_title": title,
        },
        "part1": _parse_part1(rows("part1"), warnings),
        "acknowledgement": _parse_acknowledgement(rows("acknowledgement")),
        "part2": {
            "purpose": purpose,
            "subordinates": _parse_subordinates(rows("subordinates"), warnings),
            "tasks": {"dominant": tasks_dom, "other": tasks_other, "unclassified": tasks_unclassified},
            "authorizations": authorizations,
            "complexity_creativity": _desc_examples(rows("complexity_creativity"), "opis"),
            "independence_initiative": _desc_examples(rows("independence_initiative"), "opis"),
            "planning_horizon": planning,
            "external_contacts": _parse_contacts(rows("external_contacts")),
            "hindering_factors": hindering,
            "required_competencies": _parse_competencies(rows("required_competencies"), warnings),
        },
        "part3": _parse_part3(rows("part3")),
        "warnings": warnings,
    }
    return result


def _fix_zip_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not info.flag_bits & 0x800:
        for enc in ("utf-8", "cp852"):
            try:
                return name.encode("cp437").decode(enc)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return name


def iter_docx_inputs(path) -> Iterator[tuple[str, bytes]]:
    """Zwraca (nazwa_pliku, bajty) dla pliku .docx, katalogu z .docx albo archiwum .zip (bez rozpakowywania na dysk)."""
    p = Path(path)
    if p.is_dir():
        for f in sorted(p.rglob("*.docx")):
            if not f.name.startswith("~$"):
                yield f.name, f.read_bytes()
    elif p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as zf:
            for info in zf.infolist():
                name = os.path.basename(_fix_zip_name(info).replace("\\", "/"))
                if info.is_dir() or not name.lower().endswith(".docx") or name.startswith("~$"):
                    continue
                if "__MACOSX" in info.filename or info.file_size > MAX_DOCX_BYTES:
                    continue
                yield name, zf.read(info)
    else:
        yield p.name, p.read_bytes()


def summarize(res: dict) -> str:
    p1, p2 = res["part1"], res["part2"]
    soft = (p2["required_competencies"].get("soft_competencies") or {}).get("ids", [])
    t = p2["tasks"]
    return (f"{res['source']['file']}: symbol={p1['position_symbol']!r} stanowisko={p1['position_name']!r} "
            f"podlegli={p2['subordinates']['selected_codes']} zadania={len(t['dominant'])}+{len(t['other'])}"
            f"+{len(t['unclassified'])} miekkie={soft} ostrzezenia={len(res['warnings'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parser OSP (DOCX) -> JSON")
    ap.add_argument("input", help="plik .docx, katalog z .docx albo archiwum .zip")
    ap.add_argument("--out", help="katalog wyjściowy na <slug>.json (bez tego JSON na stdout)")
    args = ap.parse_args(argv)
    results: dict[str, dict] = {}
    errors = 0
    for name, data in iter_docx_inputs(args.input):
        try:
            res = parse_osp_docx(data, filename=name)
        except (OspParseError, ET.ParseError) as exc:
            print(f"BŁĄD {name}: {exc}", file=sys.stderr)
            errors += 1
            continue
        slug = slugify(Path(name).stem)
        results[slug] = res
        print(summarize(res), file=sys.stderr)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for slug, res in results.items():
            (out / f"{slug}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Zapisano {len(results)} plik(ów) do {out}", file=sys.stderr)
    else:
        payload = next(iter(results.values())) if len(results) == 1 else results
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 1 if errors and not results else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
