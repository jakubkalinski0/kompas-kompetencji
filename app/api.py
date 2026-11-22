"""API JSON /api/v1 – działający podzbiór kontraktu `kompas-dokumenty-i-terminy/assets/openapi.json`.

Dokumentacja: /docs (OpenAPI generowane przez FastAPI). W prototypie uwierzytelnianie to ciasteczko sesji
konta demo (to samo co w interfejsie); docelowo SSO urzędu i token Bearer (schemat w pełnym kontrakcie:
GET /api/v1/integrations/contract). Uprawnienia jak w UI: HR dostaje widok z białej listy pól (rbac.json),
decyzje podejmuje wyłącznie przełożony, a sugestię liczy reguła (nie LLM).
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import assistant_service, settings, workflow
from .skills import rbac

router = APIRouter(prefix="/api/v1")
CONTRACT = settings.SKILLS_DIR / "kompas-dokumenty-i-terminy" / "assets" / "openapi.json"


class DecisionIn(BaseModel):
    points: int = Field(description="Ocena cząstkowa ze skali arkusza: 1/3/5/7/9 (ocena okresowa) albo 3/5/7 (pierwsza ocena).")
    note: str | None = Field(default=None, max_length=1000, description="Opcjonalna notatka do śladu decyzji.")


class HistoryTurn(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    a: str = Field(default="", max_length=700)


class FormalQuestionIn(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    process: Literal["periodic", "first"] | None = None
    history: list[HistoryTurn] = Field(default_factory=list, max_length=2,
                                       description="Poprzednie tury rozmowy od najstarszej (pytania uzupełniające)")


def _ctx(request: Request):
    from .main import current_user, sandbox_of, store  # import leniwy: main importuje ten moduł
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Zaloguj się na konto demo (POST /login) – docelowo token Bearer z SSO urzędu.")
    return user, sandbox_of(request), store


def _visible(request: Request, pid: str) -> tuple[dict, dict, object]:
    user, sandbox, store = _ctx(request)
    proc = store.get_process(pid)
    if not proc or (proc.get("sandbox") and proc["sandbox"] != sandbox):
        raise HTTPException(404, "Nie ma takiego procesu.")
    if user["role"] == "przelozony" and proc["owner"] != user["id"]:
        raise HTTPException(404, "Nie ma takiego procesu.")
    return user, proc, store


def _evaluator(store, proc: dict) -> str:
    return (store.get_user(proc["owner"]) or {"full_name": proc["owner"]})["full_name"]


def _summary(proc: dict) -> dict:
    doc = proc.get("doc") or {}
    return {"process_id": proc["id"], "type": proc["kind"], "form": doc.get("form"), "status": proc["status"],
            "employee": proc["employee"]["full_name"], "updated_at": proc["updated_at"], "demo": bool(proc.get("demo"))}


@router.get("/processes", tags=["procesy"], summary="Lista procesów w zakresie roli")
def list_processes(request: Request) -> list[dict]:
    """Przełożony: własne procesy (skrót). HR: wszystkie procesy, widok z białej listy pól (bez ocen i notatek S-D-R)."""
    user, sandbox, store = _ctx(request)
    if user["role"] == "hr_admin":
        return [rbac.view_for_role(workflow.hr_record(p, _evaluator(store, p)), "hr_admin")
                for p in store.list_processes(sandbox)]
    return [_summary(p) for p in store.list_processes(sandbox, owner=user["id"])]


@router.get("/processes/{process_id}", tags=["procesy"], summary="Dokument oceny (kontrakt C3) – widok wg roli")
def get_process(request: Request, process_id: str) -> dict:
    user, proc, store = _visible(request, process_id)
    if user["role"] == "hr_admin":
        return rbac.view_for_role(workflow.hr_record(proc, _evaluator(store, proc)), "hr_admin")
    return {**_summary(proc), "document": workflow.evaluated(proc) if proc.get("doc") else None}


@router.get("/processes/{process_id}/deadlines", tags=["hr"], summary="Kalendarz czynności z podstawą prawną i flagami")
def get_deadlines(request: Request, process_id: str) -> dict:
    _, proc, store = _visible(request, process_id)
    return workflow.calendar_view(proc, _evaluator(store, proc))


@router.get("/processes/{process_id}/criteria/{criterion_id}/suggestion", tags=["ocena"],
            summary="Sugerowany poziom kryterium – reguła z jawnym wzorem, nie LLM")
def get_suggestion(request: Request, process_id: str, criterion_id: str) -> dict:
    user, proc, _ = _visible(request, process_id)
    if user["role"] != "przelozony":
        raise HTTPException(403, "Oceny wskaźników i sugestie widzi tylko przełożony.")
    try:
        return workflow.suggest(proc, criterion_id)
    except workflow.WorkflowError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/processes/{process_id}/criteria/{criterion_id}/decision", tags=["ocena"],
             summary="Ocena cząstkowa – zawsze decyzja przełożonego; odejście od sugestii trafia do śladu")
def post_decision(request: Request, process_id: str, criterion_id: str, body: DecisionIn) -> dict:
    user, proc, store = _visible(request, process_id)
    if user["role"] != "przelozony":
        raise HTTPException(403, "Decyzję o ocenie cząstkowej podejmuje wyłącznie przełożony.")
    if proc.get("demo"):
        raise HTTPException(409, "Proces demo jest tylko do podglądu.")
    try:
        entry = workflow.decide(proc, user, criterion_id, body.points, body.note)
    except workflow.WorkflowError as exc:
        raise HTTPException(422, str(exc)) from None
    store.save_process(proc)
    return {"audit_entry": entry, "result": workflow.evaluated(proc).get("result")}


@router.get("/processes/{process_id}/pdf", tags=["dokumenty"], summary="Arkusz PDF wg wzoru z rozporządzenia",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def get_pdf(request: Request, process_id: str) -> Response:
    """Przełożony: zawsze, gdy ocena jest kompletna. HR: tylko arkusz sporządzonej oceny (rbac.json: pdf:arkusz_final)."""
    user, proc, store = _visible(request, process_id)
    if user["role"] == "hr_admin" and proc["status"] not in ("do_podpisu", "zakonczona"):
        raise HTTPException(403, "HR pobiera tylko arkusz sporządzonej oceny.")
    try:
        data = workflow.pdf_bytes(proc, user)
    except workflow.WorkflowError as exc:
        raise HTTPException(422, str(exc)) from None
    if not proc.get("demo") and user["role"] == "przelozony":
        store.save_process(proc)
    return Response(data, media_type="application/pdf")


@router.post("/assistant/formal", tags=["asystent"],
             summary="Asystent formalny: odpowiedź wyłącznie z bazy wiedzy z cytatami albo jawna odmowa")
def assistant_formal(request: Request, body: FormalQuestionIn) -> dict:
    user, sandbox, store = _ctx(request)
    if user["role"] != "przelozony":
        raise HTTPException(403, "Asystent jest dostępny dla przełożonego.")
    res = assistant_service.ask_formal(body.question, body.process, sandbox,
                                       history=[h.model_dump() for h in body.history],
                                       custom=store.list_kb_sources(sandbox))
    keys = ("answer", "refused", "refusal_reason", "source", "citations", "latency_s", "followup")
    return {k: res.get(k) for k in keys} | {"model": (res.get("llm") or {}).get("model")}


@router.post("/integrations/ezd/export/{process_id}", tags=["integracje"], status_code=202,
             summary="PROPOZYCJA (mock): pakiet oceny do EZD RP – metadane + PDF arkusza")
def ezd_export(request: Request, process_id: str) -> dict:
    """Buduje pakiet, który adapter EZD RP przekazałby do systemu (w prototypie nic nie jest wysyłane).
    Pakiet nie zawiera notatek S-D-R, sugestii systemu ani rozmów z asystentem."""
    user, proc, store = _visible(request, process_id)
    if proc["status"] not in ("do_podpisu", "zakonczona"):
        raise HTTPException(409, "Do EZD trafia sporządzona ocena – najpierw wygeneruj arkusz.")
    pdf = workflow.pdf_bytes(proc, user)
    doc = workflow.evaluated(proc)
    return {
        "status": "mock – nie wysłano (adapter do potwierdzenia z API EZD RP)",
        "metadata": {"process_id": proc["id"], "rodzaj": "pierwsza ocena" if proc["kind"] == "first" else "ocena okresowa",
                     "arkusz": workflow.FORM_LABELS[doc["form"]], "oceniany": doc["employee"]["full_name"],
                     "komorka": doc["employee"].get("unit"), "oceniajacy": doc["evaluator"]["full_name"],
                     "wynik": doc.get("result"), "data_rozmowy": doc.get("interview_date"),
                     "kategoria_archiwalna": "do ustalenia z JRWA urzędu"},
        "attachments": [{"name": f"arkusz_{proc['id']}.pdf", "media_type": "application/pdf", "size": len(pdf),
                         "sha256": hashlib.sha256(pdf).hexdigest()}],
    }


@router.get("/integrations/contract", tags=["integracje"],
            summary="Pełny proponowany kontrakt API (OpenAPI 3.1), w tym EZD RP i import z systemu kadrowego (np. QNT)")
def integration_contract() -> JSONResponse:
    return JSONResponse(json.loads(CONTRACT.read_text(encoding="utf-8")))
