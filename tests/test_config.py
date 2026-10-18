import importlib
import os

import pytest

from backend import constants

CONFIG_VARS = (
    "DATA_DIR", "DB_PATH", "TOKEN_PATH", "CREDENTIALS_PATH", "PORT", "TRUST_PROXY",
    "ADMIN_USERNAME", "ADMIN_PASSWORD",
)


@pytest.fixture
def cfg(monkeypatch):
    """Reload backend.constants under a clean env; restore env and constants afterwards."""
    saved = dict(os.environ)  # load_dotenv writes os.environ directly, bypassing monkeypatch
    for var in CONFIG_VARS:
        monkeypatch.delenv(var, raising=False)

    def load():
        return importlib.reload(constants)

    yield load, monkeypatch
    os.environ.clear()
    os.environ.update(saved)
    importlib.reload(constants)


def test_without_data_dir_paths_keep_legacy_defaults(cfg):
    load, _ = cfg
    c = load()
    assert c.DATA_DIR is None
    assert c.DB_PATH.endswith(os.path.join("backend", "db", "finance_tracker.db"))
    assert c.TOKEN_FILE.endswith("token.json")
    assert c.CREDENTIALS_FILE.endswith("credentials.json")
    root = os.path.dirname(os.path.dirname(os.path.abspath(c.__file__)))
    assert os.path.dirname(c.TOKEN_FILE) == root
    assert os.path.dirname(c.CREDENTIALS_FILE) == root


def test_data_dir_relocates_db_token_and_credentials(cfg, tmp_path):
    load, mp = cfg
    mp.setenv("DATA_DIR", str(tmp_path))
    c = load()
    assert c.DB_PATH == os.path.join(str(tmp_path), "finance_tracker.db")
    assert c.TOKEN_FILE == os.path.join(str(tmp_path), "token.json")
    assert c.CREDENTIALS_FILE == os.path.join(str(tmp_path), "credentials.json")


def test_explicit_paths_beat_data_dir(cfg, tmp_path):
    load, mp = cfg
    mp.setenv("DATA_DIR", str(tmp_path))
    mp.setenv("DB_PATH", "/x/db.sqlite")
    mp.setenv("TOKEN_PATH", "/x/tok.json")
    mp.setenv("CREDENTIALS_PATH", "/x/cred.json")
    c = load()
    assert c.DB_PATH == "/x/db.sqlite"
    assert c.TOKEN_FILE == "/x/tok.json"
    assert c.CREDENTIALS_FILE == "/x/cred.json"


def test_port_defaults_to_5000_and_reads_port_env(cfg):
    load, mp = cfg
    assert load().SERVER_PORT == 5000
    mp.setenv("PORT", "8080")
    assert load().SERVER_PORT == 8080


def test_trust_proxy_defaults_off_and_parses_true(cfg):
    load, mp = cfg
    assert load().TRUST_PROXY is False
    mp.setenv("TRUST_PROXY", "true")
    assert load().TRUST_PROXY is True


def test_env_file_values_are_loaded(cfg, tmp_path):
    load, mp = cfg
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_USERNAME=fromfile\n")
    mp.setenv("ENV_FILE", str(env_file))
    assert load().ADMIN_USERNAME == "fromfile"


def test_real_env_beats_env_file(cfg, tmp_path):
    load, mp = cfg
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_USERNAME=fromfile\n")
    mp.setenv("ENV_FILE", str(env_file))
    mp.setenv("ADMIN_USERNAME", "fromenv")
    assert load().ADMIN_USERNAME == "fromenv"


def test_empty_db_path_falls_back_to_default(cfg):
    load, mp = cfg
    mp.setenv("DB_PATH", "")
    assert load().DB_PATH.endswith(os.path.join("backend", "db", "finance_tracker.db"))


def test_empty_db_path_falls_back_to_data_dir(cfg, tmp_path):
    load, mp = cfg
    mp.setenv("DATA_DIR", str(tmp_path))
    mp.setenv("DB_PATH", "")
    assert load().DB_PATH == os.path.join(str(tmp_path), "finance_tracker.db")


def test_empty_token_and_credentials_paths_fall_back(cfg):
    load, mp = cfg
    mp.setenv("TOKEN_PATH", "")
    mp.setenv("CREDENTIALS_PATH", "")
    c = load()
    assert c.TOKEN_FILE.endswith("token.json") and os.path.basename(c.TOKEN_FILE)
    assert c.CREDENTIALS_FILE.endswith("credentials.json") and os.path.basename(c.CREDENTIALS_FILE)


def test_empty_port_defaults_to_5000(cfg):
    load, mp = cfg
    mp.setenv("PORT", "")
    assert load().SERVER_PORT == 5000


def test_relative_data_dir_resolves_against_project_root(cfg):
    load, mp = cfg
    mp.setenv("DATA_DIR", "data")
    c = load()
    root = os.path.dirname(os.path.dirname(os.path.abspath(c.__file__)))
    assert c.DB_PATH == os.path.join(root, "data", "finance_tracker.db")
    assert c.TOKEN_FILE == os.path.join(root, "data", "token.json")


def test_data_dir_expands_user_home(cfg):
    load, mp = cfg
    mp.setenv("DATA_DIR", "~/x")
    c = load()
    assert c.DATA_DIR == os.path.join(os.path.expanduser("~"), "x")
    assert c.DB_PATH == os.path.join(os.path.expanduser("~"), "x", "finance_tracker.db")
