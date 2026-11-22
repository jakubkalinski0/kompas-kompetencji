"""Wspólna warstwa LLMProvider dla Kompasu Kompetencji (tylko biblioteka standardowa).

Dwa tryby przełączane zmienną LLM_PROVIDER:
  ollama        – lokalna Ollama (http://localhost:11434), natywne /api/chat i /api/embed
  openai_compat – dowolny serwer zgodny z OpenAI (/chat/completions, /embeddings):
                  Groq, Mistral, OpenRouter, Ollama /v1, vLLM/llama.cpp z PLLuM/Bielikiem on-prem

Zmienne środowiskowe (patrz ../.env.example):
  LLM_PROVIDER, LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, EMBED_MODEL, EMBED_PROVIDER, EMBED_BASE_URL,
  LLM_TIMEOUT (s), LLM_RETRIES, LLM_CACHE (0/1), LLM_CACHE_DIR, LLM_REPLAY (0/1),
  LLM_REASONING_EFFORT (low|medium|high|none; domyślnie low dla gpt-oss w trybie openai_compat)

Użycie:
  from llm_provider import LLMProvider
  llm = LLMProvider.from_env()
  r = llm.chat([{"role": "system", "content": "..."}, {"role": "user", "content": "..."}])
  r.text, r.latency_s, r.completion_tokens, r.tokens_per_s
  vecs = llm.embed(["search_query: termin sprzeciwu"])

CLI (szybki test):  python llm_provider.py chat "Napisz jedno zdanie po polsku."
                    python llm_provider.py embed "tekst"
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434", "model": "qwen2.5:14b"},
    "openai_compat": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
}
RETRY_HTTP = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Czytelny błąd do pokazania w UI (brak klucza, limit, timeout, brak w cache w trybie replay)."""


@dataclass
class ChatResult:
    text: str
    model: str
    provider: str
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_per_s: float | None = None  # generacja (eval) – tylko gdy serwer podaje czasy (Ollama)
    cached: bool = False
    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        return d


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "tak", "on"}


