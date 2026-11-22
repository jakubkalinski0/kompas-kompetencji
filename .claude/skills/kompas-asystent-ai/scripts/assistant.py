"""Jedno wejście Asystenta AI Kompasu Kompetencji: answer(question, mode, context).

mode="formal"        – Asystent formalny: reguła odmowy decyzji → FAQ → retrieval hybrydowy → próg odmowy → LLM
                       z cytatami [id] → walidacja cytatów → filtr wyjścia. context["history"] = [{q, a}, …]
                       (ostatnie tury rozmowy) pozwala dopytać („a w pierwszej ocenie?”): pytanie uzupełniające
                       szuka razem z poprzednim pytaniem, a model dostaje wcześniejsze tury bez cytatów.
                       Słabe dopasowanie (retrieve.SOFT_COVERAGE_MIN ≤ pokrycie < COVERAGE_MIN) idzie do modelu,
                       który odpowiada z cytatem albo odmawia; poniżej SOFT – odmowa bez modelu.
mode="conversation"  – Asystent rozmowy: context["action"] ∈ questions|feedback|justification|development;
                       notatki maskowane przez privacy_shield przed wysłaniem do LLM; filtr propozycji punktów.

Zwraca dict: answer, refused, refusal_reason, citations[{id, citation, fragment}], mode, signals, latency_s,
llm{model, provider, completion_tokens, tokens_per_s}, privacy_preview (tryb rozmowy).

CLI:
  python assistant.py --kb kb_chunks.jsonl --mode formal "Ile dni na sprzeciw od oceny okresowej?"
  python assistant.py --kb kb_chunks.jsonl --mode conversation --action questions --context ctx.json
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from llm_provider import LLMError, LLMProvider, load_dotenv  # noqa: E402
from privacy_shield import ShieldContext, mask, preview, unmask  # noqa: E402
from retrieve import Retriever, analyze, load_jsonl, unit_matches  # noqa: E402

ASSETS = HERE.parent / "assets"
# Limity odpowiedzi obejmują tokeny rozumowania modeli takich jak gpt-oss (Groq liczy je do max_tokens);
# przy 450 tokenach odpowiedź bywała pusta, więc aplikacja pokazywała odmowę „bez poprawnego cytatu”.
FORMAL_MAX_TOKENS = 1400
CONVERSATION_MAX_TOKENS = 2000
HISTORY_TURNS = 2  # ile wcześniejszych pytań rozmowy dostaje model (pytania uzupełniające)
FOLLOWUP_RX = re.compile(r"^\s*(a|i|oraz|to|czyli|ale|więc|wiec|w\s+takim\s+razie|a\s+co|a\s+jeśli|a\s+jesli|"
                         r"a\s+kiedy|a\s+ile|a\s+kto|a\s+w|a\s+dla|a\s+gdy|dlaczego|czemu|skąd|skad)\b", re.I)
REFUSAL = ("Nie znalazłem odpowiedzi w bazie wiedzy Kompasu (ustawa, rozporządzenia, poradniki i Q&A KPRM, "
           "model kompetencji). Nie zgaduję – sprawdź to w komórce kadr albo u radcy prawnego urzędu.")
DECISION_REFUSAL = ("Nie proponuję poziomu, punktów ani wyniku oceny konkretnego pracownika – tę decyzję podejmuje "
                    "przełożony. Mogę wyjaśnić skalę ocen, progi i reguły z przepisów albo pomóc przygotować rozmowę.")
FILTER_NOTE = "[Usunięto zdanie z propozycją poziomu lub punktów – decyzja o ocenie należy do przełożonego.]"

DECISION_RX = re.compile(
    r"(ile\s+punkt\w*|jak\w*\s+(poziom\w*|ocen\w*)|jak\s+ocenić)[^?]{0,80}?"
    r"(powin\w+|mam\s+(dać|przyznać|wystawić)|dać|przyznać|wystawić|zasługuje)", re.I)
# Propozycje poziomu/punktów w odpowiedzi modelu.
STRICT_OUT_RX = re.compile(
    r"(propon\w+|sugeru\w+|rekomend\w+|zalecam\w*|powin\w+\s+(otrzymać|dostać|uzyskać|mieć)|zasługuj\w*\s+na|"
    r"należy\s+(przyznać|wystawić|dać))[^.\n]{0,80}?(\b[13579]\s*(pkt|punkt\w*)|poziom\w*|ocen\w*\s+(pozytywn|"
    r"negatywn|cząstkow|łączn|ogóln|znacznie|powyżej|poniżej|na\s+poziomie))", re.I)
SOFT_OUT_RX = re.compile(r"(propon\w+|sugeru\w+|rekomend\w+|zalecam\w*)[^.\n]{0,60}?(\b[13579]\s*(pkt|punkt\w*)|"
                         r"poziom\w*\s+(znacznie|powyżej|poniżej|na\s+poziomie))", re.I)
CITE_RX = re.compile(r"\[([A-Za-z0-9_:.\-ąćęłńóśźż]+)\]")


_ALT_BRACKETS = str.maketrans({"【": "[", "】": "]", "〔": "[", "〕": "]", "［": "[", "］": "]"})
_MULTI_CITE_RX = re.compile(r"\[([A-Za-z0-9_:.\-ąćęłńóśźż]+(?:\s*[,;]\s*[A-Za-z0-9_:.\-ąćęłńóśźż]+)+)\]")


def normalize_citations(text: str) -> str:
    """Ujednolica zapis cytatów modelu: 【id】 (natywny format gpt-oss) → [id], [a, b] → [a][b].

    Bez tego walidator nie widział poprawnego cytatu i odrzucał trafną odpowiedź jako „bez podstawy”.
    """
    text = text.translate(_ALT_BRACKETS)
    return _MULTI_CITE_RX.sub(lambda m: "".join(f"[{p.strip()}]" for p in re.split(r"[,;]", m.group(1))), text)


def bracket_known_ids(text: str, allowed: set[str]) -> str:
    """„(ustawa_sc:art81 ust. 4)” → „[ustawa_sc:art81]”, ale tylko dla identyfikatorów z kontekstu.

    Mały model lokalny zapisuje identyfikator w nawiasie okrągłym; zmyślonego identyfikatora to nie uratuje,
    bo zamiana dotyczy wyłącznie jednostek, które model dostał w bloku <zrodla>.
    """
    if not allowed:
        return text
    alt = "|".join(re.escape(i) for i in sorted(allowed, key=len, reverse=True))
    return re.sub(rf"\(\s*({alt})(?![\w:.\-])[^()\n]{{0,40}}\)", r"[\1]", text)


def _load_prompt(name: str) -> str:
    return (ASSETS / "prompts" / name).read_text(encoding="utf-8")


def output_filter(text: str, strict: bool) -> tuple[str, int]:
    """Usuwa zdania z propozycją poziomu/punktów. Zwraca (tekst, liczba usuniętych zdań)."""
    rx = STRICT_OUT_RX if strict else SOFT_OUT_RX
    lines, removed = [], 0
    # zdania filtrujemy w obrębie linii, żeby listy (pytania na rozmowę, wnioski do IPRZ) zachowały podział na linie
    for line in text.split("\n"):
        kept = []
        for p in re.split(r"(?<=[.!?])\s+", line):
            if rx.search(p):
                removed += 1
            else:
                kept.append(p)
        joined = " ".join(x for x in kept if x.strip())
        if re.fullmatch(r"\s*(?:\d+[.)]|[-*•])\s*", joined):
            continue  # z punktu listy zostałby sam numer po usunięciu zdania z propozycją oceny
        if joined or not line.strip():
            lines.append(joined)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if removed:
        out = (out + "\n" + FILTER_NOTE).strip()
    return out, removed


def _blocks(chunks: list[dict], max_chars: int = 1800) -> str:
    out = []
    for c in chunks:
        txt = c.get("text", "")
        txt = txt if len(txt) <= max_chars else txt[:max_chars] + " […]"
        out.append(f'<zrodlo id="{c["id"]}" cytat="{c.get("citation", "")}">\n{txt}\n</zrodlo>')
    return "<zrodla>\n" + "\n".join(out) + "\n</zrodla>"


class Assistant:
    def __init__(self, kb_path: str | Path, faq_path: str | Path | None = None, provider: LLMProvider | None = None,
                 cache_dir: str | Path = ".cache", use_embeddings: bool = True, k: int = 5):
        self.chunks = load_jsonl(kb_path)
        faq_path = faq_path or ASSETS / "faq_kb.json"
        faq = json.loads(Path(faq_path).read_text(encoding="utf-8"))["items"] if faq_path else None
        self.llm = provider or LLMProvider.from_env()
        self.retriever = Retriever(self.chunks, faq, provider=self.llm, cache_dir=cache_dir,
                                   use_embeddings=use_embeddings)
        self.k = k
        self.actions = json.loads(_load_prompt("conversation_actions.json"))

    def with_extra_chunks(self, extra: list[dict]) -> "Assistant":
        """Kopia asystenta z dodatkowymi jednostkami (źródła wgrane przez administratora); BM25 liczony od nowa.

        Embeddingi nowych jednostek wymagałyby Ollamy, więc kopia korzysta z samego BM25 (jak wersja na Render).
        """
        if not extra:
            return self
        a = copy.copy(self)
        a.chunks = self.chunks + list(extra)
        a.retriever = Retriever(a.chunks, self.retriever.faq, provider=self.llm, use_embeddings=False)
        return a

    # ------------------------------------------------------------- public
    def answer(self, question: str, mode: str = "formal", context: dict | None = None) -> dict:
        t0 = time.perf_counter()
        context = context or {}
        res = (self._formal(question, context) if mode == "formal" else self._conversation(question, context))
        res["mode"] = mode
        res["latency_s"] = round(time.perf_counter() - t0, 3)
        return res

    # ------------------------------------------------------------- formal
    def _formal(self, question: str, context: dict) -> dict:
        if DECISION_RX.search(question):
            return self._refusal(DECISION_REFUSAL, "prośba o decyzję o ocenie (reguła, bez LLM)")
        history = [h for h in (context.get("history") or []) if (h.get("q") or "").strip()][-HISTORY_TURNS:]
        process = context.get("process")
        r = self.retriever.search(question, k=self.k, process=process)
        followup = False
        if history and r["mode"] != "faq" and (r["refuse"] or FOLLOWUP_RX.match(question)
                                               or len(analyze(question)) <= 3):
            # pytanie uzupełniające („a w pierwszej ocenie?”): szukamy z poprzednim pytaniem rozmowy
            r2 = self.retriever.search(f"{history[-1]['q']} {question}", k=self.k, process=process, use_faq=False)
            if not r2["refuse"] or r2["signals"]["coverage"] > r["signals"].get("coverage", 0):
                r, followup = r2, True
        if r["mode"] == "faq":
            f = r["faq"]
            return {"answer": f["answer"], "refused": False, "refusal_reason": "", "source": "faq",
                    "faq_id": f["id"], "citations": self._citations([h["id"] for h in r["hits"]]),
                    "signals": r["signals"], "retrieved_ids": [h["id"] for h in r["hits"]], "llm": None}
        if r["refuse"] and not r.get("weak"):
            out = self._refusal(REFUSAL, f"retrieval poniżej progu ({r['reason']})")
            out.update(signals=r["signals"], retrieved_ids=[h["id"] for h in r["hits"]])
            return out
        ctx_chunks = [self.retriever.by_id[h["id"]] for h in r["hits"]]
        system = _load_prompt("formal_system.md").replace("{REFUSAL}", REFUSAL).replace(
            "{DECISION_REFUSAL}", DECISION_REFUSAL)
        messages = [{"role": "system", "content": system}]
        for h in history:
            # wcześniejsze tury rozmowy: tylko do zrozumienia pytania uzupełniającego, bez identyfikatorów źródeł
            messages.append({"role": "user", "content": f"Pytanie przełożonego: {h['q'][:500]}"})
            if (h.get("a") or "").strip():
                messages.append({"role": "assistant", "content": CITE_RX.sub("", h["a"])[:700].strip()})
        messages.append({"role": "user", "content": f"{_blocks(ctx_chunks)}\n\nPytanie przełożonego: {question}"})
        try:
            llm = self.llm.chat(messages, temperature=0.1, max_tokens=FORMAL_MAX_TOKENS)
        except LLMError as e:
            out = self._refusal(f"Asystent jest chwilowo niedostępny: {e}", "błąd LLM")
            out["error"] = str(e)
            return out
        text, removed = output_filter(normalize_citations(llm.text.strip()), strict=False)
        allowed = {c["id"] for c in ctx_chunks}
        text = bracket_known_ids(text, allowed)
        cited = list(dict.fromkeys(CITE_RX.findall(text)))
        valid = [c for c in cited if c in allowed]
        invalid = [c for c in cited if c not in allowed]
        refused = (text.startswith(REFUSAL[:40]) or text.startswith(DECISION_REFUSAL[:40])
                   or (not valid and bool(re.match(r"\s*nie\s+(znalaz|ma\s+w\s+bazie|mam\s+podstaw)", text, re.I))))
        if not refused and not valid:
            # odpowiedź bez poprawnego cytatu nie trafia do użytkownika
            out = self._refusal(REFUSAL, "odpowiedź LLM bez poprawnego cytatu")
            out.update(signals=r["signals"], raw_answer=text, retrieved_ids=list(allowed))
            return out
        for bad in invalid:
            text = text.replace(f"[{bad}]", "[źródło niezweryfikowane]")
        return {"answer": text, "refused": refused, "refusal_reason": "LLM: brak podstaw w źródłach" if refused else "",
                "source": "llm", "citations": [] if refused else self._citations(valid),
                "invalid_citations": invalid, "filtered_sentences": removed, "signals": r["signals"],
                "weak_retrieval": bool(r.get("weak")), "followup": followup,
                "retrieved_ids": [h["id"] for h in r["hits"]], "llm": self._llm_meta(llm)}

    # ------------------------------------------------------- conversation
    def _conversation(self, question: str, context: dict) -> dict:
        action = context.get("action", "questions")
        spec = self.actions.get(action)
        if not spec:
            return self._refusal(f"Nieznana akcja: {action}", "zła akcja")
        process = context.get("process", "periodic")
        if action == "development" and process == "first" and context.get("decided_result") == "negatywna":
            return self._refusal("Wnioski dotyczące rozwoju zawodowego sporządza się tylko przy pozytywnej pierwszej "
                                 "ocenie (§ 10 ust. 6 rozporządzenia z 2015 r., przypis 8 arkusza).",
                                 "reguła: wnioski rozwojowe tylko przy pozytywnej pierwszej ocenie")
        chunks = self._chunks_for(spec["sources"].get(process, []))
        for crit in context.get("criteria", []):
            chunks += [c for c in self.chunks if c.get("source_id") == "model_kompetencji"
                       and c["id"].endswith(":" + crit)]
        notes = "\n".join(f"- [{n.get('criterion', 'ogólne')}] {n.get('note', '')}" for n in context.get("notes", []))
        shield = ShieldContext(employee=context.get("employee"), evaluator=context.get("evaluator"),
                               others=context.get("others", []))
        masked = mask(notes + ("\nPytanie przełożonego: " + question if question else ""), shield)
        stage = ("rozmowa wstępna/oceniająca w pierwszej ocenie" if process == "first"
                 else context.get("stage", "rozmowa oceniająca w ocenie okresowej"))
        target = "wnioski do arkusza pierwszej oceny" if process == "first" else "wnioski do IPRZ"
        instr = spec["instruction"].format(stage=stage, target=target)
        decided = context.get("decided_result")
        meta = (f"Proces: {'pierwsza ocena' if process == 'first' else 'ocena okresowa'}; arkusz: "
                f"{context.get('form', '-')}; kryteria: {', '.join(context.get('criteria', [])) or '-'}"
                + (f"; wynik wybrany przez przełożonego: {decided}" if decided else ""))
        user = (f"{_blocks(chunks, 1500)}\n\n<notatki>\n{masked.text}\n</notatki>\n\n<kontekst>{meta}</kontekst>\n\n"
                f"Zadanie: {instr}")
        try:
            llm = self.llm.chat([{"role": "system", "content": _load_prompt("conversation_system.md")},
                                 {"role": "user", "content": user}], temperature=0.3, max_tokens=CONVERSATION_MAX_TOKENS)
        except LLMError as e:
            return self._refusal(f"Asystent jest chwilowo niedostępny: {e}", "błąd LLM")
        text, removed = output_filter(normalize_citations(llm.text.strip()), strict=True)
        allowed = {c["id"] for c in chunks}
        cited = [c for c in dict.fromkeys(CITE_RX.findall(text))]
        return {"answer": unmask(text, masked.mapping), "answer_masked": text, "refused": False,
                "refusal_reason": "", "source": "llm", "action": action,
                "citations": self._citations([c for c in cited if c in allowed]),
                "invalid_citations": [c for c in cited if c not in allowed and not c.startswith("uzupełnij")],
                "filtered_sentences": removed, "privacy_preview": preview(notes, shield), "llm": self._llm_meta(llm)}

    # ------------------------------------------------------------ helpers
    def _chunks_for(self, sources: list[dict]) -> list[dict]:
        out = []
        for s in sources:
            out += [c for c in self.chunks if c.get("source_id") == s["source_id"]
                    and unit_matches(c.get("unit", ""), s["unit"]) and c not in out]
        return out

    def _citations(self, ids: list[str]) -> list[dict]:
        out = []
        for i in ids:
            c = self.retriever.by_id.get(i)
            if c:
                out.append({"id": i, "citation": c.get("citation"), "fragment": c.get("text", "")[:300]})
        return out

    @staticmethod
    def _llm_meta(r) -> dict:
        return {"model": r.model, "provider": r.provider, "latency_s": r.latency_s,
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "tokens_per_s": r.tokens_per_s, "cached": r.cached}

    @staticmethod
    def _refusal(msg: str, reason: str) -> dict:
        return {"answer": msg, "refused": True, "refusal_reason": reason, "source": "rule", "citations": [],
                "llm": None}


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Asystent AI Kompasu Kompetencji (CLI do ręcznych testów)")
    ap.add_argument("question", nargs="?", default="")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--faq")
    ap.add_argument("--mode", choices=["formal", "conversation"], default="formal")
    ap.add_argument("--action", choices=["questions", "feedback", "justification", "development"])
    ap.add_argument("--context", help="plik JSON z kontekstem procesu (tryb rozmowy)")
    ap.add_argument("--process", choices=["first", "periodic"])
    ap.add_argument("--cache-dir", default=".cache")
    ap.add_argument("--no-embed", action="store_true")
    a = ap.parse_args()
    ctx = json.loads(Path(a.context).read_text(encoding="utf-8")) if a.context else {}
    if a.action:
        ctx["action"] = a.action
    if a.process:
        ctx["process"] = a.process
    asst = Assistant(a.kb, a.faq, cache_dir=a.cache_dir, use_embeddings=not a.no_embed)
    res = asst.answer(a.question, a.mode, ctx)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
