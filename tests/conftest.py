import pytest


@pytest.fixture(autouse=True)
def prevent_real_gemini_calls(monkeypatch):
    # Never use the user's credentials in the automated suite.
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
