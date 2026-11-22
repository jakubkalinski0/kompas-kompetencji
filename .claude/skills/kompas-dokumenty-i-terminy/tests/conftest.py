import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
EXAMPLES = SKILL / "assets" / "examples"


@pytest.fixture
def example():
    def load(name: str) -> dict:
        return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    return load
