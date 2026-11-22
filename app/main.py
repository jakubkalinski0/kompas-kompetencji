"""Kompas Kompetencji – FastAPI. Uruchomienie: uvicorn app.main:app --reload (lokalnie), na Render z $PORT.

Role demo (jedno kliknięcie, bez haseł – tylko fikcyjne persony): przełożony Marek Kierownik-Demo,
HR Zofia Kadrowa-Demo. HR dostaje widok z białej listy pól (rbac.json): bez ocen wskaźników,
notatek S-D-R i rozmów z asystentem.
"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import assistant_service, kb_upload, radar, seed, settings, workflow
from .skills import osp_parser, rbac
from .store import Store

APP_DIR = Path(__file__).resolve().parent
DEMO_LOGINS = ("marek", "zofia")
MAX_UPLOAD = 5 * 1024 * 1024

store = Store(settings.DB_PATH)
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    app.state.seed_info = seed.run(store)
    assistant_service.get_assistant()  # indeks BM25 przy starcie (bez sieci), żeby pierwsze pytanie nie czekało
    yield


app = FastAPI(
    title="Kompas Kompetencji",
    version="0.1.0",
    description="Prototyp: ocena okresowa i pierwsza ocena w służbie cywilnej z modelem kompetencji MC. "
                "Sugerowany poziom liczy reguła, decyzję podejmuje przełożony; asystent odpowiada z cytatem albo odmawia.",
    lifespan=lifespan,
)
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, session_cookie="kompas_session",
                   same_site="lax", https_only=settings.ON_RENDER, max_age=8 * 3600)
from . import api  # noqa: E402  API JSON /api/v1 (kontrakt OpenAPI pod /docs)

app.include_router(api.router)
# kroje interfejsu (self-hosted woff2): na Windows mimetypes bierze typ z rejestru i zwraca text/plain
mimetypes.add_type("font/woff2", ".woff2")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.mount("/fonts", StaticFiles(directory=settings.FONTS_DIR), name="fonts")


# ---------------------------------------------------------------- filtry szablonów
def fmt_date(value) -> str:
    if not value:
        return "—"
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def fmt_dt(value) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).astimezone(workflow.TZ).strftime("%d.%m.%Y, %H:%M")
    except ValueError:
        return str(value)


def fmt_pts(value) -> str:
    return "—" if value is None else f"{value} pkt"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Odmiana polska: 1 wskaźnik, 2–4 wskaźniki, 5+ wskaźników (12–14 → many)."""
    if n == 1:
        word = one
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = few
    else:
        word = many
    return f"{n} {word}"


RULE_CODE = re.compile(r"^[A-Z]+(?:-[A-Z0-9]+)+:\s*")      # „P-POSITIVE: …”, „F-EXAM: …” – kody reguł silnika
INTERNAL_MARK = re.compile(r"\s*\[~\s*([^\]]+)\]")         # „[~ nazwy efektów: literatura HR]” – adnotacja źródła
CERTAINTY_MARK = re.compile(r"\[[✓✔?~]\]\s*")              # „[✓] § 11 …” – znacznik pewności ze słownika reguł
RULE_BOOK = re.compile(r"\brozp(\d{4})\b")                  # „rozp2016” → „rozp. 2016”


def plain(text) -> str:
    """Tekst silnika dla przełożonego: bez kodu reguły i znaczników pewności; adnotacja „[~ …]” jako zwykły nawias."""
    s = RULE_CODE.sub("", str(text or ""))
    s = INTERNAL_MARK.sub(lambda m: " (" + m.group(1).replace(": ", " – ") + ")", s)
    s = CERTAINTY_MARK.sub("", s)
    s = RULE_BOOK.sub(lambda m: "rozp. " + m.group(1), s)
    return s[:1].upper() + s[1:] if s else s


def fmt_roman(n) -> str:
    """Cyfry rzymskie I–X dla numerów kroków i sekcji."""
    table = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    try:
        v = int(n)
    except (TypeError, ValueError):
        return str(n or "")
    if v <= 0:
        return str(v)
    out = []
    for k, sym in table:
        while v >= k:
            out.append(sym)
            v -= k
    return "".join(out)


_TABLET_UA = re.compile(r"iPad|Tablet|PlayBook|Silk", re.I)
_PHONE_UA = re.compile(r"iPhone|iPod|Windows Phone|IEMobile|Opera Mini|Opera Mobi|BlackBerry|BB10|\bMobile\b", re.I)


def is_mobile_request(request: Request | None) -> bool:
    """Prawdziwe wykrywanie smartfona po nagłówkach HTTP (Sec-CH-UA-Mobile / User-Agent), nie po szerokości okna."""
    if not request:
        return False
    ch_mobile = (request.headers.get("sec-ch-ua-mobile") or "").strip()
    if ch_mobile == "?1":
        return True
    ua = request.headers.get("user-agent") or ""
    if _TABLET_UA.search(ua):
        return False
    return bool(_PHONE_UA.search(ua))


def finalize_arrows(value):
    """Spójne lotkowe strzałki ↣ / ↢ w całym renderowanym HTML (wzory, uwagi, odpowiedzi asystenta)."""
    if isinstance(value, Markup):
        s = str(value)
        return Markup(s.replace("→", "↣").replace("←", "↢")) if ("→" in s or "←" in s) else value
    if isinstance(value, str):
        return value.replace("→", "↣").replace("←", "↢") if ("→" in value or "←" in value) else value
    return value


