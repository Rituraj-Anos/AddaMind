import pytest


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    """Every test gets its own data folder and never calls an embedding API."""
    monkeypatch.setenv("ADDAMIND_DATA", str(tmp_path))
    monkeypatch.setenv("ADDAMIND_EMBEDDINGS", "off")
