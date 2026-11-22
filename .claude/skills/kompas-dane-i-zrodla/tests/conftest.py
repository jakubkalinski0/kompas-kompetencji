import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def pytest_addoption(parser):
    parser.addoption("--materials", action="store", default=None,
                     help="katalog materialow Partnera (albo zmienna KOMPAS_MATERIALY)")


@pytest.fixture(scope="session")
def materials(request) -> Path:
    m = request.config.getoption("--materials") or os.environ.get("KOMPAS_MATERIALY")
    if not m or not Path(m).is_dir():
        pytest.skip("brak materialow Partnera: podaj --materials <katalog> albo KOMPAS_MATERIALY")
    return Path(m)


@pytest.fixture(scope="session")
def built(materials, tmp_path_factory) -> Path:
    import build_data
    out = tmp_path_factory.mktemp("processed")
    rc = build_data.main(["--input", str(materials), "--output", str(out)])
    assert rc == 0, "build_data.py zakonczyl sie bledem"
    return out