templates.env.finalize = finalize_arrows
templates.env.filters.update(d=fmt_date, dt=fmt_dt, pts=fmt_pts, plural=plural, plain=plain, roman=fmt_roman)
templates.env.globals.update(
    FORM_LABELS=workflow.FORM_LABELS, FORM_SCOPE=workflow.FORM_SCOPE, STEPS=workflow.STEPS_PERIODIC,
    LEVELS=workflow.LEVELS, ROLE_LABELS=workflow.ROLE_LABELS, CATALOG=workflow.CATALOG,
    STATUS_LABELS=workflow.deadlines.STATUS_LABELS, TRAIL_LABELS=workflow.TRAIL_LABELS,
    INDICATOR_TEXT=workflow.INDICATOR_TEXT, is_mobile_request=is_mobile_request,
)


# ---------------------------------------------------------------- sesja i role
class Redirect(Exception):
    def __init__(self, url: str):
        self.url = url


@app.exception_handler(Redirect)
async def _redirect(request: Request, exc: Redirect):
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": exc.url})
    return RedirectResponse(exc.url, status_code=303)


@app.exception_handler(workflow.WorkflowError)
async def _workflow_error(request: Request, exc: workflow.WorkflowError):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": str(exc)}, status_code=422)
    if request.headers.get("HX-Request"):
        return HTMLResponse(f'<p class="flash error" role="alert">{escape(str(exc))}</p>', status_code=422)
    return templates.TemplateResponse(request, "error.html", {"user": current_user(request), "code": 422,
                                                              "detail": str(exc)}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    user = current_user(request)
    return templates.TemplateResponse(request, "error.html", {"user": user, "code": exc.status_code,
                                                              "detail": exc.detail}, status_code=exc.status_code)


def current_user(request: Request) -> dict | None:
    return store.get_user(request.session.get("uid"))


def sandbox_of(request: Request) -> str:
    sb = request.session.get("sandbox")
    if not sb:
        sb = secrets.token_hex(8)
        request.session["sandbox"] = sb
    return sb


def need(*roles: str):
    def dep(request: Request) -> dict:
        user = current_user(request)
        if not user:
            raise Redirect("/login")
        if roles and user["role"] not in roles:
            if user["role"] == "hr_admin":
                raise HTTPException(403, "Ten widok jest dostępny tylko dla przełożonego. Rola HR nie widzi ocen "
                                         "wskaźników, notatek S-D-R ani rozmów z asystentem (minimalizacja danych, "
                                         "uprawnienia według roli).")
            raise HTTPException(403, "Nie masz dostępu do tego widoku.")
        return user
    return dep


SUPERVISOR = need("przelozony")
HR = need("hr_admin")


def flash(request: Request, text: str, kind: str = "info") -> None:
    request.session.setdefault("flash", []).append({"text": text, "kind": kind})


def page(request: Request, name: str, user: dict | None, status_code: int = 200, **ctx) -> HTMLResponse:
    msgs = request.session.pop("flash", [])
    return templates.TemplateResponse(request, name, {"user": user, "flash": msgs, **ctx}, status_code=status_code)


def load_proc(request: Request, pid: str, user: dict, editable: bool = False, kind: str | None = None) -> dict:
    proc = store.get_process(pid)
    if not proc or proc["owner"] != user["id"] or (proc.get("sandbox") and proc["sandbox"] != sandbox_of(request)):
        raise HTTPException(404, "Nie ma takiej oceny albo należy ona do innej sesji demo.")
    if kind:
        require_kind(proc, kind)
    if editable and proc.get("demo"):
        flash(request, "To przykładowa ocena demo – można ją tylko przeglądać. Żeby przejść całą ścieżkę, rozpocznij nową ocenę.")
        raise Redirect(f"/procesy/{pid}/podsumowanie")
    return proc


def step_url(proc: dict, step: str) -> str:
    if step == "wskazniki" and proc.get("doc"):
        first = next((c["id"] for c in proc["doc"]["criteria"] if c.get("final_points") is None),
                     proc["doc"]["criteria"][0]["id"])
        return f"/procesy/{proc['id']}/wskazniki/{first}"
    return f"/procesy/{proc['id']}/{step}"


templates.env.globals.update(step_url=step_url, step_state=workflow.step_state)


def proc_ctx(proc: dict, active: str) -> dict:
    nxt = None if proc.get("demo") else workflow.calendar_view(proc, evaluator_name(proc)).get("next")
    steps = workflow.steps_for(proc)
    step_no = next((i for i, (key, _) in enumerate(steps, 1) if key == active), None)
    return {"proc": proc, "doc": proc.get("doc"), "active": active, "steps_state": workflow.step_state(proc),
            "steps": steps, "assistant_process": proc["kind"], "next_deadline": nxt, "step_no": step_no,
            "step_basis": workflow.STEP_BASIS.get((proc["kind"], active))}


def require_kind(proc: dict, kind: str) -> None:
    if proc["kind"] != kind:
        raise HTTPException(404, "Ten krok nie występuje w tej ścieżce oceny.")


# ---------------------------------------------------------------- wejście
@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/hr" if user["role"] == "hr_admin" else "/pulpit", status_code=303)


@app.get("/design", response_class=HTMLResponse, include_in_schema=False)
def design_system(request: Request):
    """Przewodnik po systemie projektowym – komponenty z tego samego app.css co aplikacja (dostępny bez logowania)."""
    return page(request, "design.html", current_user(request))


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    users = [store.get_user(u) for u in DEMO_LOGINS]
    return page(request, "login.html", current_user(request), users=[u for u in users if u])


@app.post("/login", include_in_schema=False)
def login(request: Request, persona: str = Form(...)):
    if persona not in DEMO_LOGINS or not store.get_user(persona):
        raise HTTPException(400, "Nie ma takiego konta demo.")
    request.session["uid"] = persona
    sandbox_of(request)
    return RedirectResponse("/", status_code=303)


@app.post("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.pop("uid", None)
    return RedirectResponse("/login", status_code=303)


@app.get("/pulpit", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request, user: dict = Depends(SUPERVISOR)):
    procs = store.list_processes(sandbox_of(request), owner=user["id"])
    reminders = sorted(((r, p) for p in procs for r in p.get("reminders") or []), key=lambda x: x[0]["ts"], reverse=True)
    deadlines_by_id = {p["id"]: workflow.calendar_view(p, user["full_name"]).get("next") for p in procs if not p.get("demo")}
    results_by_id = {p["id"]: workflow.evaluated(p).get("result") for p in procs if p.get("doc")}
    return page(request, "dashboard.html", user, procs=procs, assistant_process="", next_step=workflow.next_step,
                reminders=reminders[:5], next_deadline=deadlines_by_id, results_by_id=results_by_id)


def evaluator_name(proc: dict) -> str:
    return (store.get_user(proc["owner"]) or {"full_name": proc["owner"]})["full_name"]


@app.get("/hr", response_class=HTMLResponse, include_in_schema=False)
def hr_panel(request: Request, user: dict = Depends(HR)):
    rows = [rbac.view_for_role(workflow.hr_record(p, evaluator_name(p)), "hr_admin")
            for p in store.list_processes(sandbox_of(request))]
    for r in rows:
        open_events = [e for e in r.get("events", []) if not e.get("done_on") and e["task"] != "sprzeciw"]
        r["next"] = min(open_events, key=lambda e: e["days_left"] if e["days_left"] is not None else 10 ** 6, default=None)
    return page(request, "hr.html", user, rows=rows)


@app.post("/hr/procesy/{pid}/przypomnienie", include_in_schema=False)
def hr_remind(request: Request, pid: str, user: dict = Depends(HR)):
    proc = next((p for p in store.list_processes(sandbox_of(request)) if p["id"] == pid), None)
    if not proc:
        raise HTTPException(404, "Nie ma takiej oceny.")
    try:
        entries = workflow.send_reminder(proc, user, evaluator_name(proc))
    except workflow.WorkflowError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse("/hr", status_code=303)
    store.save_process(proc)
    flash(request, f"Wysłano przypomnienie do: {entries[0]['recipient']} – „{entries[0]['subject']}” "
                   "(w prototypie bez wysyłki e-maila – przypomnienie widać na pulpicie przełożonego).", "ok")
    return RedirectResponse("/hr", status_code=303)


# ---------------------------------------------------------------- nowy proces
@app.get("/procesy/nowy", response_class=HTMLResponse, include_in_schema=False)
def new_process_page(request: Request, user: dict = Depends(SUPERVISOR), sciezka: str = "okresowa"):
    kind = "first" if sciezka == "pierwsza" else "periodic"
    employees = [e for e in store.list_employees() if e.get("process") == kind]
    return page(request, "process/start.html", user, employees=employees, kind=kind, assistant_process=kind,
                unit_head_default=store.get_user("barbara"))


def _iso_or_none(value: str) -> str | None:
    try:
        return date.fromisoformat(value.strip()).isoformat() if value and value.strip() else None
    except ValueError:
        return None


@app.post("/procesy", include_in_schema=False)
def create_process(request: Request, user: dict = Depends(SUPERVISOR), employee_id: str = Form(...),
                   kind: str = Form("periodic"), new_full_name: str = Form(""), new_position: str = Form(""),
                   new_unit: str = Form(""), new_corps_status: str = Form("pracownik_sc"),
                   new_previous_date: str = Form(""), new_employment_start: str = Form(""),
                   new_contract_end: str = Form("")):
    kind = "first" if kind == "first" else "periodic"
    back = "/procesy/nowy" + ("?sciezka=pierwsza" if kind == "first" else "")
    if employee_id == "nowy":
        name = new_full_name.strip()
        if len(name) < 3 or not new_position.strip():
            flash(request, "Podaj imię i nazwisko (fikcyjne) oraz stanowisko ocenianego.", "error")
            return RedirectResponse(back, status_code=303)
        emp = {"persona_id": None, "full_name": name[:120], "position": new_position.strip()[:160],
               "unit": new_unit.strip()[:160], "process": kind,
               "corps_status": "urzednik_sc" if new_corps_status == "urzednik_sc" and kind == "periodic" else "pracownik_sc",
               "previous_evaluation_date": _iso_or_none(new_previous_date) if kind == "periodic" else None,
               "employment_start": _iso_or_none(new_employment_start) if kind == "first" else None,
               "contract_end": _iso_or_none(new_contract_end) if kind == "first" else None}
        if kind == "first" and not emp["employment_start"]:
            flash(request, "Podaj datę nawiązania stosunku pracy – od niej liczą się terminy pierwszej oceny.", "error")
            return RedirectResponse(back, status_code=303)
    else:
        emp = store.get_employee(employee_id)
        if not emp:
            raise HTTPException(400, "Nie ma takiej osoby na liście ocenianych.")
    if kind == "first":
        head = store.get_user("barbara") or {"full_name": "", "position": ""}
        proc = workflow.new_first(user, sandbox_of(request), emp, head)
        first_step = "rozmowa-wstepna"
    else:
        proc = workflow.new_periodic(user, sandbox_of(request), emp)
        first_step = "osp"
    store.save_process(proc)
    return RedirectResponse(f"/procesy/{proc['id']}/{first_step}", status_code=303)


@app.get("/procesy/{pid}", include_in_schema=False)
def process_home(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user)
    return RedirectResponse(step_url(proc, "podsumowanie" if proc.get("demo") else workflow.next_step(proc)), status_code=303)


# ---------------------------------------------------------------- 1. OSP
def osp_samples() -> list[dict]:
    out = []
    for f in sorted((settings.DATA_DIR / "osp").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        p1 = d.get("part1") or {}
        out.append({"slug": f.stem, "position": p1.get("position_name") or f.stem, "unit": p1.get("org_unit") or "",
                    "symbol": p1.get("position_symbol") or ""})
    return out


@app.get("/procesy/{pid}/osp", response_class=HTMLResponse, include_in_schema=False)
def osp_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    return page(request, "process/osp.html", user, samples=osp_samples(), **proc_ctx(proc, "osp"))


@app.post("/procesy/{pid}/osp", include_in_schema=False)
async def osp_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR), action: str = Form(...),
                     sample: str = Form(""), file: UploadFile | None = File(None)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    if action == "skip":
        workflow.skip_osp(proc, user)
    elif action == "sample":
        slugs = {s["slug"] for s in osp_samples()}
        if sample not in slugs:
            raise HTTPException(400, "Nie ma takiego przykładowego OSP.")
        parsed = json.loads((settings.DATA_DIR / "osp" / f"{sample}.json").read_text(encoding="utf-8"))
        workflow.attach_osp(proc, user, parsed, "sample", (parsed.get("source") or {}).get("file") or sample)
    elif action == "upload":
        if file is None or not file.filename:
            flash(request, "Wybierz plik .docx z opisem stanowiska.", "error")
            return RedirectResponse(f"/procesy/{pid}/osp", status_code=303)
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            flash(request, "Plik jest za duży – limit to 5 MB.", "error")
            return RedirectResponse(f"/procesy/{pid}/osp", status_code=303)
        if not file.filename.lower().endswith(".docx"):
            flash(request, "Kompas czyta opisy stanowisk w formacie .docx (Word). Plik .doc lub PDF zapisz jako .docx.", "error")
            return RedirectResponse(f"/procesy/{pid}/osp", status_code=303)
        try:
            parsed = osp_parser.parse_osp_docx(data, filename=Path(file.filename).name)
        except osp_parser.OspParseError as exc:
            flash(request, f"Nie udało się odczytać OSP: {exc}", "error")
            return RedirectResponse(f"/procesy/{pid}/osp", status_code=303)
        workflow.attach_osp(proc, user, parsed, "upload", Path(file.filename).name)
    else:
        raise HTTPException(400, "Nie rozpoznano polecenia formularza – odśwież stronę i spróbuj ponownie.")
    store.save_process(proc)
    return RedirectResponse(f"/procesy/{pid}/arkusz", status_code=303)


# ---------------------------------------------------------------- 2. arkusz B/C
@app.get("/procesy/{pid}/arkusz", response_class=HTMLResponse, include_in_schema=False)
def form_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    if not proc["steps_done"]["osp"]:
        return RedirectResponse(f"/procesy/{pid}/osp", status_code=303)
    # pola OSP liczone w Pythonie: w Jinja `{}['items']` przy braku klucza zwraca metodę dict.items
    p2 = ((proc.get("osp") or {}).get("parsed") or {}).get("part2") or {}
    soft = ((p2.get("required_competencies") or {}).get("soft_competencies") or {}).get("items") or []
    subs = [o.get("label") for o in ((p2.get("subordinates") or {}).get("options") or []) if o.get("checked")]
    return page(request, "process/arkusz.html", user, osp_soft=[s.get("text") for s in soft], osp_subs=subs,
                **proc_ctx(proc, "arkusz"))


@app.post("/procesy/{pid}/arkusz", include_in_schema=False)
def form_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR), form: str = Form(...)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    try:
        workflow.confirm_form(proc, user, form)
    except workflow.WorkflowError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse(f"/procesy/{pid}/arkusz", status_code=303)
    store.save_process(proc)
    return RedirectResponse(f"/procesy/{pid}/kryteria", status_code=303)


# ---------------------------------------------------------------- 3. kryteria
@app.get("/procesy/{pid}/kryteria", response_class=HTMLResponse, include_in_schema=False)
def criteria_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    if not proc.get("doc"):
        return RedirectResponse(f"/procesy/{pid}/arkusz", status_code=303)
    return page(request, "process/kryteria.html", user, options=workflow.additional_options(proc),
                mandatory=[workflow.criterion(proc, c) for c in workflow.mandatory_for(proc["doc"]["form"])],
                competencies=workflow.COMPETENCIES, basis=workflow.MANDATORY_BASIS[proc["doc"]["form"]],
                **proc_ctx(proc, "kryteria"))


@app.post("/procesy/{pid}/kryteria", include_in_schema=False)
async def criteria_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    form = await request.form()
    selected = [str(x) for x in form.getlist("additional")]
    try:
        workflow.set_criteria(proc, user, selected)
    except workflow.WorkflowError as exc:
        opts = workflow.additional_options(proc)
        for o in opts:
            o["checked"] = o["id"] in selected
        return page(request, "process/kryteria.html", user, status_code=422, error=str(exc), options=opts,
                    mandatory=[workflow.criterion(proc, c) for c in workflow.mandatory_for(proc["doc"]["form"])],
                    competencies=workflow.COMPETENCIES, basis=workflow.MANDATORY_BASIS[proc["doc"]["form"]],
                    **proc_ctx(proc, "kryteria"))
    store.save_process(proc)
    return RedirectResponse(f"/procesy/{pid}/czesc-i", status_code=303)


@app.post("/procesy/{pid}/kryteria/ai", response_class=HTMLResponse, include_in_schema=False)
def criteria_ai(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    """Propozycje kryteriów dodatkowych od modelu – tylko z dosłownym cytatem zadania z OSP; wybór należy do przełożonego."""
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    parsed = (proc.get("osp") or {}).get("parsed")
    if not parsed or not proc.get("doc"):
        raise workflow.WorkflowError("Propozycje AI wymagają wczytanego OSP i wybranego arkusza.")
    ai = assistant_service.osp_ai_candidates(parsed, proc["doc"]["form"], proc["employee"]["full_name"],
                                             user["full_name"], request.session.get("sandbox"))
    if not ai.get("error"):
        proc["osp_ai"] = ai
        store.save_process(proc)
    return templates.TemplateResponse(request, "partials/_osp_ai.html", {"proc": proc, "ai": ai})


# ---------------------------------------------------------------- 4. Część I
@app.get("/procesy/{pid}/czesc-i", response_class=HTMLResponse, include_in_schema=False)
def part1_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    if not proc["steps_done"]["kryteria"]:
        return RedirectResponse(f"/procesy/{pid}/kryteria", status_code=303)
    hints = workflow.part1_hints(proc)
    part1 = proc["doc"].get("part1") or {}
    defaults = {
        "meeting": part1.get("criteria_meeting_date") or next((h["due"] for h in hints if h["task"] == "kryteria"), ""),
        "deadline": part1.get("evaluation_deadline") or next((h["due"] for h in hints if h["task"] == "ocena"), ""),
        "goals": part1.get("goals") or "",
    }
    return page(request, "process/czesc_i.html", user, hints=hints, defaults=defaults, **proc_ctx(proc, "czesc-i"))


@app.post("/procesy/{pid}/czesc-i", include_in_schema=False)
def part1_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR), meeting: str = Form(""),
                 deadline: str = Form(""), goals: str = Form("")):
    proc = load_proc(request, pid, user, editable=True, kind="periodic")
    try:
        workflow.set_part1(proc, user, meeting, deadline, goals)
    except workflow.WorkflowError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse(f"/procesy/{pid}/czesc-i", status_code=303)
    store.save_process(proc)
    return RedirectResponse(step_url(proc, "wskazniki"), status_code=303)


