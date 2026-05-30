import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

# B3에서 Pydantic Settings로 이동 예정
DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
