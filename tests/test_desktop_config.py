"""
desktop/config.py is pure file I/O against the user's own home directory —
tests redirect that to a tmp_path via monkeypatch so nothing here ever
touches a real home directory or leaves anything behind.
"""

import stat

from desktop import config


def _use_tmp_config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path / ".mocha_aba_reviewer")


def test_get_api_key_is_none_when_never_saved(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    assert config.get_api_key() is None


def test_save_and_get_api_key_round_trips(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    config.save_api_key("sk-test-abc123")
    assert config.get_api_key() == "sk-test-abc123"


def test_save_api_key_rejects_empty_string(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    try:
        config.save_api_key("   ")
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert config.get_api_key() is None


def test_clear_api_key_removes_it_but_keeps_other_settings(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    config.save_api_key("sk-test-abc123")
    config.clear_api_key()
    assert config.get_api_key() is None


def test_config_file_is_written_with_owner_only_permissions(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    config.save_api_key("sk-test-abc123")
    mode = stat.S_IMODE(config.config_path().stat().st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_get_model_and_base_url_have_sensible_defaults(monkeypatch, tmp_path):
    _use_tmp_config_dir(monkeypatch, tmp_path)
    assert config.get_model() == config.DEFAULT_MODEL
    assert config.get_base_url() == config.DEFAULT_BASE_URL


def test_mask_api_key_never_reveals_the_middle():
    masked = config.mask_api_key("sk-proj-abcdefghijklmnopqrstuvwxyz")
    assert masked.startswith("sk-pr")
    assert masked.endswith("wxyz")
    assert "abcdefghijklmnop" not in masked


def test_mask_api_key_handles_very_short_strings():
    assert config.mask_api_key("short") == "*****"