# ---------------------------------------------------------------- pierwsza ocena: rozmowa wstępna, warunki
@app.get("/procesy/{pid}/rozmowa-wstepna", response_class=HTMLResponse, include_in_schema=False)
def intro_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="first")
    calendar = workflow.first_calendar(proc)
    intro = proc["doc"].get("first_eval_intro") or {}
    due = {e["task"]: e for e in calendar}
    report = (intro.get("report_deadline") or {})
    defaults = {
        "employment_start": proc["employee"].get("employment_start") or "",
        "contract_end": proc["employee"].get("contract_end") or "",
        "intro": intro.get("intro_interview_date") or (due.get("rozmowa_wstepna") or {}).get("due") or "",
        "report_from": report.get("from") or ((due.get("sprawozdanie") or {}).get("window") or {}).get("from") or "",
        "report_to": report.get("to") or ((due.get("sprawozdanie") or {}).get("window") or {}).get("to") or "",
        "head_name": proc["doc"]["unit_head"].get("full_name") or "",
        "head_position": proc["doc"]["unit_head"].get("position") or "",
    }
    return page(request, "process/rozmowa_wstepna.html", user, calendar=calendar, defaults=defaults,
                **proc_ctx(proc, "rozmowa-wstepna"))


@app.post("/procesy/{pid}/rozmowa-wstepna", include_in_schema=False)
async def intro_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="first")
    form = await request.form()
    try:
        workflow.set_intro(proc, user, {k: str(v) for k, v in form.items()})
    except workflow.WorkflowError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse(f"/procesy/{pid}/rozmowa-wstepna", status_code=303)
    store.save_process(proc)
    return RedirectResponse(f"/procesy/{pid}/warunki", status_code=303)


