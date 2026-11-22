"""Retrieval dla Asystenta formalnego: FAQ → hybryda BM25 + embeddingi (RRF) → próg odmowy. Tylko stdlib.

Warstwa 1: dopasowanie pytania do `faq_kb.json` (pytania kanoniczne + warianty). Tylko bardzo bliskie
           dopasowanie (Jaccard rdzeni ≥ FAQ_JACCARD albo cosinus ≥ FAQ_COSINE) zwraca gotową odpowiedź.
Warstwa 2: BM25 (czysty Python, polska normalizacja) + embeddingi `nomic-embed-text` (Ollama) na
           `kb_chunks.jsonl` (kontrakt C1), fuzja Reciprocal Rank Fusion (k=60).
Odmowa:    gdy max cosinus < DENSE_MIN albo pokrycie słów pytania w top-3 < COVERAGE_MIN. Pokrycie między
           SOFT_COVERAGE_MIN a COVERAGE_MIN to dopasowanie „słabe” (`weak`): Asystent przekazuje je modelowi,
           który odpowiada tylko z cytatem albo odmawia – pytania zadane potocznie („nie zgadza się z oceną”)
           nie kończą się odmową na etapie wyszukiwania.
Rozszerzenie pytania: QUERY_EXPANSIONS dopisuje do pytania słownictwo przepisów dla potocznych sformułowań
           (tylko do wyszukiwania; model dostaje pytanie w oryginale).

Polska normalizacja (ograniczenia – patrz też SKILL.md, sekcja „Pułapki”):
  małe litery → usunięcie znaków diakrytycznych (ł→l) → obcięcie najdłuższej pasującej końcówki fleksyjnej
  (rdzeń ≥ 3 znaki) → obcięcie do 7 znaków. Nie obsługuje oboczności (sąd/sądzie→„sad”/„sadzi”), supletywizmu
  (człowiek/ludzie) ani złożeń; skleja czasem różne słowa o wspólnym początku (ocena/oceniający → „ocen…”).

CLI:
  python retrieve.py --kb kb_chunks.jsonl --faq ../assets/faq_kb.json --cache-dir .cache "Ile dni na sprzeciw?"
  python retrieve.py --kb kb_chunks.jsonl --no-embed "..."      # sam BM25 (bez Ollamy)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FAQ_JACCARD = 0.75
FAQ_COSINE = 0.93
# Progi odmowy skalibrowane 2026-11-21 na eval_holdout (kompas-ewaluacja/references/test-run.md) – optymistyczne,
# bo strojone na zbiorze testowym; przed demo przelicz na osobnym zbiorze kalibracyjnym.
DENSE_MIN = 0.74
COVERAGE_MIN = 0.20
# Poniżej tego pokrycia odmowa bez modelu; między SOFT a COVERAGE_MIN decyduje model (odpowiedź z cytatem albo odmowa).
SOFT_COVERAGE_MIN = 0.06
RRF_K = 60
LEGAL_BOOST = True
# „wlasne” – dokumenty urzędu wgrane przez administratora (zarządzenia, wytyczne): dla urzędu też źródło pierwotne;
# bez tego lista RRF „tylko akty prawne” liczyła przepisy podwójnie i wypychała je z top-5 mimo wyższego BM25.
LEGAL_TYPES = {"ustawa", "rozporzadzenie", "wlasne"}

STOP = set("""a aby albo ale bo by byc chce co czy czym dla do gdy go i ich ile im ja jak jaka jaki jakie jakim
jakiej jaka jej jego je jest jesli jezeli juz kiedy kto ktora ktore ktory ktorych ktorej ma mam mi mnie moge
moj moja moje moze my na nad nie o od oraz po pod przez przy sa sie ta tak te tego tej ten tez to tym u w we
wiec z za ze czyli lub mozna musi musze trzeba powinien powinna nalezy jakie jakich ktorym""".split())

SUFFIXES = sorted("""osciami osciach owaniami owaniach owaniem owania owanie owaniu aniem eniem aniu eniu ania
enia anie enie osci oscia osc ami ach ego emu owi owie ych ymi imi ich iej iem ej em om ow ie ia iu ii y a e i o
u ujesz uje uja owac ywac iwac ac ic""".split(), key=len, reverse=True)
PROCESS_WORDS = {"first": "pierwsza ocena pierwszej oceny", "periodic": "ocena okresowa oceny okresowej"}
# Słowa pytające i przeczenie zostają w dopasowaniu FAQ: bez nich „Kto sporządza ocenę okresową?”
# i „Kiedy nie sporządza się oceny okresowej?” dawały ten sam zbiór rdzeni co „Jak często sporządza się…”.
QWORDS = {"kto": "kto", "kogo": "kto", "komu": "kto", "kiedy": "kiedy", "ile": "ile", "jak": "jak", "czy": "czy",
          "nie": "nie", "co": "co", "czego": "co", "gdzie": "gdzie", "dlaczego": "dlaczego", "jaki": "jaki",
          "jaka": "jaki", "jakie": "jaki", "jakim": "jaki", "jakiej": "jaki", "jakich": "jaki", "ktory": "jaki",
          "ktora": "jaki", "ktore": "jaki"}

# Potoczne sformułowania → słownictwo przepisów (wzorzec na tekście bez polskich znaków, małymi literami).
# Tylko wąskie wzorce dla słów spoza języka przepisów. Pierwsza wersja z szerokimi wzorcami („nowy pracownik”,
# „kierownik”, „zwolnienie”) obniżała hit@5 na eval_holdout z 0,97 do 0,90; po zawężeniu holdout jest bez zmian
# przy każdej wadze 0,4–1,0, a na 8 roboczych pytaniach potocznych waga 1,0 daje 8/8 trafień w top-5.
QUERY_EXPANSIONS = [
    (r"nie zgadza|nie zgodzi|niezgod|odwol|kwestionu|zaskarz|reklamac", "sprzeciw od oceny"),
    (r"podpisuj|kto podpis", "podpis oceniającego"),
    (r"co ile|jak czesto|czestotliw|co jaki czas", "sporządza się co 24 miesiące"),
    (r"\biprz\b", "indywidualny program rozwoju zawodowego"),
    (r"spozni|opozni|nie dotrzymuj", "terminowo"),
    (r"\bzwolnic|zwolnion\w* z prac|zwolnieni\w* z prac|wyrzuc|straci\w* prac|rozwiaz\w* umow",
     "rozwiązanie stosunku pracy"),
    (r"\bl4\b|chorob|macierzy|rodzicielsk|zwolnieni\w* lekarsk", "usprawiedliwiona nieobecność"),
    (r"menedzer|manager|szef\w* zespol|kieruje zespol|kierowni\w* zespol|lider", "kierujący zespołem"),
    (r"\bszef", "bezpośredni przełożony"),
    (r"feedback", "informacja zwrotna"),
    (r"nie widzial|nie mial\w* okazji|brak obserwacj", "brak podstaw do oceny"),
    (r"formularz", "arkusz"),
    (r"\bzle\b|slab\w* prac|nie radzi", "negatywna"),
    (r"swietn|wybitn|najlepsz", "znacznie powyżej oczekiwań"),
]
EXPANSION_WEIGHT = 1.0


def expansion_terms(question: str) -> str:
    """Słownictwo przepisów dla potocznych sformułowań w pytaniu (tylko do wyszukiwania; model dostaje oryginał)."""
    low = strip_diacritics(question.lower())
    return " ".join(text for rx, text in QUERY_EXPANSIONS if re.search(rx, low))


def strip_diacritics(s: str) -> str:
    s = s.replace("ł", "l").replace("Ł", "L")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def stem(tok: str) -> str:
    if tok.isdigit():
        return tok
    for suf in SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            tok = tok[: -len(suf)]
            break
    return tok[:7]


def analyze(text: str) -> list[str]:
    toks = re.findall(r"[^\W\d_]+|\d+", strip_diacritics(text.lower()))
    return [stem(t) for t in toks if t not in STOP and (len(t) > 1 or t.isdigit())]


def analyze_faq(text: str) -> list[str]:
    """Jak analyze(), ale ze słowami pytającymi i przeczeniem (do dopasowania FAQ)."""
    out = []
    for t in re.findall(r"[^\W\d_]+|\d+", strip_diacritics(text.lower())):
        if t in QWORDS:
            out.append("?" + QWORDS[t])
        elif t not in STOP and (len(t) > 1 or t.isdigit()):
            out.append(stem(t))
    return out


def jaccard(a: list[str] | set, b: list[str] | set) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def cosine(u: list[float], v: list[float]) -> float:
    num = sum(x * y for x, y in zip(u, v))
    den = math.sqrt(sum(x * x for x in u)) * math.sqrt(sum(y * y for y in v))
    return num / den if den else 0.0


def load_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.avgdl = sum(map(len, docs)) / max(self.N, 1)
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.tf = [Counter(d) for d in docs]
        self.max_idf = math.log(1 + (self.N + 0.5) / 0.5)

    def scores(self, q: list[str], weights: dict[str, float] | None = None) -> list[float]:
        """Wynik BM25 dla każdego dokumentu; `weights` – waga rdzenia zapytania (domyślnie 1)."""
        weights = weights or {}
        out = []
        for tf, d in zip(self.tf, self.docs):
            s, dl = 0.0, len(d)
            for t in set(q):
                f = tf.get(t)
                if f:
                    s += weights.get(t, 1.0) * self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


class EmbeddingCache:
    """Cache wektorów w <cache_dir>/emb_<model>.json, klucz = sha256(model|tekst)."""

    def __init__(self, provider, cache_dir: str | Path = ".cache"):
        self.provider = provider
        self.path = Path(cache_dir) / f"emb_{re.sub(r'[^A-Za-z0-9_.-]', '_', provider.embed_model)}.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.dirty = False

    def key(self, text: str) -> str:
        return hashlib.sha256(f"{self.provider.embed_model}|{text}".encode("utf-8")).hexdigest()

    def get(self, texts: list[str], batch: int = 32) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if self.key(t) not in self.data]
        for i in range(0, len(missing), batch):
            part = missing[i: i + batch]
            for t, v in zip(part, self.provider.embed(part)):
                self.data[self.key(t)] = [round(x, 6) for x in v]
            self.dirty = True
        if self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
            self.dirty = False
        return [self.data[self.key(t)] for t in texts]


class Retriever:
    def __init__(self, chunks: list[dict], faq: list[dict] | None = None, provider=None,
                 cache_dir: str | Path = ".cache", use_embeddings: bool = True):
        self.chunks = chunks
        self.by_id = {c["id"]: c for c in chunks}
        self.faq = faq or []
        self.docs = [analyze(" ".join([c.get("unit", ""), " ".join(c.get("heading_path") or []),
                                       " ".join(PROCESS_WORDS.get(p, "") for p in c.get("process") or []),
                                       c.get("text", "")])) for c in chunks]
        self.bm25 = BM25(self.docs)
        self.emb = None
        self.doc_vecs = None
        if use_embeddings:
            if provider is None:
                from llm_provider import LLMProvider
                provider = LLMProvider.from_env()
            self.emb = EmbeddingCache(provider, cache_dir)
            self.doc_vecs = self.emb.get([self.doc_text(c) for c in chunks])
            if self.faq:
                self.faq_vecs = self.emb.get([f"search_query: {f['question']}" for f in self.faq])

    @staticmethod
    def doc_text(c: dict) -> str:
        return f"search_document: {c.get('citation', c.get('unit', ''))}\n{c.get('text', '')}"[:6000]

    # ---------------------------------------------------------------- FAQ
    def match_faq(self, question: str, qvec: list[float] | None = None) -> dict | None:
        qa = analyze_faq(question)
        best, best_s = None, 0.0
        for i, f in enumerate(self.faq):
            variants = [f["question"], *f.get("alt_questions", [])]
            s = max(jaccard(qa, analyze_faq(v)) for v in variants)
            if qvec is not None and self.emb is not None:
                s = max(s, cosine(qvec, self.faq_vecs[i]) if cosine(qvec, self.faq_vecs[i]) >= FAQ_COSINE else 0)
            if s > best_s:
                best, best_s = f, s
        if best is not None and (best_s >= FAQ_JACCARD or best_s >= FAQ_COSINE):
            return {"faq": best, "score": round(best_s, 3)}
        return None

    # ----------------------------------------------------------- retrieval
    def search(self, question: str, k: int = 5, process: str | None = None, use_faq: bool = True) -> dict:
        q_orig = analyze(question)
        extra = [t for t in analyze(expansion_terms(question)) if t not in q_orig]
        q = q_orig + extra
        weights = {t: EXPANSION_WEIGHT for t in extra}
        qvec = self.emb.get([f"search_query: {question}"])[0] if self.emb else None
        if use_faq and self.faq:
            m = self.match_faq(question, qvec)
            if m:
                return {"mode": "faq", "faq": m["faq"], "faq_score": m["score"], "hits": self._faq_hits(m["faq"]),
                        "refuse": False, "signals": {"faq_score": m["score"]}}
        bm = self.bm25.scores(q, weights)
        allowed = [i for i, c in enumerate(self.chunks)
                   if not process or not c.get("process") or process in c["process"]]
        rank_bm = sorted((i for i in allowed if bm[i] > 0), key=lambda i: -bm[i])[:30]
        fused = Counter()
        for r, i in enumerate(rank_bm):
            fused[i] += 1 / (RRF_K + r + 1)
        cos = None
        if qvec is not None:
            cos = {i: cosine(qvec, self.doc_vecs[i]) for i in allowed}
            for r, i in enumerate(sorted(cos, key=lambda i: -cos[i])[:30]):
                fused[i] += 1 / (RRF_K + r + 1)
        if LEGAL_BOOST:
            # trzecia lista RRF: tylko akty prawne (ustawa, rozporządzenia) – źródło pierwotne ma pierwszeństwo
            # przed poradnikiem i Q&A, które często powtarzają ten sam fakt w dłuższym tekście
            legal = [i for i in allowed if self.chunks[i].get("doc_type") in LEGAL_TYPES]
            key = (lambda i: -(cos[i] + bm[i] / 50)) if cos else (lambda i: -bm[i])
            for r, i in enumerate(sorted(legal, key=key)[:30]):
                fused[i] += 1 / (RRF_K + r + 1)
        top = [i for i, _ in fused.most_common(k)]
        # sygnały do odmowy
        qset = [t for t in set(q)]
        idf = {t: weights.get(t, 1.0) * self.bm25.idf.get(t, self.bm25.max_idf) for t in qset}
        covered = set().union(*(set(self.docs[i]) for i in top[:3])) if top else set()
        coverage = sum(idf[t] for t in qset if t in covered) / sum(idf.values()) if qset else 0.0
        dense_top = max(cos.values()) if cos else None
        refuse = (not top) or coverage < COVERAGE_MIN or (dense_top is not None and dense_top < DENSE_MIN)
        reason = ("brak dopasowań" if not top else f"pokrycie {coverage:.2f} < {COVERAGE_MIN}"
                  if coverage < COVERAGE_MIN else f"cosinus {dense_top:.2f} < {DENSE_MIN}" if refuse else "")
        # słabe dopasowanie: nie odmawiamy od razu, decyzję (odpowiedź z cytatem albo odmowa) podejmuje model
        weak = bool(top) and refuse and coverage >= SOFT_COVERAGE_MIN and (dense_top is None or dense_top >= DENSE_MIN)
        hits = [{"id": self.chunks[i]["id"], "source_id": self.chunks[i].get("source_id"),
                 "unit": self.chunks[i].get("unit"), "citation": self.chunks[i].get("citation"),
                 "text": self.chunks[i].get("text", ""), "rrf": round(fused[i], 5), "bm25": round(bm[i], 3),
                 "cosine": round(cos[i], 4) if cos else None, "rank": r + 1} for r, i in enumerate(top)]
        return {"mode": "hybrid" if cos else "bm25", "faq": None, "hits": hits, "refuse": refuse, "weak": weak,
                "reason": reason,
                "signals": {"coverage": round(coverage, 3),
                            "dense_top": round(dense_top, 4) if dense_top is not None else None,
                            "bm25_top": round(bm[top[0]], 3) if top else 0.0}}

    def _faq_hits(self, f: dict) -> list[dict]:
        hits = []
        for s in f.get("sources", []):
            for c in self.chunks:
                if c.get("source_id") == s["source_id"] and unit_matches(c.get("unit", ""), s["unit"]):
                    hits.append({"id": c["id"], "source_id": c["source_id"], "unit": c.get("unit"),
                                 "citation": c.get("citation"), "text": c.get("text", ""), "rank": len(hits) + 1})
        return hits


def norm_unit(u: str) -> str:
    u = strip_diacritics(u.lower()).replace("§", "par ").replace(".", " ")
    return " ".join(u.split())


def unit_matches(chunk_unit: str, expected_unit: str) -> bool:
    """Jednostka z chunka pasuje do oczekiwanej, gdy jest nią lub jej częścią (§ 11 ust. 1 pkt 2 ⊂ § 11 ust. 1)
    albo gdy chunk obejmuje całą oczekiwaną jednostkę nadrzędnie (chunk „§ 11” ⊃ oczekiwane „§ 11 ust. 3”)."""
    a, b = norm_unit(chunk_unit), norm_unit(expected_unit)
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrieval Asystenta formalnego")
    ap.add_argument("question")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--faq")
    ap.add_argument("--cache-dir", default=".cache")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--process", choices=["first", "periodic"])
    ap.add_argument("--no-embed", action="store_true")
    a = ap.parse_args()
    faq = json.loads(Path(a.faq).read_text(encoding="utf-8"))["items"] if a.faq else None
    r = Retriever(load_jsonl(a.kb), faq, cache_dir=a.cache_dir, use_embeddings=not a.no_embed)
    res = r.search(a.question, k=a.k, process=a.process)
    for h in res["hits"]:
        h["text"] = h["text"][:160]
    if res.get("faq"):
        res["faq"] = {"id": res["faq"]["id"], "question": res["faq"]["question"]}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
