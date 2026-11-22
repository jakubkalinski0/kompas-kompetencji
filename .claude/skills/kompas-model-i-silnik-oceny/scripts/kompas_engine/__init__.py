"""Kompas Kompetencji – deterministyczny silnik oceny (periodic_b, periodic_c, first_eval).

Sama biblioteka standardowa Pythona (3.10+). Jeden import dla backendu:

    from kompas_engine import evaluate, suggest_criterion, record_decision, load_config
"""
from .audit import record_decision, reconcile_overrides
from .config import load_config, load_model, load_schema
from .engine import evaluate, suggest_all
from .guard import run_guard
from .rules import first_eval_outcome, part3_status, periodic_outcome
from .scoring import band_for_average, fmt_pl, indicator_points, suggest_criterion
from .validate import schema_errors

__all__ = [
    "evaluate", "suggest_all", "suggest_criterion", "record_decision", "reconcile_overrides",
    "periodic_outcome", "first_eval_outcome", "part3_status", "run_guard", "schema_errors",
    "band_for_average", "indicator_points", "fmt_pl", "load_config", "load_model", "load_schema",
]
__version__ = "1.0.0"
