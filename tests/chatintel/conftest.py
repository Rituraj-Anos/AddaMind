import pytest


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    """Every test gets its own data folder and never calls an embedding or media API."""
    monkeypatch.setenv("ADDAMIND_DATA", str(tmp_path))
    monkeypatch.setenv("ADDAMIND_EMBEDDINGS", "off")
    monkeypatch.setenv("ADDAMIND_MEDIA", "off")
