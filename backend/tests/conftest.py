from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.db import get_session
from src.lib.rate_limit import reset_rate_limits
from src.main import app
from src.models.user import User
from src.services import auth_service

# 표준 테스트 계정 - existing_user 픽스처와 로그인 테스트(_LOGIN)가 공유하는 단일 출처.
# test 파일이 같은 리터럴을 또 박아 불일치 버그가 나지 않도록 여기서만 정의한다.
EXISTING_USER_EMAIL = "user@example.com"
EXISTING_USER_PASSWORD = "Passw0rd!"
EXISTING_USER_NICKNAME = "tester"


@pytest.fixture(autouse=True, scope="session")
def _disable_sentry():
    # 테스트에서 Sentry 초기화를 막아 teardown 시 I/O 에러 방지
    with patch("sentry_sdk.init"):
        yield


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # 모듈 전역 rate limiter는 프로세스 내내 공유되므로, 각 테스트의 누적 hit이
    # 다른 테스트를 429로 깨뜨리지 않도록 매 테스트 전에 비운다(동기 - 동기 테스트 호환).
    reset_rate_limits()
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


@pytest.fixture
def session_factory(test_engine):
    """test_engine에서 독립 AsyncSession을 찍어내는 팩토리.

    커넥션이 분리된 세션 2개 이상을 asyncio.gather로 동시에 돌려야 하는
    동시성 테스트(I4 회전 race·M3 결제 멱등)에서 쓴다. db_session도 이걸로 만든다.
    """
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(test_engine, session_factory) -> AsyncGenerator[AsyncSession, None]:
    # 서비스가 session.commit()을 직접 호출하므로 롤백 격리 대신
    # 실제 커밋 후 테이블 전체 DELETE로 격리한다.
    async with session_factory() as session:
        yield session
    async with test_engine.connect() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.commit()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """앱을 같은 이벤트 루프에서 ASGITransport로 띄운 httpx 클라이언트.

    TestClient(동기·자체 루프)는 session-scope async db_session(asyncpg)과 루프가
    어긋난다(MISTAKES "different loop"). 엔드포인트+DB 통합 테스트 공용.
    """

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test.example") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    """FK 부모용 가벼운 유저(비밀번호 없음).

    refresh 토큰·회전 등 FK만 필요한 테스트용 - bcrypt(cost=12)를 안 거쳐 빠르다.
    로그인·비밀번호 검증이 필요한 테스트는 existing_user를 쓴다.
    """
    u = User(email="plain@example.com", nickname="plain")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def existing_user(db_session: AsyncSession) -> User:
    """이미 가입된(이메일+비밀번호) 유저. 로그인·재발송 등 인증 플로우 테스트용."""
    user = await auth_service.create_user(
        EXISTING_USER_EMAIL, EXISTING_USER_PASSWORD, EXISTING_USER_NICKNAME, db_session
    )
    await db_session.commit()
    return user
