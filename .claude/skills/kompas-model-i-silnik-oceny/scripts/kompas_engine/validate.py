"""Walidacja dokumentu oceny: (1) podzbiór JSON Schema na samej stdlib, (2) reguły formalne z przepisów."""
from __future__ import annotations

import re
from datetime import date, datetime

from .config import catalog_names, rule_source

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _type_ok(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[t])


def _resolve(schema: dict, root: dict) -> dict:
    ref = schema.get("$ref")
    if ref:
        node = root
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return node
    return schema


def schema_errors(value, schema: dict, root: dict | None = None, path: str = "$") -> list[dict]:
    """Obsługiwane słowa kluczowe: $ref, type, enum, required, properties, items, minItems, maxItems,
    minimum, maximum, minLength, format (date, date-time)."""
    root = root or schema
    schema = _resolve(schema, root)
    errs: list[dict] = []
    types = schema.get("type")
    if types:
        tlist = types if isinstance(types, list) else [types]
        if not any(_type_ok(value, t) for t in tlist):
            return [{"rule_id": "SCHEMA", "path": path, "message": f"Zły typ: oczekiwano {tlist}, jest {type(value).__name__}", "source": "evaluation_schema.json"}]
    if "enum" in schema and value not in schema["enum"]:
        errs.append({"rule_id": "SCHEMA", "path": path, "message": f"Wartość {value!r} spoza dozwolonych {schema['enum']}", "source": "evaluation_schema.json"})
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errs.append({"rule_id": "SCHEMA", "path": f"{path}.{req}", "message": "Brak wymaganego pola", "source": "evaluation_schema.json"})
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errs.extend(schema_errors(value[key], sub, root, f"{path}.{key}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append({"rule_id": "SCHEMA", "path": path, "message": f"Za mało elementów (min {schema['minItems']})", "source": "evaluation_schema.json"})
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append({"rule_id": "SCHEMA", "path": path, "message": f"Za dużo elementów (max {schema['maxItems']})", "source": "evaluation_schema.json"})
        if "items" in schema:
            for i, item in enumerate(value):
                errs.extend(schema_errors(item, schema["items"], root, f"{path}[{i}]"))
    if _type_ok(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append({"rule_id": "SCHEMA", "path": path, "message": f"Wartość < {schema['minimum']}", "source": "evaluation_schema.json"})
        if "maximum" in schema and value > schema["maximum"]:
            errs.append({"rule_id": "SCHEMA", "path": path, "message": f"Wartość > {schema['maximum']}", "source": "evaluation_schema.json"})
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append({"rule_id": "SCHEMA", "path": path, "message": "Puste pole", "source": "evaluation_schema.json"})
        fmt = schema.get("format")
        try:
            if fmt == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError
                date.fromisoformat(value)
            elif fmt == "date-time":
                datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errs.append({"rule_id": "SCHEMA", "path": path, "message": f"Zły format {fmt}: {value!r} (oczekiwano ISO)", "source": "evaluation_schema.json"})
    return errs


def _issue(config, rule_id, message, path=""):
    return {"rule_id": rule_id, "message": message, "path": path, "source": rule_source(config, rule_id)}


def _blank(text) -> bool:
    return not (text or "").strip()


def business_issues(doc: dict, config: dict) -> tuple[list[dict], list[dict]]:
    """Reguły formalne niezależne od wyniku (kryteria, skala, daty). Zwraca (errors, warnings)."""
    errors: list[dict] = []
    warnings: list[dict] = []
    form_id = doc.get("form")
    form = config["forms"].get(form_id)
    if form is None:
        return [_issue(config, "SCHEMA", f"Nieznany formularz {form_id!r}", "$.form")], []
    names = catalog_names(config)
    scale = config["scales"][form["scale"]]["points"]
    mandatory = form["mandatory_criteria"]
    crits = doc.get("criteria", [])
    ids = [c.get("id") for c in crits]

    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errors.append(_issue(config, "P-MANDATORY" if form["process"] == "periodic" else "F-SCALE", f"Powtórzone kryteria: {', '.join(dup)}", "$.criteria"))
    for m in mandatory:
        if m not in ids:
            rid = "P-MANDATORY" if form["process"] == "periodic" else "F-TOTAL"
            errors.append(_issue(config, rid, f"Brak obowiązkowego kryterium/elementu „{names.get(m, m)}” dla formularza {form_id}.", "$.criteria"))

    additional = []
    for i, c in enumerate(crits):
        cid, kind = c.get("id"), c.get("kind")
        path = f"$.criteria[{i}]"
        if cid not in names:
            errors.append(_issue(config, "P-MAX-ADDITIONAL", f"Kryterium {cid!r} nie występuje w załączniku nr 1 do rozp. 2016.", path))
            continue
        if form["process"] == "first":
            if cid not in mandatory or kind != "first_eval_element":
                errors.append(_issue(config, "F-TOTAL", f"Pierwsza ocena ma zamkniętą listę 5 elementów (§ 2 pkt 1 rozp. 2015); „{names[cid]}” jako {kind} jest niedozwolone.", path))
        else:
            if kind == "first_eval_element":
                errors.append(_issue(config, "P-MANDATORY", "Rodzaj first_eval_element nie występuje w ocenie okresowej.", path))
            elif cid in mandatory and kind != "mandatory":
                errors.append(_issue(config, "P-MAX-ADDITIONAL", f"„{names[cid]}” jest kryterium obowiązkowym tego arkusza – nie może być dodatkowym.", path))
            elif cid not in mandatory and kind == "mandatory":
                errors.append(_issue(config, "P-MANDATORY", f"„{names[cid]}” nie jest kryterium obowiązkowym arkusza {form_id}; oznacz je jako kryterium dodatkowe.", path))
            if kind == "additional":
                additional.append(cid)
        fp = c.get("final_points")
        if fp is not None and fp not in scale:
            rid = "F-SCALE" if form["process"] == "first" else "P-SCALE"
            errors.append(_issue(config, rid, f"Ocena {fp} pkt spoza skali {scale}.", f"{path}.final_points"))
        for j, r in enumerate(c.get("indicator_ratings") or []):
            iid = str(r.get("indicator_id", ""))
            if iid and not iid.startswith(f"{cid}."):
                warnings.append(_issue(config, "S-INDICATOR-POINTS", f"Wskaźnik {iid} nie należy do kryterium {cid}.", f"{path}.indicator_ratings[{j}]"))
    if len(additional) > form["max_additional_criteria"]:
        errors.append(_issue(config, "P-MAX-ADDITIONAL",
                             f"Wybrano {len(additional)} kryteria dodatkowe – dopuszczalne najwyżej {form['max_additional_criteria']} (§ 5 ust. 2 rozp. 2016).",
                             "$.criteria"))

    # Daty okresu (przypisy 6–7 arkuszy B/C)
    if form["process"] == "periodic":
        period = doc.get("period") or {}
        meeting = (doc.get("part1") or {}).get("criteria_meeting_date")
        if period.get("from") and meeting and period["from"] != meeting:
            warnings.append(_issue(config, "P-PERIOD-FROM", f"Data „od” ({period['from']}) powinna być datą zapoznania z kryteriami z Części I ({meeting}).", "$.period.from"))
        if period.get("from") and period.get("to") and period["from"] > period["to"]:
            errors.append(_issue(config, "P-PERIOD-TO", "Data „do” jest wcześniejsza niż data „od”.", "$.period"))
    else:
        if doc.get("exam") == "nie_dotyczy" and not doc.get("exam_exemption"):
            warnings.append(_issue(config, "F-EXAM", "Egzamin „nie dotyczy” – wskaż, który z trzech wyjątków § 10 ust. 3 rozp. 2015 zachodzi.", "$.exam_exemption"))
        if doc.get("exam") != "nie_dotyczy" and doc.get("exam_exemption"):
            warnings.append(_issue(config, "F-EXAM", "Podano wyjątek od egzaminu, ale pole egzaminu nie jest „nie dotyczy”.", "$.exam_exemption"))
        if not doc.get("unit_head"):
            warnings.append(_issue(config, "F-UNIT-HEAD", "Brak danych kierującego komórką organizacyjną (arkusz: dane i podpis kierującego; ocena w porozumieniu z nim – art. 38 ust. 2 ustawy).", "$.unit_head"))
    return errors, warnings


def outcome_issues(doc: dict, config: dict) -> tuple[list[dict], list[dict]]:
    """Reguły zależne od wyniku: uzasadnienie, wnioski rozwojowe, Część III."""
    errors: list[dict] = []
    warnings: list[dict] = []
    form = config["forms"][doc["form"]]
    result = doc.get("result")
    first = form["process"] == "first"
    if result == "negatywna" and _blank(doc.get("justification")):
        rid = "F-JUSTIFICATION" if first else "P-JUSTIFICATION"
        errors.append(_issue(config, rid, "Ocena negatywna wymaga uzasadnienia.", "$.justification"))
    if first:
        if result == "negatywna" and not _blank(doc.get("development_conclusions")):
            errors.append(_issue(config, "F-DEV-ONLY-POSITIVE", "Wnioski dotyczące rozwoju zawodowego sporządza się tylko przy pozytywnej pierwszej ocenie (przypis 8) – usuń je.", "$.development_conclusions"))
        if result == "pozytywna" and not _blank(doc.get("development_conclusions")) and not (doc.get("unit_head") or {}).get("agreement_confirmed"):
            warnings.append(_issue(config, "F-DEV-ONLY-POSITIVE", "Wnioski rozwojowe sporządza się w porozumieniu z kierującym komórką organizacyjną (§ 10 ust. 6 rozp. 2015) – potwierdź porozumienie.", "$.unit_head.agreement_confirmed"))
    else:
        if result is not None and _blank(doc.get("development_conclusions")):
            warnings.append(_issue(config, "P-IPRZ", "Uzupełnij wnioski dotyczące indywidualnego programu rozwoju zawodowego (element obowiązkowy oceny).", "$.development_conclusions"))
    return errors, warnings
