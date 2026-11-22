"""Filtr widoku wg roli (RBAC) – czysta stdlib, konfiguracja w assets/rbac.json.

Użycie:
    python rbac.py --role hr_admin --input dokument_lub_proces.json [--rbac assets/rbac.json]

Zasada: HR (hr_admin) dostaje tylko pola z białej listy (statusy, terminy, log przypomnień);
pozostałe role poza przełożonym dostają dokument bez pól prywatnych (notatki S-D-R, czat asystenta rozmowy).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

DEFAULT_RBAC = Path(__file__).resolve().parent.parent / "assets" / "rbac.json"


def load_rbac(path: Path = DEFAULT_RBAC) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def can(rbac: dict, role: str, permission: str) -> bool:
    return permission in rbac["roles"].get(role, {}).get("permissions", [])


def _drop(obj, parts):
    if not parts or obj is None:
        return
    head, rest = parts[0], parts[1:]
    if head.endswith("[]"):
        items = obj.get(head[:-2]) if isinstance(obj, dict) else None
        for item in items or []:
            _drop(item, rest)
    elif not rest:
        if isinstance(obj, dict):
            obj.pop(head, None)
    elif isinstance(obj, dict):
        _drop(obj.get(head), rest)


def _allow(obj: dict, fields: list) -> dict:
    out: dict = {}
    for f in fields:
        head, _, sub = f.partition(".")
        if head not in obj:
            continue
        if not sub:
            out[head] = copy.deepcopy(obj[head])
        elif isinstance(obj[head], dict) and sub in obj[head]:
            out.setdefault(head, {})[sub] = copy.deepcopy(obj[head][sub])
    return out


def view_for_role(doc: dict, role: str, rbac: dict | None = None) -> dict:
    rbac = rbac or load_rbac()
    if role not in rbac["roles"]:
        raise PermissionError(f"Nieznana rola: {role}")
    spec = rbac["roles"][role]
    if spec["view"] == "full":
        return copy.deepcopy(doc)
    if spec["view"] == "allowlist":
        return _allow(doc, spec["allow_fields"])
    red = copy.deepcopy(doc)
    for path in rbac["private_fields"]:
        _drop(red, path.split("."))
    return red


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--rbac", default=str(DEFAULT_RBAC))
    a = ap.parse_args(argv)
    doc = json.loads(Path(a.input).read_text(encoding="utf-8"))
    print(json.dumps(view_for_role(doc, a.role, load_rbac(Path(a.rbac))), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
