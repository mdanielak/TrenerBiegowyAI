import os

from trainer.env_file import load_env_file


def test_load_env_file_parses_supported_syntax(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("\ufeff# komentarz\nexport ONE='a=b'\nTWO=value # opis\nBAD-KEY=no\n", encoding="utf-8")
    monkeypatch.delenv("ONE", raising=False)
    monkeypatch.delenv("TWO", raising=False)
    assert load_env_file(path) == {"ONE": "a=b", "TWO": "value"}
    assert os.environ["ONE"] == "a=b"


def test_existing_environment_wins_unless_overridden(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("VALUE=file\n", encoding="utf-8")
    monkeypatch.setenv("VALUE", "system")
    assert load_env_file(path) == {}
    assert load_env_file(path, override=True) == {"VALUE": "file"}


def test_missing_file_is_silent(tmp_path):
    assert load_env_file(tmp_path / "missing") == {}
