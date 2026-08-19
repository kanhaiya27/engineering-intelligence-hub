"""
Shared pytest fixtures and configuration for Engineering Intelligence Hub tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.api.main import app


@pytest.fixture(scope="session")
def sample_task_id() -> str:
    return "test-task-001"


@pytest.fixture(scope="session")
def sample_repository() -> str:
    return "test-org/test-repo"


@pytest.fixture
async def api_client():
    """Async HTTP client for FastAPI integration tests."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
