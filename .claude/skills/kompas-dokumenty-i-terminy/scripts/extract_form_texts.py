"""Wyciąga dosłowne przypisy i nagłówki ze wzorów arkuszy (DOCX Partnera) do assets/form_texts.json.

Użycie:
    python extract_form_texts.py --input <katalog_materialow> --output <form_texts.json>

Czysta biblioteka standardowa (DOCX = ZIP + XML). Numeracja list w przypisach
(np. "1)", "–") jest odtwarzana z word/numbering.xml.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

FORMS = {
    "periodic_b": ("Ocena okresowa w służbie cywilnej", "Arkusz oceny B"),
    "periodic_c": ("Ocena okresowa w służbie cywilnej", "Arkusz oceny C"),
    "first_eval": ("Pierwsza ocena w służbie cywilnej", "Arkusz pierwszej oceny"),
}


def _numbering(z: zipfile.ZipFile) -> dict:
    """numId -> {ilvl: (numFmt, lvlText)}"""
    if "word/numbering.xml" not in z.namelist():
        return {}
    root = ET.fromstring(z.read("word/numbering.xml"))
    abstract = {}
    for an in root.findall(W + "abstractNum"):
        lvls = {}
        for lvl in an.findall(W + "lvl"):
            fmt = lvl.find(W + "numFmt")
            txt = lvl.find(W + "lvlText")
            lvls[lvl.get(W + "ilvl")] = (
                fmt.get(W + "val") if fmt is not None else "decimal",
                txt.get(W + "val") if txt is not None else "%1.",
            )
        abstract[an.get(W + "abstractNumId")] = lvls
    out = {}
    for num in root.findall(W + "num"):
        ref = num.find(W + "abstractNumId")
        if ref is not None:
            out[num.get(W + "numId")] = abstract.get(ref.get(W + "val"), {})
    return out


def _run_text(p) -> str:
    parts = []
    for el in p.iter():
        if el.tag == W + "t":
            parts.append(el.text or "")
        elif el.tag in (W + "tab", W + "br"):
            parts.append(" ")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _footnotes(z: zipfile.ZipFile) -> dict:
    numbering = _numbering(z)
    root = ET.fromstring(z.read("word/footnotes.xml"))
    result = {}
    for fn in root.findall(W + "footnote"):
        fid = fn.get(W + "id")
        if fid is None or int(fid) <= 0:
            continue
        counters: dict = {}
        lines = []
        for p in fn.findall(W + "p"):
            text = _run_text(p)
            if not text:
                continue
            numpr = p.find(f"{W}pPr/{W}numPr")
            prefix = ""
            if numpr is not None and numpr.find(W + "numId") is not None:
                num_id = numpr.find(W + "numId").get(W + "val")
                ilvl_el = numpr.find(W + "ilvl")
                ilvl = ilvl_el.get(W + "val") if ilvl_el is not None else "0"
                fmt, lvl_text = numbering.get(num_id, {}).get(ilvl, ("decimal", "%1)"))
                counters[(num_id, ilvl)] = counters.get((num_id, ilvl), 0) + 1
                if fmt == "bullet":
                    prefix = "–"
                else:
                    prefix = re.sub(r"%\d", str(counters[(num_id, ilvl)]), lvl_text)
            # przypis zaczyna się od znaku ")" po numerze odnośnika – zostawiamy sam tekst
            text = re.sub(r"^\)\s*", "", text)
            lines.append((prefix + " " + text).strip() if prefix else text)
        result[fid] = " ".join(lines) if len(lines) == 1 else "\n".join(lines)
    return result


def find_docx(material_dir: Path, folder: str, stem: str) -> Path:
    cands = sorted((material_dir / folder).glob(stem + "*.docx"))
    if not cands:
        cands = sorted(material_dir.rglob(stem + "*.docx"))
    if not cands:
        raise FileNotFoundError(f"Nie znaleziono '{stem}*.docx' w {material_dir}")
    return cands[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="katalog materiałów Partnera (MAT / materialy)")
    ap.add_argument("--output", required=True, help="ścieżka form_texts.json")
    args = ap.parse_args(argv)
    mat = Path(args.input)
    out = {"_info": "Przypisy dosłownie z DOCX wzorów arkuszy (word/footnotes.xml). Generowane przez extract_form_texts.py.",
           "forms": {}}
    for key, (folder, stem) in FORMS.items():
        path = find_docx(mat, folder, stem)
        data = path.read_bytes()
        with zipfile.ZipFile(path) as z:
            fns = _footnotes(z)
        out["forms"][key] = {
            "source_file": str(path.relative_to(mat)).replace("\\", "/"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "footnotes": fns,
        }
        print(f"{key}: {len(fns)} przypisów z {path.name}")
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
