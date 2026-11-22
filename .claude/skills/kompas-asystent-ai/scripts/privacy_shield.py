"""Privacy Shield: maskowanie danych osobowych przed wysłaniem kontekstu do LLM (tylko stdlib).

Co maskuje:
  * osoby z kontekstu procesu (oceniany → „Pracownik A”, oceniający → „Przełożony”, inni → „Osoba B”, „Osoba C”…),
    także w odmianie (Jana Testowego, Annie Przykładowej, Ewą Fikcyjną) – dopasowanie po rdzeniu imienia/nazwiska;
  * osoby trzecie w notatkach: popularne imię + słowo z wielkiej litery („Tomaszowi Zielińskiemu”) → „Osoba B”;
  * PESEL (11 cyfr) → [PESEL], e-mail → [E-MAIL], telefon → [TELEFON], adres (ul./al./pl./os. + numer,
    kod pocztowy z miejscowością) → [ADRES], NIP → [NIP], nr dowodu osobistego → [DOWÓD].

Ograniczenia (opisz je w UI i w dokumentacji): heurystyka, nie gwarancja; nie rozpozna nazwiska bez imienia,
jeśli osoba nie jest w kontekście procesu; rdzeń imienia może zamaskować podobne słowo (np. „Jan” → „Janina”);
nie usuwa opisów pozwalających zidentyfikować osobę pośrednio („jedyna radczyni w wydziale”).

API:
  ctx = ShieldContext(employee="Jan Testowy", evaluator="Marek Kierownik-Demo", others=["Zofia Kadrowa-Demo"])
  res = mask(text, ctx)   -> MaskResult(text, mapping, counts)
  unmask(llm_output, res.mapping)  # przywraca nazwiska lokalnie, po odpowiedzi LLM
  preview(text, ctx)      -> dict do panelu „Co wysyłamy do AI”
CLI: python privacy_shield.py --employee "Jan Testowy" --evaluator "Marek Kierownik-Demo" --text "..."
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

UP = "A-ZĄĆĘŁŃÓŚŹŻ"
LO = "a-ząćęłńóśźż"
W = f"[{UP}{LO}]"

# Rdzenie popularnych imion (do wykrywania osób trzecich w notatkach, w odmianie).
COMMON_FIRST_NAME_STEMS = [
    "Adam", "Agnieszk", "Aleksand", "Andrzej", "Ann", "Barbar", "Bartosz", "Beat", "Dariusz", "Dorot", "Ew",
    "Grzegorz", "Iwon", "Jacek", "Jack", "Jakub", "Jan", "Janusz", "Jerzy", "Joann", "Józef", "Justyn", "Kamil",
    "Karol", "Katarzyn", "Krystyn", "Krzysztof", "Łukasz", "Maciej", "Magdalen", "Małgorzat", "Marcin", "Marek",
    "Mark", "Mari", "Marta", "Mart", "Michał", "Monik", "Natali", "Pawł", "Paweł", "Piotr", "Rafał", "Robert",
    "Stanisław", "Tomasz", "Wojciech", "Zbigniew", "Zofi", "Zuzann",
]

PATTERNS = [
    ("[E-MAIL]", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("[PESEL]", re.compile(r"(?<![\d.,/-])\d{11}(?!\d|[.,/-]\d)")),
    ("[NIP]", re.compile(r"\b\d{3}-\d{3}-\d{2}-\d{2}\b|\b\d{3}-\d{2}-\d{2}-\d{3}\b")),
    ("[DOWÓD]", re.compile(r"\b[A-Z]{3}\s?\d{6}\b")),
    ("[TELEFON]", re.compile(r"(?<![\w/.-])(?:\+48[\s-]?)?(?:\(\d{2}\)\s?\d{3}[\s-]?\d{2}[\s-]?\d{2}|"
                             r"\d{3}[\s-]\d{3}[\s-]\d{3}|\d{2}[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}|(?<=\+48)\d{9}|"
                             r"(?<=\+48 )\d{9}|\b\d{9}\b)(?![\w/-]|\.\w)")),  # kropka kończąca zdanie nie blokuje
    ("[ADRES]", re.compile(rf"\b(?:ul\.|al\.|pl\.|os\.|ulica|aleja)\s+[{UP}0-9][{LO}{UP}.\- ]{{1,40}}?\s\d+[a-zA-Z]?"
                           rf"(?:\s?/\s?\d+[a-zA-Z]?|\s(?:m\.|lok\.)\s?\d+)?(?:,\s*\d{{2}}-\d{{3}}\s+[{UP}][{LO}]+"
                           rf"(?:[\s-][{UP}][{LO}]+)?)?")),
    ("[ADRES]", re.compile(rf"\b\d{{2}}-\d{{3}}\s+[{UP}][{LO}]+(?:[\s-][{UP}][{LO}]+)?")),
]


def _stem(word: str) -> str:
    """Rdzeń do dopasowania form fleksyjnych imienia/nazwiska."""
    if len(word) >= 5:
        return word[:-2] if word[-1] in "aeiouyąę" or word[-2:] in {"ek", "eł"} else word[:-1] if len(word) > 6 else word
    if len(word) == 4:
        return word[:-1]
    if len(word) == 3 and word[-1] in "aeiouy":
        return word[:-1]
    return word


def _name_regex(full_name: str) -> list[re.Pattern]:
    parts = [p for p in full_name.split() if p]
    if not parts:
        return []
    def part_rx(p: str) -> str:
        return "-".join(re.escape(_stem(s)) + rf"{W}{{0,5}}" for s in p.split("-"))
    rx = []
    if len(parts) >= 2:
        first, last = parts[0], " ".join(parts[1:])
        last_rx = r"\s+".join(part_rx(x) for x in last.split())
        rx.append(re.compile(rf"(?<!{W}){part_rx(first)}\s+{last_rx}(?!{W})"))
        rx.append(re.compile(rf"(?<!{W}){last_rx}\s+{part_rx(first)}(?!{W})"))  # „Testowy Jan”
        rx.append(re.compile(rf"(?<!{W}){last_rx}(?!{W})"))
        rx.append(re.compile(rf"(?<!{W}){part_rx(first)}(?!{W})"))
    else:
        rx.append(re.compile(rf"(?<!{W}){part_rx(parts[0])}(?!{W})"))
    return rx


@dataclass
class ShieldContext:
    employee: str | None = None
    evaluator: str | None = None
    others: list[str] = field(default_factory=list)
    employee_label: str = "Pracownik A"
    evaluator_label: str = "Przełożony"


@dataclass
class MaskResult:
    text: str
    mapping: dict  # etykieta -> oryginał (tylko lokalnie, nigdy do LLM)
    counts: dict   # etykieta -> liczba zamian


def mask(text: str, ctx: ShieldContext | None = None, detect_third_parties: bool = True) -> MaskResult:
    ctx = ctx or ShieldContext()
    mapping: dict[str, str] = {}
    counts: dict[str, int] = {}

    def sub(rx: re.Pattern, label: str, s: str) -> str:
        new, n = rx.subn(label, s)
        if n:
            counts[label] = counts.get(label, 0) + n
        return new

    out = text
    for label, rx in PATTERNS:  # najpierw identyfikatory (PESEL przed telefonem itd.)
        out = sub(rx, label, out)
    people = []
    if ctx.employee:
        people.append((ctx.employee_label, ctx.employee))
    if ctx.evaluator:
        people.append((ctx.evaluator_label, ctx.evaluator))
    letters = iter("BCDEFGHIJKLMNOPRSTUWZ")
    for o in ctx.others:
        people.append((f"Osoba {next(letters)}", o))
    for label, name in people:
        mapping[label] = name
        for rx in _name_regex(name):
            out = sub(rx, label, out)
    if detect_third_parties:
        stems = "|".join(sorted(COMMON_FIRST_NAME_STEMS, key=len, reverse=True))
        rx3 = re.compile(rf"(?<!{W})(?:{stems}){W}{{0,4}}\s+[{UP}][{LO}]+(?:-[{UP}][{LO}]+)?(?!{W})")
        protected = set(mapping) | {"Pracownik", "Przełożony", "Osoba"}
        seen: dict[str, str] = {}
        def repl(m: re.Match) -> str:
            found = m.group(0)
            if found.split()[0] in protected:
                return found
            key = found.split()[1][:5]
            if key not in seen:
                seen[key] = f"Osoba {next(letters)}"
                mapping[seen[key]] = found
            counts[seen[key]] = counts.get(seen[key], 0) + 1
            return seen[key]
        out = rx3.sub(repl, out)
    return MaskResult(out, mapping, counts)


def unmask(text: str, mapping: dict) -> str:
    """Przywraca nazwiska w odpowiedzi LLM (forma podstawowa) – wyłącznie po stronie serwera/UI."""
    for label in sorted(mapping, key=len, reverse=True):
        text = text.replace(label, mapping[label])
    return text


def preview(text: str, ctx: ShieldContext | None = None) -> dict:
    """Dane do panelu „Co wysyłamy do AI”: zamaskowany tekst + liczniki, bez oryginałów."""
    r = mask(text, ctx)
    leftovers = re.findall(rf"(?<!{W})[{UP}][{LO}]{{2,}}\s+[{UP}][{LO}]{{2,}}(?:ski|cki|dzki|ska|cka|dzka|"
                           rf"skiego|skiej|wicz|wiczem|ak|ek)(?!{W})", r.text)
    return {"masked_text": r.text,
            "replacements": [{"label": k, "count": v} for k, v in sorted(r.counts.items())],
            "warnings": [f"Możliwe niezamaskowane nazwisko: „{x}” – sprawdź przed wysłaniem." for x in leftovers]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--employee")
    ap.add_argument("--evaluator")
    ap.add_argument("--other", action="append", default=[])
    ap.add_argument("--text", required=True)
    a = ap.parse_args()
    print(json.dumps(preview(a.text, ShieldContext(a.employee, a.evaluator, a.other)), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
