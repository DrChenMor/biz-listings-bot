import json
import os
from types import SimpleNamespace

from bizbot import __main__ as cli
from bizbot import config

SHEET = "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd/edit#gid=0"


def test_env_file_fills_in_settings_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nSHEET_ID="abc"\nGOOGLE_SERVICE_ACCOUNT_FILE=C:\\Users\\Sam\\bot\\key.json\n\nBROKEN LINE\n', encoding="utf-8")
    monkeypatch.delenv("SHEET_ID", raising=False)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "already-set.json")
    cli.load_env_file(env)
    assert os.environ["SHEET_ID"] == "abc"
    assert os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] == "already-set.json"


def test_dragged_in_paths():
    assert cli.clean_dropped_path('"C:\\Users\\Sam\\Downloads\\listings-bot-123.json" ') == "C:\\Users\\Sam\\Downloads\\listings-bot-123.json"
    if os.sep == "/":
        assert cli.clean_dropped_path("/Users/sam/My\\ Downloads/key.json") == "/Users/sam/My Downloads/key.json"


def test_setup_copies_the_key_saves_settings_and_tests_the_sheet(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    key = downloads / "listings-bot-123.json"
    key.write_text(json.dumps({"client_email": "bot@x.iam.gserviceaccount.com", "private_key": "-----KEY-----"}), encoding="utf-8")
    project = tmp_path / "biz-listings-bot"
    project.mkdir()
    monkeypatch.setattr(config, "ROOT", project)
    answers = iter([f'"{key}"', SHEET])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    opened = {}

    def fake_store(sheet_id, credentials):
        opened["id"], opened["email"] = sheet_id, credentials["client_email"]
        return SimpleNamespace(book=SimpleNamespace(title="WA businesses for sale"))

    monkeypatch.setattr(cli, "SheetStore", fake_store)
    assert cli.setup() == 0
    assert opened == {"id": "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd", "email": "bot@x.iam.gserviceaccount.com"}
    assert json.loads((project / cli.KEY_FILE).read_text(encoding="utf-8"))["private_key"] == "-----KEY-----"
    env = (project / ".env").read_text(encoding="utf-8")
    assert "SHEET_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd" in env
    assert f"GOOGLE_SERVICE_ACCOUNT_FILE={project / cli.KEY_FILE}" in env


def test_setup_refuses_a_file_that_is_not_a_key(tmp_path, monkeypatch):
    other = tmp_path / "notes.json"
    other.write_text('{"hello": 1}', encoding="utf-8")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": str(other))
    assert cli.setup() == 1
    assert not (tmp_path / ".env").exists()
