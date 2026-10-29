"""Config defaults and mapping errors."""

import pytest

from usage_audit.config import default_config, load_config
from usage_audit.errors import ConfigError

from conftest import EXAMPLE_CONFIG


def test_example_file_matches_defaults():
    assert load_config(EXAMPLE_CONFIG) == default_config()


def test_partial_mapping_keeps_other_defaults(tmp_path):
    path = tmp_path / "usage-audit.yaml"
    path.write_text("mapping:\n  units: tokens\n", encoding="utf-8")
    loaded = load_config(path)
    assert loaded.mapping["units"] == "tokens"
    assert loaded.mapping["timestamp"] == "timestamp"
    assert loaded.top == 10


def test_unknown_key_and_overlap(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("extra: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown config key"):
        load_config(path)

    path.write_text(
        """
outcomes:
  noop: ["changed"]
  changed: ["changed"]
  error: ["error"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="outcome label"):
        load_config(path)


def test_retry_min_and_top_and_column_type(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("retry_min: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="retry_min"):
        load_config(path)

    path.write_text("top: 0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="top"):
        load_config(path)

    path.write_text("mapping:\n  timestamp: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="column name"):
        load_config(path)


def test_missing_config(tmp_path):
    with pytest.raises(ConfigError, match="could not read config"):
        load_config(tmp_path / "missing.yaml")
