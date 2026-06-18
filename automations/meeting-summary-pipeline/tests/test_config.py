import os

from meeting_summary_pipeline.config import _int_env


def test_int_env_uses_default_for_missing_or_empty(monkeypatch):
    monkeypatch.delenv("EXAMPLE_INT", raising=False)
    assert _int_env("EXAMPLE_INT", 2) == 2

    monkeypatch.setenv("EXAMPLE_INT", "")
    assert _int_env("EXAMPLE_INT", 2) == 2

    monkeypatch.setenv("EXAMPLE_INT", "  ")
    assert _int_env("EXAMPLE_INT", 2) == 2


def test_int_env_parses_value(monkeypatch):
    monkeypatch.setenv("EXAMPLE_INT", "7")
    assert _int_env("EXAMPLE_INT", 2) == 7
