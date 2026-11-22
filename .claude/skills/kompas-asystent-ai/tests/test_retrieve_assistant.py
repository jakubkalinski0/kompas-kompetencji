"""Testy retrievalu i Asystenta na małym fikstrurowym korpusie (bez Ollamy: atrapa LLM i embeddingów)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import retrieve  # noqa: E402
from assistant import (DECISION_REFUSAL, REFUSAL, Assistant, bracket_known_ids, normalize_citations,  # noqa: E402
                       output_filter)
from llm_provider import ChatResult  # noqa: E402
from retrieve import (Retriever, analyze, analyze_faq, load_jsonl, stem, strip_diacritics,  # noqa: E402
                      unit_matches)

KB = HERE / "fixtures" / "kb_fixture.jsonl"
FAQ = json.loads((HERE.parent / "assets" / "faq_kb.json").read_text(encoding="utf-8"))["items"]


class FakeLLM:
    """Atrapa LLMProvider: embeddingi = worek rdzeni (hash), czat = odpowiedź z pierwszym id ze źródeł."""
    embed_model = "fake"

    def __init__(self, reply=None):
        self.reply = reply
        self.calls = []

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 64
            for tok in analyze(t.split(":", 1)[-1]):
                v[hash(tok) % 64] += 1.0
            out.append(v)
        return out

    def chat(self, messages, **kw):
        self.calls.append(messages)
        user = messages[-1]["content"]
        first_id = user.split('<zrodlo id="', 1)[1].split('"', 1)[0] if '<zrodlo id="' in user else "x"
        text = self.reply or f"Sprzeciw wnosi się w terminie 7 dni od dnia zapoznania się z oceną [{first_id}]."
        return ChatResult(text=text, model="fake", provider="fake", latency_s=0.01, completion_tokens=12)


def test_polish_normalization():
    assert strip_diacritics("Łódź żółć") == "Lodz zolc"
    assert stem("oceny") == stem("ocena") == stem("oceną".replace("ą", "a"))
    assert stem("terminie") == stem("terminu") == "termin"
    assert analyze("sprzeciwu") == analyze("sprzeciw") == ["sprzeci"]  # obcięcie do 7 znaków


def test_unit_matching_parent_child():
    assert unit_matches("§ 11 ust. 1", "§ 11")
    assert unit_matches("art. 81", "art. 81 ust. 4")
    assert not unit_matches("§ 1", "§ 11")
    assert not unit_matches("art. 8", "art. 81 ust. 4")


def test_bm25_finds_objection_article():
    r = Retriever(load_jsonl(KB), use_embeddings=False)
    res = r.search("Ile dni mam na złożenie sprzeciwu od oceny okresowej?", k=3, use_faq=False)
    assert res["hits"][0]["id"] == "ustawa_sc:art83:ust1"
    assert not res["refuse"]


def test_out_of_scope_is_refused_by_coverage():
    r = Retriever(load_jsonl(KB), use_embeddings=False)
    res = r.search("Jakie są stawki diet za zagraniczną podróż służbową?", k=3, use_faq=False)
    assert res["refuse"]


def test_faq_exact_match_layer():
    r = Retriever(load_jsonl(KB), FAQ, use_embeddings=False)
    res = r.search("Ile kryteriów dodatkowych można wybrać w ocenie okresowej?")
    assert res["mode"] == "faq" and res["faq"]["id"] == "faq_periodic_06"
    assert res["hits"] and res["hits"][0]["id"] == "rozp2016:par5:ust2"


def test_embedding_cache_and_hybrid(tmp_path):
    r = Retriever(load_jsonl(KB), provider=FakeLLM(), cache_dir=tmp_path)
    old = retrieve.DENSE_MIN
    retrieve.DENSE_MIN = 0.0
    try:
        res = r.search("negatywna ocena okresowa kiedy", k=3, use_faq=False)
    finally:
        retrieve.DENSE_MIN = old
    assert res["mode"] == "hybrid" and res["hits"]
    assert list(tmp_path.glob("emb_fake.json"))


def make_assistant(reply=None):
    a = Assistant(KB, provider=FakeLLM(reply), use_embeddings=False)
    return a


def test_assistant_formal_answer_with_valid_citation():
    a = make_assistant()
    res = a.answer("Do kogo i w jakim terminie wnosi się sprzeciw od oceny okresowej?", "formal")
    assert not res["refused"]
    assert res["citations"] and res["citations"][0]["id"] in a.retriever.by_id
    assert res["citations"][0]["fragment"]


def test_assistant_refuses_decision_request_without_llm():
    a = make_assistant()
    res = a.answer("Ile punktów powinienem dać Janowi z komunikacji?", "formal")
    assert res["refused"] and res["answer"] == DECISION_REFUSAL
    assert a.llm.calls == []


def test_assistant_rejects_answer_with_fabricated_citation():
    a = make_assistant(reply="Termin wynosi 30 dni [rozp2099:par1].")
    res = a.answer("Pracownik chce zakwestionować ocenę okresową – ile ma dni na sprzeciw?", "formal")
    assert res["refused"] and res["answer"] == REFUSAL


def test_native_gpt_oss_citation_brackets_are_accepted():
    # gpt-oss pisze czasem 【id】 albo [a, b] – to nadal poprawny cytat z kontekstu, nie powód do odmowy
    assert normalize_citations("Termin 7 dni【ustawa_sc:art83:ust1】.") == "Termin 7 dni[ustawa_sc:art83:ust1]."
    assert normalize_citations("Tak [rozp2016:par5, ustawa_sc:art81].") == "Tak [rozp2016:par5][ustawa_sc:art81]."
    a = make_assistant(reply="Sprzeciw wnosi się w terminie 7 dni【ustawa_sc:art83:ust1】.")
    res = a.answer("Pracownik nie zgadza się z oceną okresową – ile ma dni na sprzeciw?", "formal")
    assert not res["refused"] and res["citations"][0]["id"] == "ustawa_sc:art83:ust1"
    # nawias okrągły (mały model lokalny): tylko identyfikator z kontekstu, zmyślony dalej daje odmowę
    assert bracket_known_ids("Termin (ustawa_sc:art83:ust1 ust. 1).", {"ustawa_sc:art83:ust1"}) == "Termin [ustawa_sc:art83:ust1]."
    assert bracket_known_ids("Termin (ustawa_sc:art8).", {"ustawa_sc:art83"}) == "Termin (ustawa_sc:art8)."
    bad = make_assistant(reply="Termin wynosi 30 dni (rozp2099:par1).")
    assert bad.answer("Pracownik chce zakwestionować ocenę okresową – ile ma dni na sprzeciw?", "formal")["refused"]


def test_faq_keeps_question_words_and_negation():
    r = Retriever(load_jsonl(KB), FAQ, use_embeddings=False)
    assert r.match_faq("Kto sporządza ocenę okresową?") is None  # nie „Jak często sporządza się…”
    assert r.match_faq("Kiedy nie sporządza się oceny okresowej?") is None
    assert analyze_faq("Kto nie sporządza?")[:2] == ["?kto", "?nie"]


def test_weak_retrieval_goes_to_model_and_followup_uses_history():
    a = make_assistant()
    res = a.answer("Czy mogę się nie zgodzić?", "formal",
                   {"history": [{"q": "Do kogo i w jakim terminie wnosi się sprzeciw od oceny okresowej?", "a": "Do DG."}]})
    assert not res["refused"] and res["followup"]
    sent = a.llm.calls[-1]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]  # tura historii przed pytaniem
    assert "Do DG." in sent[2]["content"] and "<zrodlo" not in sent[1]["content"]


def test_output_filter_blocks_level_proposals_but_not_scale_explanations():
    txt = ("Skala: 5 punktów – na poziomie oczekiwań. Proponuję przyznać 7 punktów za komunikację. "
           "Pracownik A powinien otrzymać ocenę pozytywną.")
    strict, n = output_filter(txt, strict=True)
    assert n == 2 and "Proponuję" not in strict and "5 punktów – na poziomie oczekiwań" in strict
    soft, n2 = output_filter("Zgodnie z § 11 przyznaje się 5 punktów za poziom oczekiwań.", strict=False)
    assert n2 == 0


def test_output_filter_keeps_list_lines():
    txt = "Pytania:\n1. Jakie zadania były najważniejsze?\n2. Proponuję przyznać 7 punktów za komunikację.\n3. Co pomogło?"
    out, n = output_filter(txt, strict=True)
    assert n == 1 and out.splitlines()[:3] == ["Pytania:", "1. Jakie zadania były najważniejsze?", "3. Co pomogło?"]


def test_conversation_masks_pii_and_restores_locally():
    llm = FakeLLM(reply="Pracownik A przygotował raport w terminie [rozp2016:par7].")
    a = Assistant(KB, provider=llm, use_embeddings=False)
    ctx = {"action": "feedback", "process": "periodic", "employee": "Jan Testowy", "evaluator": "Marek Kierownik-Demo",
           "notes": [{"criterion": "komunikacja", "note": "Jan Testowy (PESEL 85010112345) przygotował raport."}]}
    res = a.answer("", "conversation", ctx)
    sent = json.dumps(llm.calls[-1], ensure_ascii=False)
    assert "Testow" not in sent and "85010112345" not in sent and "Pracownik A" in sent
    assert res["answer"].startswith("Jan Testowy")
    assert res["privacy_preview"]["replacements"]


def test_conversation_development_blocked_after_negative_first_eval():
    a = make_assistant()
    res = a.answer("", "conversation", {"action": "development", "process": "first", "decided_result": "negatywna"})
    assert res["refused"] and "pozytywnej" in res["answer"]


def test_provider_extra_fields_reach_openai_compat_payload_only():
    from llm_provider import LLMProvider
    sent = []
    p = LLMProvider("openai_compat", base_url="http://localhost:9/v1", model="m", api_key="x")
    p._post = lambda url, payload, auth: sent.append(payload) or {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    p.chat([{"role": "user", "content": "q"}], extra={"reasoning_effort": "low"})
    assert sent[-1]["reasoning_effort"] == "low" and sent[-1]["max_tokens"] == 700
    o = LLMProvider("ollama", base_url="http://localhost:9", model="m")
    o._post = lambda url, payload, auth: sent.append(payload) or {"message": {"content": "ok"}}
    o.chat([{"role": "user", "content": "q"}], extra={"reasoning_effort": "low"})
    assert "reasoning_effort" not in sent[-1]
