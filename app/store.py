"""SQLite: użytkownicy demo, oceniani i procesy oceny.

Proces to jeden rekord JSON: metadane (status, krok, właściciel, piaskownica sesji), wynik analizy OSP,
dokument oceny wg kontraktu C3 (`kompas-model-i-silnik-oceny/assets/evaluation_schema.json`) i ślad
decyzji procesu. Dysk darmowej instancji Render jest nietrwały, więc dane demo ładuje `seed.py`
przy każdym starcie, a procesy jurorów żyją do restartu instancji.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, full_name TEXT NOT NULL, role TEXT NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY, full_name TEXT NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processes (
    id TEXT PRIMARY KEY,
    sandbox TEXT,              -- NULL = proces demo widoczny dla wszystkich; inaczej tylko w tej sesji
    owner TEXT NOT NULL,       -- id przełożonego
    kind TEXT NOT NULL,        -- periodic | first
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_processes_owner ON processes(owner, sandbox);
CREATE TABLE IF NOT EXISTS kb_sources (
    id TEXT PRIMARY KEY,       -- source_id jednostek bazy wiedzy (wlasne_<slug>)
    sandbox TEXT,              -- sesja demo, w której administrator wgrał źródło
    created_at TEXT NOT NULL,
    data TEXT NOT NULL         -- metadane źródła + jednostki (chunks) do indeksu asystenta
);
CREATE INDEX IF NOT EXISTS ix_kb_sources_sandbox ON kb_sources(sandbox);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as con:
            con.executescript(_SCHEMA)

    # ----------------------------------------------------------------- users
    def upsert_user(self, uid: str, full_name: str, role: str, data: dict) -> None:
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO users(id, full_name, role, data) VALUES(?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name, role=excluded.role, data=excluded.data",
                        (uid, full_name, role, json.dumps(data, ensure_ascii=False)))

    def get_user(self, uid: str | None) -> dict | None:
        if not uid:
            return None
        with self._connect() as con:
            row = con.execute("SELECT data FROM users WHERE id=?", (uid,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_users(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT data FROM users ORDER BY role DESC, id").fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ------------------------------------------------------------- employees
    def upsert_employee(self, eid: str, full_name: str, data: dict) -> None:
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO employees(id, full_name, data) VALUES(?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name, data=excluded.data",
                        (eid, full_name, json.dumps(data, ensure_ascii=False)))

    def get_employee(self, eid: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT data FROM employees WHERE id=?", (eid,)).fetchone()
        return json.loads(row["data"]) if row else None

    def list_employees(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT data FROM employees ORDER BY id").fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ------------------------------------------------------------- processes
    def save_process(self, proc: dict) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO processes(id, sandbox, owner, kind, status, updated_at, data) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at, data=excluded.data",
                (proc["id"], proc.get("sandbox"), proc["owner"], proc["kind"], proc["status"], proc["updated_at"],
                 json.dumps(proc, ensure_ascii=False)))

    def get_process(self, pid: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT data FROM processes WHERE id=?", (pid,)).fetchone()
        return json.loads(row["data"]) if row else None

    def has_process(self, pid: str) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM processes WHERE id=?", (pid,)).fetchone() is not None

    # ----------------------------------------------------- źródła bazy wiedzy wgrane w urzędzie
    def save_kb_source(self, src: dict, sandbox: str | None) -> None:
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO kb_sources(id, sandbox, created_at, data) VALUES(?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                        (src["source_id"], sandbox, src["created_at"], json.dumps(src, ensure_ascii=False)))

    def list_kb_sources(self, sandbox: str | None) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT data FROM kb_sources WHERE sandbox = ? ORDER BY created_at",
                               (sandbox or "",)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def delete_kb_source(self, source_id: str, sandbox: str | None) -> bool:
        with self._lock, self._connect() as con:
            cur = con.execute("DELETE FROM kb_sources WHERE id = ? AND sandbox = ?", (source_id, sandbox or ""))
        return cur.rowcount > 0

    def list_processes(self, sandbox: str | None, owner: str | None = None) -> list[dict]:
        """Procesy demo (sandbox NULL) + procesy tej sesji; owner=None → wszystkie (widok HR)."""
        sql = "SELECT data FROM processes WHERE (sandbox IS NULL OR sandbox = ?)"
        args: list = [sandbox or ""]
        if owner:
            sql += " AND owner = ?"
            args.append(owner)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        return [json.loads(r["data"]) for r in rows]