class LLMProvider:
    def __init__(self, provider: str = "ollama", base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None, embed_model: str = "nomic-embed-text",
                 embed_provider: str | None = None, embed_base_url: str | None = None,
                 timeout: float = 120.0, retries: int = 2, cache: bool = False,
                 cache_dir: str | os.PathLike = ".llm_cache", replay: bool = False,
                 reasoning_effort: str | None = None):
        if provider not in DEFAULTS:
            raise LLMError(f"Nieznany LLM_PROVIDER={provider!r}; dozwolone: {', '.join(DEFAULTS)}")
        self.provider = provider
        self.base_url = (base_url or DEFAULTS[provider]["base_url"]).rstrip("/")
        self.model = model or DEFAULTS[provider]["model"]
        # Modele rozumujące (gpt-oss) liczą rozumowanie do max_tokens; „low” skraca je, żeby odpowiedź nie była pusta.
        # LLM_REASONING_EFFORT=none wyłącza pole (serwery, które go nie znają).
        if reasoning_effort is None and provider == "openai_compat" and "gpt-oss" in self.model.lower():
            reasoning_effort = "low"
        self.reasoning_effort = None if (reasoning_effort or "").lower() in ("", "none", "off") else reasoning_effort
        self.api_key = api_key
        self.embed_model = embed_model
        # Embeddingi domyślnie z lokalnej Ollamy (nomic-embed-text), także gdy czat idzie do API w chmurze.
        self.embed_provider = embed_provider or "ollama"
        self.embed_base_url = (embed_base_url or (self.base_url if self.embed_provider == provider
                                                  else DEFAULTS[self.embed_provider]["base_url"])).rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.cache = cache or replay
        self.replay = replay
        self.cache_dir = Path(cache_dir)

    @classmethod
    def from_env(cls, **overrides) -> "LLMProvider":
        kw = dict(
            provider=_env("LLM_PROVIDER", "ollama"),
            base_url=_env("LLM_BASE_URL"),
            model=_env("LLM_MODEL"),
            api_key=_env("LLM_API_KEY"),
            embed_model=_env("EMBED_MODEL", "nomic-embed-text"),
            embed_provider=_env("EMBED_PROVIDER"),
            embed_base_url=_env("EMBED_BASE_URL"),
            timeout=float(_env("LLM_TIMEOUT", "120")),
            retries=int(_env("LLM_RETRIES", "2")),
            cache=_truthy(_env("LLM_CACHE", "0")),
            cache_dir=_env("LLM_CACHE_DIR", ".llm_cache"),
            replay=_truthy(_env("LLM_REPLAY", "0")),
            reasoning_effort=_env("LLM_REASONING_EFFORT"),
        )
        kw.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kw)

    # ------------------------------------------------------------------ HTTP
    def _post(self, url: str, payload: dict, auth: bool) -> dict:
        data = json.dumps(payload).encode("utf-8")
        # Własny User-Agent: Cloudflare przed api.groq.com odrzuca domyślny "Python-urllib/x.y"
        # błędem HTTP 403 "error code: 1010" (sprawdzone 2026-11-21).
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "kompas-kompetencji/0.1 (python-urllib)"}
        if auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:300]
                last_err = LLMError(f"HTTP {e.code} z {url}: {body}")
                if e.code not in RETRY_HTTP or attempt == self.retries:
                    raise last_err from None
                wait = e.headers.get("Retry-After") if e.headers else None
                time.sleep(min(float(wait), 20.0) if wait and wait.replace(".", "").isdigit() else 2 ** attempt)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_err = LLMError(f"Brak połączenia z {url}: {e}")
                if attempt == self.retries:
                    raise last_err from None
                time.sleep(2 ** attempt)
        raise last_err or LLMError("nieznany błąd")

    # ----------------------------------------------------------------- cache
    def _cache_path(self, kind: str, payload: dict) -> Path:
        key = hashlib.sha256(json.dumps([kind, self.provider, payload], sort_keys=True,
                                        ensure_ascii=False).encode("utf-8")).hexdigest()
        return self.cache_dir / f"{kind}_{key[:32]}.json"

    # ------------------------------------------------------------------ chat
    def chat(self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 700,
             options: dict | None = None, extra: dict | None = None) -> ChatResult:
        """Wysyła rozmowę i zwraca ChatResult. `options` trafia do Ollamy (np. {"num_gpu": 0, "num_ctx": 8192}).

        `extra` – dodatkowe pola żądania dla trybu openai_compat, np. {"reasoning_effort": "low"} dla modeli
        rozumujących (gpt-oss na Groq liczy tokeny rozumowania do max_tokens). W trybie ollama jest ignorowane.
        """
        if self.provider == "ollama":
            opts = {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192}
            opts.update(options or {})
            payload = {"model": self.model, "messages": messages, "stream": False, "options": opts}
            url = f"{self.base_url}/api/chat"
        else:
            payload = {"model": self.model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens}
            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort
            payload.update(extra or {})
            url = f"{self.base_url}/chat/completions"
            if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
                raise LLMError("Brak LLM_API_KEY dla trybu openai_compat (ustaw w .env, nigdy w repozytorium).")

        cpath = self._cache_path("chat", payload) if self.cache else None
        if cpath and cpath.exists():
            d = json.loads(cpath.read_text(encoding="utf-8"))
            d["cached"] = True
            return ChatResult(**d)
        if self.replay:
            raise LLMError("Tryb LLM_REPLAY=1: brak zapisanej odpowiedzi na to pytanie (demo offline).")

        t0 = time.perf_counter()
        raw = self._post(url, payload, auth=self.provider != "ollama")
        latency = time.perf_counter() - t0
        if self.provider == "ollama":
            text = (raw.get("message") or {}).get("content", "")
            ev, evd = raw.get("eval_count"), raw.get("eval_duration")
            res = ChatResult(text=text, model=self.model, provider=self.provider, latency_s=round(latency, 3),
                             prompt_tokens=raw.get("prompt_eval_count"), completion_tokens=ev,
                             tokens_per_s=round(ev / (evd / 1e9), 2) if ev and evd else None, raw=raw)
        else:
            choices = raw.get("choices") or [{}]
            text = (choices[0].get("message") or {}).get("content") or ""
            usage = raw.get("usage") or {}
            ct = usage.get("completion_tokens")
            res = ChatResult(text=text, model=raw.get("model", self.model), provider=self.provider,
                             latency_s=round(latency, 3), prompt_tokens=usage.get("prompt_tokens"),
                             completion_tokens=ct, tokens_per_s=round(ct / latency, 2) if ct and latency else None,
                             raw=raw)
        if cpath:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        return res

    # ----------------------------------------------------------------- embed
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.embed_provider == "ollama":
            raw = self._post(f"{self.embed_base_url}/api/embed", {"model": self.embed_model, "input": texts},
                             auth=False)
            vecs = raw.get("embeddings")
        else:
            raw = self._post(f"{self.embed_base_url}/embeddings", {"model": self.embed_model, "input": texts},
                             auth=True)
            vecs = [d["embedding"] for d in sorted(raw.get("data", []), key=lambda d: d.get("index", 0))]
        if not vecs or len(vecs) != len(texts):
            raise LLMError(f"Serwer embeddingów zwrócił {len(vecs or [])} wektorów dla {len(texts)} tekstów")
        return vecs

    def describe(self) -> dict:
        return {"provider": self.provider, "base_url": self.base_url, "model": self.model,
                "embed_provider": self.embed_provider, "embed_model": self.embed_model,
                "api_key_set": bool(self.api_key), "cache": self.cache, "replay": self.replay}


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimalny loader .env (KLUCZ=wartość), nie nadpisuje istniejących zmiennych."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main(argv: list[str]) -> int:
    load_dotenv()
    if len(argv) < 2 or argv[0] not in {"chat", "embed", "info"}:
        print(__doc__)
        return 2
    llm = LLMProvider.from_env()
    if argv[0] == "info":
        print(json.dumps(llm.describe(), ensure_ascii=False, indent=1))
    elif argv[0] == "chat":
        r = llm.chat([{"role": "user", "content": " ".join(argv[1:])}])
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=1))
    else:
        v = llm.embed([" ".join(argv[1:])])
        print(f"wymiar={len(v[0])} pierwsze={v[0][:4]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
