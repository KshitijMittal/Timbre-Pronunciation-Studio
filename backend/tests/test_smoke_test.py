"""The smoke test is a money path: it must ask before its first paid call.

It is loaded by path because it is a script, not a package module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "smoke_test.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke_test"] = module
    spec.loader.exec_module(module)
    return module


script = load_script()


def test_no_paid_call_happens_before_confirmation(monkeypatch):
    def must_not_call(**_kwargs):
        raise AssertionError("a paid call ran before the credit guard")

    def no_stdin(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr(script, "call", must_not_call)
    monkeypatch.setattr("builtins.input", no_stdin)
    monkeypatch.setattr(sys, "argv", ["smoke_test.py"])

    with pytest.raises(SystemExit) as excinfo:
        script.main()

    assert "No credits were spent" in str(excinfo.value)
