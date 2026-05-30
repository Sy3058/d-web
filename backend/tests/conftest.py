from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings


@pytest.fixture(autouse=True, scope="session")
def _disable_sentry():
    # 테스트에서 Sentry 초기화를 막아 teardown 시 I/O 에러 방지
    with patch("sentry_sdk.init"):
        yield
from src.lib.db import get_session
from src.main import app


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    url = settings.test_database_url or settings.database_url
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    # 각 테스트마다 트랜잭션을 시작하고 끝에 롤백 - DB 상태 격리
    conn: AsyncConnection
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await conn.rollback()


@pytest.fixture
def client(db_session: AsyncSession):
    from fastapi.testclient import TestClient

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