@app.get("/procesy/{pid}/warunki", response_class=HTMLResponse, include_in_schema=False)
def conditions_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True, kind="first")
    if not proc["steps_done"].get("rozmowa-wstepna"):
        return RedirectResponse(f"/procesy/{pid}/rozmowa-wstepna", status_code=303)
    return page(request, "process/warunki.html", user, exemptions=workflow.EXEMPTION_LABELS,
                **proc_ctx(proc, "warunki"))


@app.post("/procesy/{pid}/warunki", include_in_schema=False)
def conditions_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR), exam: str = Form(""),
                      exam_exemption: str = Form(""), report: str = Form("")):
    proc = load_proc(request, pid, user, editable=True, kind="first")
    try:
        workflow.set_conditions(proc, user, exam, exam_exemption or None, report)
    except workflow.WorkflowError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse(f"/procesy/{pid}/warunki", status_code=303)
    store.save_process(proc)
    return RedirectResponse(step_url(proc, "wskazniki"), status_code=303)


# ---------------------------------------------------------------- 5. wskaźniki i decyzje
def compass_ctx(proc: dict, cid: str, saved: dict | None = None) -> dict:
    crit = workflow.criterion(proc, cid)
    if crit.get("suggestion") is None:
        workflow.suggest(proc, cid)
    ev = workflow.evaluated(proc)
    form = proc["doc"]["form"]
    return {"proc": proc, "crit": crit, "comp": workflow.COMPETENCIES[cid], "points": workflow.scale_points(form),
            "point_labels": workflow.scale_labels(form), "guard": [g for g in ev.get("guard", []) if g.get("criterion_id") == cid],
            "saved": saved, "next_cid": workflow.next_criterion(proc, cid) if saved else None}


