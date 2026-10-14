import pytest
import requests

import rag


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: end-to-end LLM calls (run with -m slow, or include all)",
    )


@pytest.fixture(scope="session", autouse=True)
def check_services():
    """Fail early when shelly-chat or Ollama can not be reached."""
    for name, url in [
        ("shelly-chat", f"{rag.SHELLY_CHAT_URL}/api/health"),
        ("Ollama", f"{rag.OLLAMA_BASE_URL}/api/version"),
    ]:
        try:
            requests.get(url, timeout=5).raise_for_status()
        except requests.RequestException as exc:
            pytest.fail(f"{name} is niet bereikbaar op {url}: {exc}")
