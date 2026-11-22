import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from privacy_shield import ShieldContext, mask, preview, unmask  # noqa: E402

CTX = ShieldContext(employee="Jan Testowy", evaluator="Marek Kierownik-Demo", others=["Zofia Kadrowa-Demo"])


def test_names_in_inflected_forms():
    t = ("Jan Testowy przygotował raport. Rozmawiałem z Janem Testowym, a Jana Testowego chwalił klient. "
         "Testowemu brakuje czasu. Marek Kierownik-Demo zatwierdził, Zofia Kadrowa-Demo przypomniała.")
    r = mask(t, CTX)
    assert "Testow" not in r.text and "Jan " not in r.text and "Kierownik-Demo" not in r.text
    assert "Kadrow" not in r.text
    assert r.text.count("Pracownik A") == 4
    assert "Przełożony" in r.text and "Osoba B" in r.text


def test_female_forms():
    r = mask("Notatka o Annie Przykładowej: Anna Przykładowa prowadziła zespół; z Anną Przykładową.",
             ShieldContext(employee="Anna Przykładowa"))
    assert "Przykładow" not in r.text and "Ann" not in r.text
    assert r.counts["Pracownik A"] == 3


def test_identifiers():
    t = ("PESEL 85010112345, mail jan.testowy@mc.gov.pl, tel. +48 600 123 456 oraz (22) 245 59 00, "
         "adres ul. Królewska 27/3, 00-060 Warszawa, NIP 123-456-32-18, dowód ABC123456.")
    r = mask(t, CTX)
    for token in ["[PESEL]", "[E-MAIL]", "[TELEFON]", "[ADRES]", "[NIP]", "[DOWÓD]"]:
        assert token in r.text, token
    for raw in ["85010112345", "jan.testowy", "600 123 456", "245 59 00", "Królewska", "00-060", "ABC123456"]:
        assert raw not in r.text, raw


def test_legal_text_untouched():
    t = ("Zgodnie z § 11 ust. 1 pkt 2 rozporządzenia z 4 kwietnia 2016 r. (Dz. U. poz. 470) i art. 83 ust. 1 "
         "ustawy sprzeciw wnosi się w 7 dni; ocena 21.11.2026 r., średnia 5,40 pkt; Departament Cyberbezpieczeństwa.")
    r = mask(t, CTX)
    assert r.text == t


def test_third_party_detection_and_unmask():
    t = "Jan Testowy pomagał Tomaszowi Zielińskiemu przy projekcie, a Tomasz Zieliński to docenił."
    r = mask(t, CTX)
    assert "Zieliński" not in r.text and "Zielińskiemu" not in r.text
    assert r.text.count("Osoba") == 2
    back = unmask("Pracownik A wspierał zespół.", r.mapping)
    assert back == "Jan Testowy wspierał zespół."


def test_preview_has_no_originals():
    p = preview("Ewa Fikcyjna, PESEL 90020212345, przygotowała analizę.", ShieldContext(employee="Ewa Fikcyjna"))
    assert "Fikcyj" not in p["masked_text"] and "90020212345" not in p["masked_text"]
    labels = {x["label"] for x in p["replacements"]}
    assert {"Pracownik A", "[PESEL]"} <= labels
    assert "Fikcyjna" not in str(p["replacements"])