@app.get("/procesy/{pid}/wskazniki", include_in_schema=False)
def indicators_home(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True)
    return RedirectResponse(step_url(proc, "wskazniki"), status_code=303)


@app.get("/procesy/{pid}/wskazniki/{cid}", response_class=HTMLResponse, include_in_schema=False)
def indicators_page(request: Request, pid: str, cid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True)
    gate = "rozmowa-wstepna" if proc["kind"] == "first" else "czesc-i"
    if not proc["steps_done"].get(gate):
        return RedirectResponse(f"/procesy/{pid}/{gate}", status_code=303)
    try:
        ctx = {**proc_ctx(proc, "wskazniki"), **compass_ctx(proc, cid)}
    except workflow.WorkflowError as exc:
        raise HTTPException(404, str(exc)) from None
    return page(request, "process/wskazniki.html", user, **ctx)


@app.post("/procesy/{pid}/wskazniki/{cid}/oceny", response_class=HTMLResponse, include_in_schema=False)
async def indicators_rate(request: Request, pid: str, cid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True)
    form = await request.form()
    workflow.update_ratings(proc, cid, {k: str(v) for k, v in form.items()})
    store.save_process(proc)
    return templates.TemplateResponse(request, "partials/_compass.html", compass_ctx(proc, cid))


