import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.config import get_settings
from app.db.session import get_db
from app.db.models import Base

# Tells pytest-asyncio to handle asynchronous plugins cleanly
pytest_plugins = ('anyio',)


@pytest.fixture(scope="session")
def mock_boto3():
    """Globally intercepts boto3 calls to isolate tests from AWS S3."""
    with patch("app.services.s3.boto3.client") as mock_client:
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3
        yield mock_s3


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """
    Creates a function-scoped async engine bound strictly to the active 
    test function's event loop, preventing asyncpg connection bleed.
    """
    settings = get_settings()
    TEST_DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    # Engine is initialized inside the running test's active loop
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Build clean database tables fresh for this isolated test context
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    
    # Tear down tables and completely dissolve connection threads on teardown
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provides a transaction-isolated session instance per test execution."""
    TestingSessionLocal = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Overrides the live app dependency injection mapping with the test session context."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def registered_user(client: AsyncClient) -> dict:
    """Registers a baseline user configuration and exposes profile credentials."""
    payload = {
        "email": "fixture_user@example.com",
        "username": "fixture_user",
        "password": "securepassword123"
    }
    response = await client.post("/api/auth/register", json=payload)
    data = response.json()
    return {
        "email": payload["email"],
        "password": payload["password"],
        "username": payload["username"],
        "access_token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"}
    }