"""Tests for configuration loading."""

from dynatrust_rag.config import get_config, DynaTrustConfig


def test_config_loads():
    config = get_config()
    assert isinstance(config, DynaTrustConfig)


def test_config_database_defaults():
    config = get_config()
    assert config.database.port == 5432
    assert config.database.database == "atlas4d"


def test_config_vector_defaults():
    config = get_config()
    assert config.vector.embedding_dim == 768
    assert 0 < config.vector.similarity_threshold <= 1.0


def test_config_dsn_format():
    config = get_config()
    dsn = config.database.dsn
    assert dsn.startswith("postgresql://")
    assert str(config.database.port) in dsn
