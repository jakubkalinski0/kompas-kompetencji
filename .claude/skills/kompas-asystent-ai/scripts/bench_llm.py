"""Pomiar czasu odpowiedzi i tokenów/s modeli w Ollamie na polskich pytaniach z kontekstem z bazy wiedzy.

python bench_llm.py --kb <kb_chunks.jsonl> --models qwen2.5:14b llama3.1:8b --out bench.json
python bench_llm.py --kb <kb_chunks.jsonl> --models llama3.2:3b --cpu --n 1 --out bench_cpu.json

Pierwsze wywołanie każdego modelu (ładowanie do pamięci) jest raportowane osobno jako „zimny start”.
Na koniec: `ollama stop <model>` (robi to skrypt, gdy podasz --stop).
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_provider import LLMProvider  # noqa: E402

QUESTIONS = [
    ("W jakim terminie przełożony przeprowadza rozmowę wstępną z nowym pracownikiem?",
     ["rozp2015:par3", "rozp2015:par4:ust1"]),
    ("Ile kryteriów dodatkowych mogę wybrać w ocenie okresowej?", ["rozp2016:par5:ust2", "rozp2016:par3:ust3"]),
    ("Kiedy ocena okresowa jest negatywna?", ["rozp2016:par11:ust1", "rozp2016:par11:ust3"]),
    ("Ile dni ma pracownik na sprzeciw od oceny okresowej i do kogo go wnosi?",
     ["ustawa_sc:art83:ust1", "ustawa_sc:art81:ust9"]),
    ("Jakie są warunki pozytywnej pierwszej oceny?", ["rozp2015:par10:ust1", "rozp2015:par10:ust3"]),
]
SYSTEM = ("Jesteś asystentem formalnym oceny w służbie cywilnej. Odpowiadasz po polsku, zwięźle (2–4 zdania), "
          "wyłącznie na podstawie źródeł z bloku <zrodla>. Po każdym zdaniu podaj identyfikator źródła w nawiasie "
          "kwadratowym, np. [rozp2016:par7].")


def build_messages(q: str, ids: list[str], kb: dict) -> list[dict]:
    blocks = "\n".join(f'<zrodlo id="{i}" cytat="{kb[i]["citation"]}">\n{kb[i]["text"]}\n</zrodlo>'
                       for i in ids if i in kb)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"<zrodla>\n{blocks}\n</zrodla>\n\nPytanie: {q}"}]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=len(QUESTIONS))
    ap.add_argument("--cpu", action="store_true", help="options.num_gpu=0 (wymusza CPU)")
    ap.add_argument("--max-tokens", type=int, default=300)
    ap.add_argument("--stop", action="store_true", help="ollama stop <model> po pomiarze")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    kb = {}
    for line in Path(a.kb).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            kb[d["id"]] = d
    opts = {"num_gpu": 0} if a.cpu else {}
    report = {"cpu_only": a.cpu, "models": {}}
    for model in a.models:
        llm = LLMProvider(provider="ollama", model=model, timeout=600, retries=0)
        warm = llm.chat(build_messages(*QUESTIONS[0], kb), max_tokens=20, options=opts)
        rows = []
        for q, ids in QUESTIONS[: a.n]:
            r = llm.chat(build_messages(q, ids, kb), max_tokens=a.max_tokens, options=opts)
            rows.append({"q": q, "latency_s": r.latency_s, "prompt_tokens": r.prompt_tokens,
                         "completion_tokens": r.completion_tokens, "tokens_per_s": r.tokens_per_s,
                         "answer": r.text[:400]})
            print(f"{model} {r.latency_s:6.1f}s {r.tokens_per_s} tok/s | {r.text[:90]!r}", flush=True)
        lat = [r["latency_s"] for r in rows]
        tps = [r["tokens_per_s"] for r in rows if r["tokens_per_s"]]
        report["models"][model] = {
            "cold_start_s": warm.latency_s,
            "load_duration_s": round((warm.raw.get("load_duration") or 0) / 1e9, 2),
            "latency_median_s": round(statistics.median(lat), 2), "latency_max_s": max(lat),
            "tokens_per_s_median": round(statistics.median(tps), 2) if tps else None,
            "rows": rows}
        if a.stop:
            subprocess.run(["ollama", "stop", model], check=False)
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({m: {k: v for k, v in d.items() if k != "rows"} for m, d in report["models"].items()},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
