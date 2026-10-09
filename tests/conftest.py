import pytest
import httpx
import os


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (end-to-end LLM calls — run with -m slow or omit to include all)",
    )


@pytest.fixture(scope="session", autouse=True)
def check_fastapi_service():
    """
    Verify that the FastAPI service is reachable before running tests.
    This fixture runs automatically for all test sessions.
    """
    base_url = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{base_url}/health")
            response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        pytest.fail(
            f"FastAPI service is not reachable at {base_url}: {exc}\n"
            f"Please start the service with:\n"
            f"  docker compose up\n"
            f"  -- or --\n"
            f"  uvicorn generating.app:app --port 8000\n\n"
            f"You can also set FASTAPI_BASE_URL environment variable "
            f"if running on a different host/port."
        )