@app.post("/procesy/{pid}/wskazniki/{cid}/ai", response_class=HTMLResponse, include_in_schema=False)
def indicators_ai(request: Request, pid: str, cid: str, user: dict = Depends(SUPERVISOR), note: str = Form("")):
    """Asystent oceny zachowań: opis przełożonego → propozycje poziomów wskaźników (nic się nie zapisuje samo)."""
    proc = load_proc(request, pid, user, editable=True)
    try:
        workflow.criterion(proc, cid)
    except workflow.WorkflowError as exc:
        raise HTTPException(404, str(exc)) from None
    text = note.strip()
    if len(text) < 20:
        return HTMLResponse('<p class="assist-hint">Opisz co najmniej jedno konkretne zachowanie: sytuację, '
                            'co pracownik zrobił i jaki był rezultat.</p>')
    res = assistant_service.behavior_proposals(proc, cid, text, user, sandbox_of(request))
    return templates.TemplateResponse(request, "partials/_behavior_ai.html",
                                      {"res": res, "proc": proc, "cid": cid, "comp": workflow.COMPETENCIES[cid]})


@app.post("/procesy/{pid}/wskazniki/{cid}/decyzja", response_class=HTMLResponse, include_in_schema=False)
def indicators_decide(request: Request, pid: str, cid: str, user: dict = Depends(SUPERVISOR),
                      points: int = Form(...), note: str = Form("")):
    proc = load_proc(request, pid, user, editable=True)
    try:
        entry = workflow.decide(proc, user, cid, points, note)
    except workflow.WorkflowError as exc:
        ctx = compass_ctx(proc, cid)
        ctx["error"] = str(exc)
        return templates.TemplateResponse(request, "partials/_compass.html", ctx, status_code=422)
    store.save_process(proc)
    if not request.headers.get("HX-Request"):
        return RedirectResponse(f"/procesy/{pid}/wskazniki/{cid}", status_code=303)
    return templates.TemplateResponse(request, "partials/_compass.html", compass_ctx(proc, cid, saved=entry),
                                      headers={"HX-Trigger": "decision-saved"})


# ---------------------------------------------------------------- 6. wynik i PDF
@app.get("/procesy/{pid}/podsumowanie", response_class=HTMLResponse, include_in_schema=False)
def summary_page(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user)
    if not proc.get("doc"):
        return RedirectResponse(f"/procesy/{pid}/arkusz", status_code=303)
    ev = workflow.evaluated(proc)
    form = proc["doc"]["form"]
    profile = radar.radar_view(ev, workflow.scale_points(form), workflow.scale_labels(form))
    return page(request, "process/podsumowanie.html", user, ev=ev, trail=workflow.trail(proc), radar=profile,
                today=workflow.today_iso(), **proc_ctx(proc, "podsumowanie"))


@app.post("/procesy/{pid}/podsumowanie", include_in_schema=False)
async def summary_submit(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user, editable=True)
    form = await request.form()
    try:
        workflow.save_summary(proc, user, {k: str(v) for k, v in form.items()})
        flash(request, "Zapisano dane do arkusza.", "ok")
    except workflow.WorkflowError as exc:
        flash(request, str(exc), "error")
    store.save_process(proc)
    return RedirectResponse(f"/procesy/{pid}/podsumowanie#wynik", status_code=303)


@app.get("/procesy/{pid}/arkusz.pdf", include_in_schema=False)
def summary_pdf(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user)
    try:
        data = workflow.pdf_bytes(proc, user)
    except workflow.WorkflowError as exc:
        flash(request, f"Arkusza nie da się jeszcze wygenerować: {exc}", "error")
        return RedirectResponse(f"/procesy/{pid}/podsumowanie#wynik", status_code=303)
    if not proc.get("demo"):
        store.save_process(proc)
    name = f"arkusz_{proc['doc']['form'].split('_')[-1].upper()}_{proc['id']}.pdf"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


# ---------------------------------------------------------------- asystent formalny
def custom_kb(request: Request) -> list[dict]:
    """Źródła wgrane przez administratora w tej sesji demo (dopisywane do bazy wiedzy asystenta)."""
    return store.list_kb_sources(sandbox_of(request))


