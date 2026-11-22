"""Asystent formalny w aplikacji: klasa Assistant ze skilla kompas-asystent-ai + limity zapytań + HTML cytatów.

- Retrieval: na Render bez Ollamy → sam BM25 (`KOMPAS_EMBEDDINGS=0`); pomiar wpływu w README i docs/eval/.
- LLM: `LLMProvider.from_env()` (Groq przez API zgodne z OpenAI albo Ollama). Klucz tylko w zmiennej
  środowiskowej `LLM_API_KEY`, nigdy w repozytorium.
- Limity chronią darmowy plan Groq: wywołania LLM na minutę (instancja) i na godzinę (sesja).
  Odpowiedzi z FAQ i odmowy regułą nie wywołują modelu, więc limitu nie zużywają.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import threading
import time
from collections import defaultdict, deque

from markupsafe import Markup, escape

from . import settings
from .skills import Assistant, llm_provider

_session_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("kompas_session", default=None)
_lock = threading.Lock()
_assistant: Assistant | None = None


class SlidingLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = SlidingLimiter()


def _limited(provider):
    """Opakowuje provider.chat limitem; przekroczenie = LLMError, który Assistant pokazuje jako komunikat."""
    original = provider.chat

    def chat(messages, **kw):
        if not LIMITER.allow("global", settings.LLM_CALLS_PER_MIN, 60):
            raise llm_provider.LLMError("chwilowy limit zapytań – spróbuj ponownie za minutę.")
        key = _session_key.get()
        if key and not LIMITER.allow(f"s:{key}", settings.LLM_CALLS_PER_SESSION_HOUR, 3600):
            raise llm_provider.LLMError("limit pytań w tej sesji demo na godzinę – spróbuj później.")
        return original(messages, **kw)

    provider.chat = chat
    return provider


def get_assistant() -> Assistant:
    global _assistant
    with _lock:
        if _assistant is None:
            provider = _limited(llm_provider.LLMProvider.from_env())
            _assistant = Assistant(settings.DATA_DIR / "kb" / "kb_chunks.jsonl", provider=provider,
                                   cache_dir=settings.CACHE_DIR, use_embeddings=settings.USE_EMBEDDINGS)
        return _assistant


def reset(provider=None) -> None:
    """Testy: podmiana providera (atrapa LLM) i wyczyszczenie limitów."""
    global _assistant
    with _lock:
        _assistant = None
        _derived.clear()
        LIMITER.reset()
        if provider is not None:
            _assistant = Assistant(settings.DATA_DIR / "kb" / "kb_chunks.jsonl", provider=_limited(provider),
                                   cache_dir=settings.CACHE_DIR, use_embeddings=False)


# Źródła wgrane przez administratora są w sesji demo (piaskownicy) – każda sesja ma własny indeks BM25,
# budowany przy pierwszym pytaniu po zmianie listy źródeł (ok. 0,1 s dla ~400 jednostek).
_derived: dict[str, tuple[str, Assistant, Assistant]] = {}


def assistant_for(custom: list[dict] | None, key: str | None) -> Assistant:
    base = get_assistant()
    if not custom:
        return base
    sig = "|".join(f"{s['source_id']}@{s['created_at']}" for s in custom)
    with _lock:
        hit = _derived.get(key or "")
        if hit and hit[0] == sig and hit[2] is base:
            return hit[1]
    derived = base.with_extra_chunks([c for s in custom for c in s["chunks"]])
    with _lock:
        if len(_derived) > 64:
            _derived.clear()
        _derived[key or ""] = (sig, derived, base)
    return derived


def describe() -> dict:
    a = get_assistant()
    d = a.llm.describe()
    d["retrieval"] = "hybryda BM25 + embeddingi" if settings.USE_EMBEDDINGS else "BM25 (bez embeddingów)"
    d["kb_units"] = len(a.chunks)
    return d


UNAVAILABLE = ("Asystent jest chwilowo niedostępny – darmowe API modelu ma limit zapytań na minutę albo nie odpowiada. "
               "Spróbuj ponownie za minutę. Odpowiedzi z zestawu pytań i odpowiedzi oraz odmowy działają bez modelu.")


# Powody odmowy z modułu asystenta są techniczne (służą też raportom ewaluacji) – przełożony widzi je po polsku,
# a oryginał zostaje w polu detail („szczegół techniczny” w podpowiedzi).
PUBLIC_REASONS = (
    ("prośba o decyzję", "pytanie dotyczy oceny konkretnej osoby, a o niej decyduje przełożony"),
    ("retrieval poniżej progu", "w źródłach nie ma fragmentu, który odpowiadałby na to pytanie"),
    ("odpowiedź LLM bez poprawnego cytatu", "odpowiedź modelu nie miała poprawnego cytatu, więc jej nie pokazano"),
    ("LLM: brak podstaw", "model nie znalazł podstawy w źródłach"),
    ("reguła: wnioski rozwojowe", "przy negatywnej pierwszej ocenie nie sporządza się wniosków rozwojowych"),
    ("zła akcja", "asystent nie zna tego polecenia"),
)


def _friendly(res: dict) -> dict:
    """Błąd LLM (limit 429, timeout, brak klucza) → zrozumiały komunikat; szczegół techniczny tylko w polu detail."""
    if res.get("refusal_reason") == "błąd LLM":
        res["detail"] = res.get("error") or res.get("answer")
        res["answer"] = UNAVAILABLE
        res["refusal_reason"] = "model chwilowo niedostępny"
        return res
    reason = res.get("refusal_reason") or ""
    for prefix, text in PUBLIC_REASONS:
        if reason.startswith(prefix):
            if reason != prefix and not res.get("detail"):
                res["detail"] = reason
            res["refusal_reason"] = text
            break
    return res


MAX_HISTORY = 2


def parse_history(raw: list[str]) -> list[dict]:
    """Historia rozmowy z formularza (ukryte pola przy wcześniejszych odpowiedziach, najnowsza pierwsza)."""
    out = []
    for item in raw[:MAX_HISTORY]:
        try:
            h = json.loads(item)
        except (TypeError, ValueError):
            continue
        if isinstance(h, dict) and isinstance(h.get("q"), str) and h["q"].strip():
            a = h.get("a") if isinstance(h.get("a"), str) else ""
            out.append({"q": h["q"][:500], "a": a[:700]})
    return list(reversed(out))  # model dostaje tury od najstarszej


def ask_formal(question: str, process: str | None, session_key: str | None, history: list[dict] | None = None,
               custom: list[dict] | None = None) -> dict:
    handle = _session_key.set(session_key)
    try:
        ctx = {"process": process} if process in ("periodic", "first") else {}
        if history:
            ctx["history"] = history
        return _friendly(assistant_for(custom, session_key).answer(question, "formal", ctx))
    finally:
        _session_key.reset(handle)


def history_value(q: str, res: dict) -> str:
    """Wartość ukrytego pola historii dla tej tury (pytanie + początek odpowiedzi bez cytatów)."""
    a = "" if res.get("refused") else _CITE.sub("", res.get("answer") or "")[:600]
    return json.dumps({"q": q, "a": a}, ensure_ascii=False)


def unit_text(chunk_id: str, custom: list[dict] | None = None, key: str | None = None) -> dict | None:
    return assistant_for(custom, key).retriever.by_id.get(chunk_id)


# ---------------------------------------------------------------- źródła bazy wiedzy (W22)
PUBLIC_SOURCES = {"ustawa_sc", "kprm_qa_oceny"}  # pobrane przez zespół z ELI Sejmu i gov.pl; reszta – materiały MC


def kb_sources(custom: list[dict] | None = None) -> dict:
    """Źródła bazy wiedzy z liczbą jednostek: materiały Partnera / źródła publiczne / wgrane w urzędzie / Q&A zespołu."""
    sources = json.loads((settings.DATA_DIR / "kb" / "sources.json").read_text(encoding="utf-8"))
    a = get_assistant()
    counts: dict[tuple, int] = defaultdict(int)
    for c in a.chunks:
        counts[(c["source_id"], c["doc_type"])] += 1
    rows = []
    for s in sources:
        rows.append(dict(s, units=counts.get((s["source_id"], s["doc_type"]), 0),
                         group="public" if s["source_id"] in PUBLIC_SOURCES else "partner"))
    custom_rows = [{k: v for k, v in s.items() if k != "chunks"} for s in custom or []]
    custom_units = sum(s["units"] for s in custom_rows)
    return {"partner": [r for r in rows if r["group"] == "partner"], "public": [r for r in rows if r["group"] == "public"],
            "custom": custom_rows, "faq_count": len(a.retriever.faq), "base_units": len(a.chunks),
            "total_units": len(a.chunks) + custom_units}


def kb_units(source_id: str, doc_type: str, custom: list[dict] | None = None) -> list[dict]:
    for s in custom or []:
        if s["source_id"] == source_id:
            return s["chunks"]
    return [c for c in get_assistant().chunks if c["source_id"] == source_id and c["doc_type"] == doc_type]


def faq_items() -> list[dict]:
    return get_assistant().retriever.faq


# ---------------------------------------------------------------- propozycje kryteriów dodatkowych z zadań OSP (LLM)
_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def osp_ai_candidates(osp: dict, form: str, employee: str, evaluator: str, session_key: str | None) -> dict:
    """Kandydaci na kryteria dodatkowe od modelu (kompas-analiza-osp: build_llm_prompt → LLM → validate_llm_output).

    Cel i zadania z OSP przechodzą przez privacy_shield przed wysłaniem (pola tekstowe OSP nie są anonimizowane);
    walidator przyjmuje tylko propozycje z dosłownym cytatem zadania (z tej samej, zamaskowanej wersji tekstu).
    """
    import copy

    from .skills import privacy_shield, propose_form
    model = propose_form.load_competency_model(settings.DATA_DIR / "competency_model.json")
    shield = privacy_shield.ShieldContext(employee=employee, evaluator=evaluator, others=[])
    masked = copy.deepcopy(osp)
    p2 = masked["part2"]
    if p2.get("purpose"):
        p2["purpose"] = privacy_shield.mask(p2["purpose"], shield).text
    for kind in ("dominant", "other", "unclassified"):
        for task in (p2.get("tasks") or {}).get(kind, []):
            task["text"] = privacy_shield.mask(task["text"], shield).text
    prompt = propose_form.build_llm_prompt(masked, form, model)
    llm = get_assistant().llm
    # gpt-oss na Groq liczy tokeny rozumowania do max_tokens – bez „low” odpowiedź JSON bywała pusta albo ucięta
    extra = json.loads(os.environ.get("KOMPAS_OSP_LLM_EXTRA", '{"reasoning_effort": "low"}') or "{}") \
        if getattr(llm, "provider", "") == "openai_compat" else None
    handle = _session_key.set(session_key)
    try:
        res = llm.chat([{"role": "system", "content": prompt["system"]}, {"role": "user", "content": prompt["user"]}],
                       temperature=0.1, max_tokens=2000, extra=extra)
    except llm_provider.LLMError as exc:
        return {"error": UNAVAILABLE, "detail": str(exc)}
    finally:
        _session_key.reset(handle)
    m = _JSON_OBJ.search(res.text or "")
    out = propose_form.validate_llm_output(m.group(0) if m else (res.text or ""), masked, form, model)
    out["llm"] = {"model": res.model, "cached": res.cached, "latency_s": res.latency_s}
    return out


# ---------------------------------------------------------------- asystent oceny zachowań (propozycje poziomów)
def behavior_proposals(proc: dict, cid: str, note: str, user: dict, session_key: str | None) -> dict:
    """Opis przełożonego → propozycje poziomów wskaźników kryterium z dosłownym fragmentem opisu jako dowodem.

    Nic nie zapisuje: propozycje zaznacza przełożony w formularzu wskaźników; poziom kryterium liczy silnik oceny.
    """
    from .skills import behavior_match, privacy_shield
    from .workflow import COMPETENCIES
    comp = COMPETENCIES[cid]
    head = (proc["doc"].get("unit_head") or {}).get("full_name")
    shield = privacy_shield.ShieldContext(employee=proc["employee"]["full_name"], evaluator=user["full_name"],
                                          others=[head] if head else [])
    llm = get_assistant().llm
    handle = _session_key.set(session_key)
    try:
        out = behavior_match.propose(llm, comp, note, shield, proc["kind"])
    except llm_provider.LLMError as exc:
        return {"error": UNAVAILABLE, "detail": str(exc), "proposals": []}
    finally:
        _session_key.reset(handle)
    out["preview"] = {"masked_text": out.pop("masked_note")}
    return out


# ---------------------------------------------------------------- asystent rozmowy
CONVERSATION_ACTIONS = {
    "questions": "Pytania na rozmowę",
    "feedback": "Informacja zwrotna (S-D-R)",
    "justification": "Szkic uzasadnienia oceny",
    "development": "Propozycje wniosków rozwojowych",
}


def conversation_context(proc: dict, user: dict, action: str, decided_result: str | None) -> dict:
    """Kontekst dla Assistant._conversation: osoby do maskowania, kryteria, notatki S-D-R przełożonego."""
    doc = proc["doc"]
    notes = [{"criterion": c.get("name") or c["id"], "note": r["sdr_note"]}
             for c in doc["criteria"] for r in c.get("indicator_ratings") or [] if r.get("sdr_note")]
    head = (doc.get("unit_head") or {}).get("full_name")
    return {"action": action, "process": proc["kind"], "form": doc["form"],
            "employee": proc["employee"]["full_name"], "evaluator": user["full_name"],
            "others": [head] if head else [], "criteria": [c["id"] for c in doc["criteria"]],
            "notes": notes, "decided_result": decided_result}


def privacy_preview(ctx: dict, question: str = "") -> dict:
    """To samo maskowanie co w Assistant._conversation, bez wywołania modelu – do panelu „Co wysyłamy do AI”."""
    from .skills import privacy_shield
    notes = "\n".join(f"- [{n['criterion']}] {n['note']}" for n in ctx["notes"])
    text = notes + (("\nPytanie przełożonego: " + question) if question else "")
    shield = privacy_shield.ShieldContext(employee=ctx["employee"], evaluator=ctx["evaluator"], others=ctx["others"])
    return privacy_shield.preview(text, shield) | {"notes_count": len(ctx["notes"])}


def ask_conversation(ctx: dict, question: str, session_key: str | None) -> dict:
    handle = _session_key.set(session_key)
    try:
        res = _friendly(get_assistant().answer(question, "conversation", ctx))
    finally:
        _session_key.reset(handle)
    res["preview"] = privacy_preview(ctx, question)
    return res


_QUESTION = re.compile(r"(?:^|\s)(?:\d+[.)]|[-*•])\s+([^?\n]{8,300}?\?)")


def extract_questions(text: str, limit: int = 12) -> list[str]:
    """Pytania z odpowiedzi akcji „Pytania na rozmowę” (punkty listy zakończone „?”) – do karty przygotowania."""
    out = []
    for m in _QUESTION.finditer((text or "").replace("**", "")):
        q = re.sub(r"\s+", " ", _CITE.sub("", m.group(1))).strip()
        if q and q not in out:
            out.append(q)
    return out[:limit]


# ---------------------------------------------------------------- HTML odpowiedzi
_CITE = re.compile(r"\[([A-Za-z0-9_:.\-ąćęłńóśźż]+)\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BULLET = re.compile(r"^\s*(?:[-•*]|&#8226;)\s+(.+)$")


def answer_html(res: dict, uid: str) -> Markup:
    """Tekst odpowiedzi z klikalnymi odnośnikami [n] do listy cytatów (escape przed podstawieniem)."""
    numbers = {c["id"]: i + 1 for i, c in enumerate(res.get("citations") or [])}
    text = str(escape(res.get("answer") or ""))

    def repl(m: re.Match) -> str:
        cid = m.group(1)
        n = numbers.get(cid)
        if not n:
            return m.group(0)
        return (f'<a class="cite-ref" href="#c-{uid}-{n}" data-cite="c-{uid}-{n}" '
                f'title="Pokaż źródło">[{n}]</a>')

    text = _CITE.sub(repl, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    # punkty listy („- ”, „• ”, „* ”) → <ul>; pozostałe linie rozdziela <br>
    out, items = [], []
    for line in text.split("\n"):
        m = _BULLET.match(line)
        if m:
            items.append(f"<li>{m.group(1)}</li>")
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        out.append(line + "<br>" if line.strip() else "<br>")
    if items:
        out.append("<ul>" + "".join(items) + "</ul>")
    html = "".join(out)
    html = re.sub(r"(<br>)+(<ul>)", r"\2", html)
    html = re.sub(r"(<br>){2,}", "<br><br>", html)
    return Markup(re.sub(r"(<br>)+$", "", html))
