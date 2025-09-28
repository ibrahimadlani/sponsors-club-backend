"""Unit tests ensuring the Django management entry point behaves as expected."""

from __future__ import annotations

import os
import runpy
import sys

import pytest

import manage


@pytest.fixture(autouse=True)
def restore_settings(monkeypatch):
    """Clear the Django settings override before each test."""

    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)


def test_main_sets_default_settings_module(monkeypatch):
    """Running ``main`` configures Django and delegates to the command runner."""

    captured = {}

    def fake_execute(argv):
        captured["argv"] = list(argv)

    monkeypatch.setattr(manage, "execute_from_command_line", fake_execute)
    monkeypatch.setattr(manage.sys, "argv", ["manage.py", "check"])

    manage.main()

    assert os.environ["DJANGO_SETTINGS_MODULE"] == "core.settings"
    assert captured["argv"] == ["manage.py", "check"]


def test_entrypoint_executes_main_when_run_as_script(monkeypatch):
    """Executing the module as ``__main__`` still delegates through ``main``."""

    called = {}

    def fake_execute(argv):
        called["argv"] = list(argv)

    from django.core import management as django_management

    monkeypatch.setattr(django_management, "execute_from_command_line", fake_execute)
    monkeypatch.setattr(sys, "argv", ["manage.py", "showmigrations"])

    runpy.run_path("manage.py", run_name="__main__")

    assert os.environ["DJANGO_SETTINGS_MODULE"] == "core.settings"
    assert called["argv"] == ["manage.py", "showmigrations"]
