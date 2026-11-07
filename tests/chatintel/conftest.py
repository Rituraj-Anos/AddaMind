import pytest


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    """Every test gets its own data folder and never calls an embedding, media or chat model."""
    monkeypatch.setenv("ADDAMIND_DATA", str(tmp_path))
    monkeypatch.delenv("ADDAMIND_PUBLIC", raising=False)  # public mode is opt-in per test
    monkeypatch.setenv("ADDAMIND_EMBEDDINGS", "off")
    monkeypatch.setenv("ADDAMIND_MEDIA", "off")
    monkeypatch.setenv("ADDAMIND_MEMORY", "off")
