"""Zgodność wyjścia parsera z assets/osp_schema.json (minimalny walidator stdlib: type/required/enum/const/$ref/anyOf)."""
import json
from pathlib import Path

from test_osp_synthetic import make_docx
from osp_parser import parse_osp_docx

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "assets" / "osp_schema.json").read_text(encoding="utf-8"))
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "null": type(None)}


def check(node, sch, path="$"):
    errs = []
    if "$ref" in sch:
        ref = SCHEMA
        for part in sch["$ref"].lstrip("#/").split("/"):
            ref = ref[part]
        return check(node, {**ref, **{k: v for k, v in sch.items() if k != "$ref"}}, path)
    if "anyOf" in sch:
        return [] if any(not check(node, s, path) for s in sch["anyOf"]) else [f"{path}: anyOf"]
    if "const" in sch and node != sch["const"]:
        errs.append(f"{path}: const")
    if "enum" in sch and node not in sch["enum"]:
        errs.append(f"{path}: enum {node!r}")
    if "type" in sch:
        types = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(isinstance(node, TYPES[t]) and not (t == "integer" and isinstance(node, bool)) for t in types):
            return errs + [f"{path}: type {type(node).__name__}"]
    if isinstance(node, dict):
        errs += [f"{path}.{k}: brak" for k in sch.get("required", []) if k not in node]
        for k, s in sch.get("properties", {}).items():
            if k in node:
                errs += check(node[k], s, f"{path}.{k}")
    if isinstance(node, list) and "items" in sch:
        for i, x in enumerate(node):
            errs += check(x, sch["items"], f"{path}[{i}]")
    return errs


def test_synthetic_output_matches_schema():
    assert check(parse_osp_docx(make_docx()), SCHEMA) == []


def test_partner_outputs_match_schema(partner_osps):
    for res in partner_osps.values():
        assert check(res, SCHEMA) == []