ASSISTANT_TOPICS = [
    ("Ocena okresowa", [
        "Jak często sporządza się ocenę okresową?",
        "Ile kryteriów dodatkowych mogę wybrać w ocenie okresowej?",
        "Kiedy ocena okresowa jest negatywna?",
        "W jakim terminie oceniany może wnieść sprzeciw od oceny okresowej?",
        "Co się dzieje po negatywnej ocenie okresowej?",
    ]),
    ("Pierwsza ocena", [
        "W jakim terminie przełożony przeprowadza rozmowę wstępną w ramach pierwszej oceny?",
        "Kiedy pierwsza ocena jest negatywna?",
        "Kogo nie dotyczy egzamin ze służby przygotowawczej przy pierwszej ocenie?",
        "Czym różni się pierwsza ocena od oceny okresowej?",
    ]),
    ("Model kompetencji i rozmowa", [
        "Co oznaczają poziomy przy wskaźnikach behawioralnych w modelu kompetencji?",
        "Co zrobić, gdy nie miałem okazji zaobserwować danego zachowania pracownika?",
        "Co omawia się na rozmowie oceniającej w ocenie okresowej?",
        "Co jeśli pracownik nie zgadza się z oceną?",
    ]),
]


@app.get("/asystent", response_class=HTMLResponse, include_in_schema=False)
def assistant_page(request: Request, user: dict = Depends(SUPERVISOR), proces: str = ""):
    """Pełny widok asystenta: rozmowa z asystentem formalnym i asystent rozmowy dla wybranej oceny."""
    procs = [p for p in store.list_processes(sandbox_of(request), owner=user["id"]) if p.get("doc") and not p.get("demo")]
    selected = next((p for p in procs if p["id"] == proces), procs[0] if procs else None)
    return page(request, "asystent.html", user, kb=assistant_service.kb_sources(custom_kb(request)),
                topics=ASSISTANT_TOPICS, conv_procs=procs, conv_proc=selected, open_conv=bool(proces),
                info=assistant_service.describe())


@app.post("/asystent/formalny", response_class=HTMLResponse, include_in_schema=False)
def assistant_formal(request: Request, user: dict = Depends(SUPERVISOR), question: str = Form(""),
                     process: str = Form(""), history: list[str] = Form(default=[]),
                     history_order: str = Form("desc")):
    q = question.strip()[:500]
    if len(q) < 5:
        return HTMLResponse('<p class="assist-hint">Wpisz pytanie o zasady oceny (co najmniej kilka słów).</p>')
    if history_order == "asc":  # pełny widok: rozmowa od najstarszej (panel boczny – od najnowszej)
        history = list(reversed(history))
    res = assistant_service.ask_formal(q, process or None, sandbox_of(request),
                                       history=assistant_service.parse_history(history), custom=custom_kb(request))
    uid = secrets.token_hex(3)
    return templates.TemplateResponse(request, "partials/_answer.html", {
        "q": q, "res": res, "uid": uid, "html": assistant_service.answer_html(res, uid),
        "history_value": assistant_service.history_value(q, res)})


@app.get("/asystent/zrodlo/{chunk_id}", response_class=HTMLResponse, include_in_schema=False)
def assistant_unit(request: Request, chunk_id: str, user: dict = Depends(SUPERVISOR)):
    unit = assistant_service.unit_text(chunk_id, custom_kb(request), sandbox_of(request))
    if not unit:
        raise HTTPException(404, "Nie ma takiej jednostki w bazie wiedzy.")
    return templates.TemplateResponse(request, "partials/_unit.html", {"unit": unit})


# ---------------------------------------------------------------- asystent rozmowy (tylko przełożony)
def _conv_ctx(proc: dict, user: dict, action: str) -> dict:
    if not proc.get("doc"):
        raise workflow.WorkflowError("Najpierw wybierz arkusz oceny – asystent rozmowy pracuje na kryteriach i notatkach z arkusza.")
    ev = workflow.evaluated(proc)
    decided = ev.get("result") if ev.get("validation", {}).get("complete") else None
    return assistant_service.conversation_context(proc, user, action, decided)


