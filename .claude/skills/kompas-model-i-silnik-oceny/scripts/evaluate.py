"""CLI: przelicza dokument oceny (kontrakt C3) i wypisuje wynik JSON z walidacją.

Użycie:
    python scripts/evaluate.py --input assets/examples/anna_periodic_b.json --pretty
    python scripts/evaluate.py --input doc.json --model data/competency_model.json --method median --now 2026-11-21T15:00:00+01:00
    python scripts/evaluate.py --input doc.json --summary      # krótki raport tekstowy zamiast JSON

Kod wyjścia: 0 = brak błędów walidacji, 1 = są błędy walidacji, 2 = zły plik wejściowy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kompas_engine import evaluate, load_config, load_model  # noqa: E402


def summary(doc: dict) -> str:
    lines = [f"Formularz: {doc.get('form')} | oceniany: {doc.get('employee', {}).get('full_name')}"]
    for c in doc.get("criteria", []):
        s = c.get("suggestion") or {}
        lines.append(f"- {c.get('name')}: sugestia {s.get('points')} pkt [{s.get('formula')}] | decyzja: {c.get('final_points')}")
    lines.append(f"Średnia/ocena łączna: {doc.get('average_display')} | poziom: {(doc.get('overall_level') or {}).get('label') or '—'} | wynik: {doc.get('result')}")
    v = doc.get("validation", {})
    lines.append(f"Walidacja: ok={v.get('ok')} complete={v.get('complete')} błędy={len(v.get('errors', []))} ostrzeżenia={len(v.get('warnings', []))}")
    for e in v.get("errors", []):
        lines.append(f"  BŁĄD {e['rule_id']}: {e['message']}")
    for g in doc.get("guard", []):
        lines.append(f"  STRAŻNIK {g['rule_id']} ({g['severity']}): {g['message'][:140]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Silnik oceny Kompas Kompetencji")
    ap.add_argument("--input", required=True, help="Dokument oceny JSON (kontrakt C3)")
    ap.add_argument("--pretty", action="store_true", help="JSON z wcięciami")
    ap.add_argument("--summary", action="store_true", help="Krótki raport tekstowy")
    ap.add_argument("--model", help="competency_model.json (opcjonalnie: liczba wskaźników i kontrola id)")
    ap.add_argument("--config", help="Alternatywny forms_config.json")
    ap.add_argument("--method", choices=["mean", "median"], help="Reguła sugestii (domyślnie z configu)")
    ap.add_argument("--now", help="Znacznik czasu dla wpisów audit_log (ISO), dla powtarzalnych wyników")
    ap.add_argument("--output", help="Zapisz wynik do pliku zamiast na stdout")
    args = ap.parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"Nie można wczytać {args.input}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    config = load_config(args.config)
    model = load_model(args.model) if args.model else None
    result = evaluate(doc, config=config, model=model, now=args.now, method=args.method)
    text = summary(result) if args.summary else json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0 if result["validation"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
