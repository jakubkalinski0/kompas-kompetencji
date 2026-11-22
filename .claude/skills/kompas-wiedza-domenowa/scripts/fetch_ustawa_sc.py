#!/usr/bin/env python3
"""Pobiera aktualny tekst jednolity ustawy o sluzbie cywilnej z API ELI Sejmu i zapisuje
go zgodnie z kontraktem C2 (kazdy artykul od nowej linii 'Art. N.') + meta.json.

Uzycie:
  python fetch_ustawa_sc.py --out <katalog> [--eli DU/2026/590] [--accessed 2026-11-21]
  python fetch_ustawa_sc.py --check <plik.txt>      # tylko kontrola obecnosci artykulow
Zaleznosci: stdlib + polecenie `pdftotext` (poppler). Bez kluczy API.
"""
import urllib.parse, argparse, json, re, subprocess, sys, tempfile, urllib.request, os, datetime

API = "https://api.sejm.gov.pl/eli/acts/"
REQUIRED_ARTS = ["35", "36", "37", "38", "81", "82", "83", "84", "86", "89"]
FOOT = re.compile(r"^\d+\) (W tym brzmieniu|W brzmieniu|Dodan|Przez art|Obowiązuje|Zmiany tekstu|"
                  r"Zdanie pierwsze|Utracił|Art\. \d+ zawiera|Zmiany wymienionej|Zmieniony|Wyrok)")
HDR = re.compile(r"^Dziennik Ustaw$")


def http(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "kompas-prep/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else json.loads(data.decode("utf-8"))


def find_latest_tj(year_from=2026):
    res = http(API + "search?title=" + urllib.parse.quote("jednolitego tekstu ustawy o służbie cywilnej") + "&publisher=DU&limit=50")
    cands = [a for a in res["items"] if "ogłoszenia jednolitego tekstu ustawy o służbie cywilnej" in a["title"]
             and a["title"].startswith("Obwieszczenie Marszałka Sejmu")]
    cands.sort(key=lambda a: (a["announcementDate"], a["pos"]), reverse=True)
    return cands[0]


def clean(raw):
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("USTAWA z dnia 21 listopada 2008"))
    out, i = [], start
    lines = lines[start:]
    i = 0
    while i < len(lines):
        l = lines[i].rstrip()
        if HDR.match(l):                       # naglowek strony: 'Dziennik Ustaw' / '– N –' / 'Poz. N'
            j = i + 1
            while j < len(lines) and j < i + 6 and (not lines[j].strip() or re.match(r"^[–-]\s*\d+\s*[–-]$", lines[j].strip()) or lines[j].strip().startswith("Poz.")):
                j += 1
            i = j
            continue
        if FOOT.match(l):
            l = "[przypis] " + l
        if l.strip():
            out.append(l)
        i += 1
    return "\n".join(out) + "\n"


def check(text):
    missing = [a for a in REQUIRED_ARTS if not re.search(r"^Art\. %s\." % a, text, re.M)]
    arts = re.findall(r"^Art\. (\d+[a-z]*)\.", text, re.M)
    print("liczba artykulow (linie 'Art. N.'):", len(arts))
    for a in ("81", "82", "83", "84", "89"):
        m = re.search(r"^Art\. %s\..*" % a, text, re.M)
        print("Art. %s:" % a, (m.group(0)[:90] if m else "BRAK"))
    for kw in ("służba przygotowawcza", "służbę przygotowawczą", "służby przygotowawczej", "pierwsz"):
        print("fraza %r: %d wystapien" % (kw, len(re.findall(kw, text, re.I))))
    print("BRAKUJE:", missing or "nic")
    return not missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--eli", help="np. DU/2026/590 (domyslnie: najnowsze obwieszczenie o t.j.)")
    ap.add_argument("--accessed", default=datetime.date.today().isoformat())
    ap.add_argument("--check")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check(open(a.check, encoding="utf-8").read()) else 1)
    if not a.out:
        ap.error("--out lub --check")
    import urllib.parse  # noqa
    eli = a.eli or find_latest_tj()["ELI"]
    meta_ob = http(API + eli)
    pdf = http(API + eli + "/text.pdf", binary=True)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "t.pdf")
        open(p, "wb").write(pdf)
        raw = subprocess.run(["pdftotext", "-enc", "UTF-8", p, "-"], capture_output=True, check=True).stdout.decode("utf-8")
    text = clean(raw)
    os.makedirs(a.out, exist_ok=True)
    open(os.path.join(a.out, "ustawa_o_sluzbie_cywilnej.txt"), "w", encoding="utf-8", newline="\n").write(text)
    meta = {
        "title": "Ustawa z dnia 21 listopada 2008 r. o służbie cywilnej – tekst jednolity",
        "dz_u": "Dz. U. " + str(meta_ob["year"]) + " poz. " + str(meta_ob["pos"]) + " (obwieszczenie Marszałka Sejmu z " + meta_ob["announcementDate"] + ")",
        "eli": "https://eli.gov.pl/eli/" + meta_ob["ELI"] + "/ogl",
        "url": API + eli + "/text.pdf",
        "accessed": a.accessed,
        "stan_prawny_na": meta_ob.get("legalStatusDate"),
        "uwagi": "Tekst z PDF obwieszczenia (pdftotext), naglowki stron usunięte, przypisy dolne oznaczone prefiksem [przypis]. "
                 "Wersja urzedowa to PDF w Dz. U.; ten plik sluzy do wyszukiwania i cytowania. "
                 "Kontrola zmian po t.j. patrz research/02_proces_i_przepisy.md.",
    }
    json.dump(meta, open(os.path.join(a.out, "ustawa_o_sluzbie_cywilnej.meta.json"), "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
    ok = check(text)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