@app.get("/procesy/{pid}/asystent/podglad", response_class=HTMLResponse, include_in_schema=False)
def conversation_preview(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    proc = load_proc(request, pid, user)
    preview = assistant_service.privacy_preview(_conv_ctx(proc, user, "questions"))
    return templates.TemplateResponse(request, "partials/_privacy.html", {"preview": preview})


@app.post("/procesy/{pid}/asystent/rozmowa", response_class=HTMLResponse, include_in_schema=False)
def conversation_ask(request: Request, pid: str, user: dict = Depends(SUPERVISOR), action: str = Form("questions"),
                     question: str = Form("")):
    proc = load_proc(request, pid, user)
    if action not in assistant_service.CONVERSATION_ACTIONS:
        raise HTTPException(400, "Asystent rozmowy nie zna tego polecenia.")
    q = question.strip()[:500]
    res = assistant_service.ask_conversation(_conv_ctx(proc, user, action), q, request.session.get("sandbox"))
    questions = assistant_service.extract_questions(res.get("answer", "")) if action == "questions" and not res["refused"] else []
    if not proc.get("demo") and not res["refused"]:
        # historia rozmowy z asystentem – pole prywatne przełożonego (rbac.json: assistant_chat), poza widokiem HR
        proc.setdefault("assistant_chat", []).append({"at": workflow.now_iso(), "action": action, "question": q or None,
                                                      "answer": res.get("answer", "")})
        proc["assistant_chat"] = proc["assistant_chat"][-10:]
        if questions:
            proc["interview_questions"] = questions
        store.save_process(proc)
    uid = secrets.token_hex(3)
    return templates.TemplateResponse(request, "partials/_conv_answer.html", {
        "proc": proc, "res": res, "uid": uid, "html": assistant_service.answer_html(res, uid),
        "label": assistant_service.CONVERSATION_ACTIONS[action], "questions": questions})


@app.post("/asystent/rozmowa", response_class=HTMLResponse, include_in_schema=False)
def conversation_ask_page(request: Request, user: dict = Depends(SUPERVISOR), pid: str = Form(...),
                          action: str = Form("questions"), question: str = Form("")):
    """Asystent rozmowy z pełnego widoku /asystent: ocena wybrana z listy zamiast z adresu."""
    return conversation_ask(request, pid, user, action, question)


@app.get("/procesy/{pid}/karta.pdf", include_in_schema=False)
def preparation_card(request: Request, pid: str, user: dict = Depends(SUPERVISOR)):
    """Karta przygotowania do rozmowy: dokument roboczy przełożonego (notatki S-D-R, pytania), nie trafia do akt ani do HR."""
    proc = load_proc(request, pid, user)
    if not proc.get("doc"):
        raise workflow.WorkflowError("Karta przygotowania powstaje po wybraniu arkusza oceny.")
    doc = workflow.evaluated(proc)
    doc["interview_questions"] = proc.get("interview_questions") or []
    for c in doc["criteria"]:
        texts = {i["id"]: i["text"] for i in workflow.COMPETENCIES.get(c["id"], {}).get("indicators", [])}
        for r in c.get("indicator_ratings") or []:
            r["indicator_text"] = texts.get(r["indicator_id"])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "karta.pdf"
        workflow.render_pdf.render(doc, out, kind="karta")
        data = out.read_bytes()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="karta_przygotowania_{proc["id"]}.pdf"'})


ANY_ROLE = need("przelozony", "hr_admin")


@app.get("/zrodla", response_class=HTMLResponse, include_in_schema=False)
def kb_sources_page(request: Request, user: dict = Depends(ANY_ROLE)):
    """Baza wiedzy asystenta: przełożony przegląda, administrator (rola HR) dodaje i usuwa źródła urzędu."""
    return page(request, "zrodla.html", user, kb=assistant_service.kb_sources(custom_kb(request)),
                doc_types=kb_upload.DOC_TYPES, max_sources=kb_upload.MAX_SOURCES_PER_SESSION)


@app.post("/zrodla/wgraj", include_in_schema=False)
async def kb_upload_submit(request: Request, user: dict = Depends(HR), title: str = Form(""),
                           doc_type: str = Form("wewnetrzne"), scope: str = Form("oba"),
                           file: UploadFile = File(...)):
    existing = custom_kb(request)
    if len(existing) >= kb_upload.MAX_SOURCES_PER_SESSION:
        flash(request, f"W sesji demo można dodać najwyżej {kb_upload.MAX_SOURCES_PER_SESSION} źródeł. "
                       "Usuń któreś z dodanych.", "error")
        return RedirectResponse("/zrodla#wlasne", status_code=303)
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        flash(request, f"Plik jest większy niż {MAX_UPLOAD // (1024 * 1024)} MB.", "error")
        return RedirectResponse("/zrodla#wlasne", status_code=303)
    base_ids = {c["source_id"] for c in assistant_service.get_assistant().chunks}
    try:
        src = kb_upload.build_source(filename=file.filename or "dokument", data=data, title=title, doc_type=doc_type,
                                     scope=scope, added_by=user["full_name"],
                                     existing_ids=base_ids | {s["source_id"] for s in existing})
    except kb_upload.UploadError as exc:
        flash(request, str(exc), "error")
        return RedirectResponse("/zrodla#wlasne", status_code=303)
    store.save_kb_source(src, sandbox_of(request))
    masked = ", ".join(f"{label} × {n}" for label, n in sorted(src["masked"].items()))
    flash(request, f"Dodano „{src['title']}”: {src['units']} jednostek w bazie wiedzy asystenta."
                   + (f" Zamaskowano dane osobowe: {masked}." if masked else ""), "ok")
    return RedirectResponse("/zrodla#wlasne", status_code=303)


@app.post("/zrodla/wlasne/{source_id}/usun", include_in_schema=False)
def kb_delete(request: Request, source_id: str, user: dict = Depends(HR)):
    if store.delete_kb_source(source_id, sandbox_of(request)):
        flash(request, "Usunięto źródło z bazy wiedzy asystenta.", "ok")
    else:
        flash(request, "Nie ma takiego źródła w tej sesji.", "error")
    return RedirectResponse("/zrodla#wlasne", status_code=303)


@app.get("/zrodla/{source_id}/{doc_type}", response_class=HTMLResponse, include_in_schema=False)
def kb_units_page(request: Request, source_id: str, doc_type: str, user: dict = Depends(ANY_ROLE)):
    if source_id == "faq":
        return page(request, "zrodla_jednostki.html", user, title="Zestaw pytań i odpowiedzi zespołu (FAQ)",
                    units=[], faq=assistant_service.faq_items())
    units = assistant_service.kb_units(source_id, doc_type, custom_kb(request))
    if not units:
        raise HTTPException(404, "Nie ma takiego źródła w bazie wiedzy.")
    return page(request, "zrodla_jednostki.html", user, title=units[0].get("title") or source_id, units=units, faq=None)


@app.get("/api/asystent/info", tags=["asystent"])
def assistant_info(user: dict = Depends(SUPERVISOR)):
    """Konfiguracja asystenta bez sekretów (dostawca, model, tryb retrievalu, liczba jednostek bazy wiedzy)."""
    return assistant_service.describe()
