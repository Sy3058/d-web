from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.db import get_session
from src.main import app


@pytest.fixture(autouse=True, scope="session")
def _disable_sentry():
    # 테스트에서 Sentry 초기화를 막아 teardown 시 I/O 에러 방지
    with patch("sentry_sdk.init"):
        yield


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
    # 서비스가 session.commit()을 직접 호출하므로 롤백 격리 대신
    # 실제 커밋 후 테이블 전체 DELETE로 격리한다.
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with test_engine.connect() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.commit()


@pytest.fixture
def client(db_session: AsyncSession):
    from fastapi.testclient import TestClient

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
