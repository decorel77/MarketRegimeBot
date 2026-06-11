"""QA-003 shared fixtures: artifact sandbox + production integrity guard.

The test suite used to overwrite the production artifacts under
``data/system/`` (``regime_export.json``, ``result_snapshot.json``,
``_test_regime_export.json``), replacing real yfinance-derived content with
fixtures that consumers then read. These fixtures make every test write under
pytest's ``tmp_path`` instead and prove the production directory stays
byte-identical across the whole suite.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from utils import regime_export_writer
from workflow import regime_cycle

# Real production locations, captured at import time — before any sandboxing.
REAL_PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_SYSTEM_DIR = REAL_PROJECT_ROOT / "data" / "system"


def _system_dir_state() -> dict[str, str]:
    """Map every file under the real data/system/ to its content hash."""
    state: dict[str, str] = {}
    if not REAL_SYSTEM_DIR.exists():
        return state
    for path in sorted(REAL_SYSTEM_DIR.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(REAL_SYSTEM_DIR))
            state[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


@pytest.fixture(scope="session", autouse=True)
def production_artifacts_untouched():
    """Guard (QA-003): the suite must not create, delete, or modify anything
    under the real data/system/ directory — git status stays clean."""
    before = _system_dir_state()
    yield
    after = _system_dir_state()
    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    created = sorted(after.keys() - before.keys())
    deleted = sorted(before.keys() - after.keys())
    assert not (changed or created or deleted), (
        "Test suite mutated production artifacts under data/system/ — "
        f"changed={changed} created={created} deleted={deleted}"
    )


@pytest.fixture(autouse=True)
def artifact_sandbox(tmp_path, monkeypatch):
    """Redirect every production artifact write to pytest's tmp_path.

    Production code resolves its output paths (and the inside-project write
    guard root) from module attributes at call time, so patching them here
    sends all writes — including the default-path writes inside
    ``run_regime_cycle`` — into a per-test temporary directory.
    """
    sandbox_root = tmp_path / "MarketRegimeBot"
    system_dir = sandbox_root / "data" / "system"
    system_dir.mkdir(parents=True)
    monkeypatch.setattr(regime_cycle, "PROJECT_ROOT", sandbox_root)
    monkeypatch.setattr(
        regime_cycle, "RESULT_SNAPSHOT_PATH", system_dir / "result_snapshot.json"
    )
    monkeypatch.setattr(regime_export_writer, "PROJECT_ROOT", sandbox_root)
    monkeypatch.setattr(
        regime_export_writer, "REGIME_EXPORT_PATH", system_dir / "regime_export.json"
    )
    return sandbox_root
