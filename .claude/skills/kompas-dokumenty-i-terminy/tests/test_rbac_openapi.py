import json
from pathlib import Path

import rbac

SKILL = Path(__file__).resolve().parent.parent


def all_keys(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            all_keys(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            all_keys(v, acc)
    return acc


def test_hr_gets_no_sdr_nor_chat(example):
    doc = example("ewa_karta")
    doc["assistant_chat"] = [{"role": "user", "content": "poufne"}]
    doc["status"] = "w_trakcie"
    view = rbac.view_for_role(doc, "hr_admin")
    keys = all_keys(view)
    assert "sdr_note" not in keys and "assistant_chat" not in keys and "criteria" not in keys
    assert view["status"] == "w_trakcie" and view["employee"] == {"full_name": "Ewa Fikcyjna",
                                                                   "unit": "Departament Cyberbezpieczeństwa",
                                                                   "position": "Starszy specjalista"}


def test_unit_head_and_employee_redacted_but_keep_ratings(example):
    doc = example("anna_b")
    doc["assistant_chat"] = ["x"]
    for role in ("kierujacy_komorka", "pracownik"):
        view = rbac.view_for_role(doc, role)
        keys = all_keys(view)
        assert "sdr_note" not in keys and "assistant_chat" not in keys
        assert view["criteria"][0]["final_points"] == doc["criteria"][0]["final_points"]


def test_supervisor_full_view(example):
    doc = example("anna_b")
    assert rbac.view_for_role(doc, "przelozony") == doc


def test_permissions():
    r = rbac.load_rbac()
    assert rbac.can(r, "hr_admin", "reminders:send")
    assert not rbac.can(r, "hr_admin", "sdr:read")
    assert not rbac.can(r, "hr_admin", "assistant_chat:read")
    assert rbac.can(r, "przelozony", "sdr:read")


def test_openapi_parses_refs_resolve_and_roles_exist():
    spec = json.loads((SKILL / "assets" / "openapi.json").read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.1")
    roles = set(rbac.load_rbac()["roles"])
    text = json.dumps(spec)
    for ref in set(__import__("re").findall(r'"\$ref": "#/([^"]+)"', text)):
        node = spec
        for part in ref.split("/"):
            node = node[part]
    op_ids = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method == "parameters":
                continue
            op_ids.append(op["operationId"])
            assert op["responses"]
            assert set(op.get("x-roles", [])) <= roles, (path, method)
    assert len(op_ids) == len(set(op_ids))
    assert any("ezd" in p for p in spec["paths"]) and any("hr/import" in p for p in spec["paths"])
