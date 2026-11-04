"""Keep disposable test files in a fresh workspace directory on restricted Windows hosts."""
from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    if not config.option.basetemp:
        config.option.basetemp = str(Path(__file__).resolve().parents[1] / ".local" / f"pytest-{uuid4().hex}")
