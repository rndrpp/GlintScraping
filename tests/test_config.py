"""Tests for scrape_glints.resolve_config precedence rules (browser-free).

These tests exercise the CLI -> env -> prompt resolution logic without launching
a browser or prompting interactively. Env vars are set/cleared with monkeypatch
and sys.stdin.isatty is patched so no prompt is ever reached.
"""

import pytest

import scrape_glints


# Env vars read by resolve_config; cleared before each test for isolation.
_ENV_VARS = (
    'GLINTS_KEYWORD',
    'GLINTS_SENDER_EMAIL',
    'GLINTS_RECEIVER_EMAIL',
    'GLINTS_APP_PASSWORD',
    'GLINTS_SLEEP',
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure a clean environment so ambient vars never leak into a test."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_cli_keyword_beats_env(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    monkeypatch.setenv('GLINTS_KEYWORD', 'from-env')

    args = scrape_glints.parse_args(['--keyword', 'from-cli', '--no-email'])
    cfg = scrape_glints.resolve_config(args)

    assert cfg.keyword == 'from-cli'


def test_env_keyword_used_when_no_flag(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    monkeypatch.setenv('GLINTS_KEYWORD', 'from-env')

    args = scrape_glints.parse_args(['--no-email'])
    cfg = scrape_glints.resolve_config(args)

    assert cfg.keyword == 'from-env'


def test_missing_keyword_on_non_tty_raises(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)

    args = scrape_glints.parse_args(['--no-email'])
    with pytest.raises(SystemExit):
        scrape_glints.resolve_config(args)


def test_no_email_flag_disables_email_even_with_sender_env(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    monkeypatch.setenv('GLINTS_SENDER_EMAIL', 'sender@example.com')

    args = scrape_glints.parse_args(['--keyword', 'python', '--no-email'])
    cfg = scrape_glints.resolve_config(args)

    assert cfg.email_enabled is False
    assert cfg.sender_gmail is None
    assert cfg.sender_apppass is None


def test_email_enabled_resolves_all_values_from_env(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    monkeypatch.setenv('GLINTS_KEYWORD', 'python')
    monkeypatch.setenv('GLINTS_SENDER_EMAIL', 'sender@example.com')
    monkeypatch.setenv('GLINTS_APP_PASSWORD', 'app-secret')
    monkeypatch.setenv('GLINTS_RECEIVER_EMAIL', 'receiver@example.com')

    args = scrape_glints.parse_args([])
    cfg = scrape_glints.resolve_config(args)

    assert cfg.email_enabled is True
    assert cfg.sender_gmail == 'sender@example.com'
    assert cfg.sender_apppass == 'app-secret'
    assert cfg.receiver == 'receiver@example.com'
