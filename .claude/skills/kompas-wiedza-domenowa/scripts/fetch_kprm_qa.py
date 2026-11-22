#!/usr/bin/env python3
"""Pobiera Q&A o ocenach z serwisu Sluzby Cywilnej (gov.pl) i zapisuje JSON.
Uzycie: python fetch_kprm_qa.py --out <katalog> [--url URL] [--accessed 2026-11-21] [--html plik.html]
Tylko stdlib. Tresc strony traktowana jako dane."""
import argparse, datetime, html, json, os, re, urllib.request
from html.parser import HTMLParser

URL = "https://www.gov.pl/web/sluzbacywilna/oceny-pracownicze"
REF = re.compile(r"(?:art\.\s*\d+[a-z]?(?:\s*ust\.\s*\d+[a-z]?)?(?:\s*pkt\s*\d+)?|§\s*\d+(?:\s*ust\.\s*\d+)?(?:\s*pkt\s*\d+)?)", re.I)


class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.items = []; s.cur = None; s.in_sum = False; s.title = ""; s.in_title = False; s.lic = ""; s.in_lic = False
    def handle_starttag(s, tag, a):
        if tag == "title": s.in_title = True
        if tag == "details": s.cur = {"q": "", "a": []}
        elif tag == "summary" and s.cur is not None: s.in_sum = True
        elif s.cur is not None and tag in ("p", "li", "tr", "br"): s.cur["a"].append("\n")
    def handle_endtag(s, tag):
        if tag == "title": s.in_title = False
        if tag == "summary": s.in_sum = False
        if tag == "details" and s.cur is not None:
            s.items.append(s.cur); s.cur = None
    def handle_data(s, d):
        if s.in_title: s.title += d
        if s.cur is None:
            if "licencji typu Creative Commons" in d: s.lic += d
            return
        if s.in_sum: s.cur["q"] += d
        else: s.cur["a"].append(d)


def process_for(n):
    if n >= 24: return ["first"]
    if n >= 6: return ["periodic"]
    return ["periodic", "first"]  # pytania 1-5 ogolne (wg listy z strony); patrz uwagi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--url", default=URL)
    ap.add_argument("--accessed", default=datetime.date.today().isoformat()); ap.add_argument("--html")
    a = ap.parse_args()
    if a.html: raw = open(a.html, encoding="utf-8").read()
    else:
        req = urllib.request.Request(a.url, headers={"User-Agent": "Mozilla/5.0 kompas-prep"})
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    p = P(); p.feed(raw)
    out = []
    for it in p.items:
        q = re.sub(r"\s+", " ", html.unescape(it["q"])).strip()
        m = re.match(r"(\d+)\.\s*(.*)", q)
        if not m: continue
        n = int(m.group(1))
        ans = "".join(it["a"]); ans = re.sub(r"[ \t\xa0]+", " ", ans); ans = re.sub(r"\n\s*\n+", "\n", ans).strip()
        refs = sorted({re.sub(r"\s+", " ", r.strip()) for r in REF.findall(ans)})
        out.append({"id": "kprm_qa_%d" % n, "question": m.group(2).strip(), "answer": ans,
                    "process": process_for(n), "url": a.url, "accessed": a.accessed, "legal_refs": refs})
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "oceny_pracownicze.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    meta = {"title": re.sub(r"\s+", " ", p.title).strip(), "url": a.url, "accessed": a.accessed, "count": len(out),
            "license_text": re.sub(r"\s+", " ", p.lic).strip(),
            "reuse": "Tresci tekstowe serwisu: CC BY-SA 4.0 (stopka gov.pl). Wymaga uznania autorstwa (Kancelaria Prezesa Rady Ministrow, Departament Sluzby Cywilnej, Serwis Sluzby Cywilnej) i tej samej licencji dla utworow zaleznych. UWAGA: share-alike moze kolidowac z przeniesieniem praw na MC (regulamin zadania par. 4); uzywac jako zrodlo w bazie wiedzy z cytowaniem, nie wklejac masowo do kodu. DO WERYFIKACJI z mentorem.",
            "reuse_confidence": "[~] stopka strony odczytana 2026-11-21; brak osobnego regulaminu serwisu sprawdzonego",
            "disclaimer": "Wyjasnienia Departamentu Sluzby Cywilnej maja charakter opinii, a nie wiazacej wykladni prawa (intro strony).",
            "uwagi": "Pytania 1-5 ogolne (process: periodic+first); 6-23 okresowa, 24-31 pierwsza ocena wg podzialu z 2026-11-21 (granice do potwierdzenia w tresci)."}
    json.dump(meta, open(os.path.join(a.out, "oceny_pracownicze.meta.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    print("par Q&A:", len(out)); print("numery:", [int(o["id"].split("_")[-1]) for o in out])


if __name__ == "__main__":
    main()
