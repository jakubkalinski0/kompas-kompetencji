import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from kompas_engine import load_config  # noqa: E402

EXAMPLES = SKILL_DIR / "assets" / "examples"


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def example():
    def _load(name: str) -> dict:
        return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    return _load
