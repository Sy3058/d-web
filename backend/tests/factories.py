"""테스트용 도메인 객체 팩토리.

test_catalog.py(공개 카탈로그)와 test_progress.py(진행도)가 같은 Work/Episode 생성
로직을 쓴다. 원래 두 파일에 복붙돼 있었으나, 모델에 nullable=False 컬럼이 하나 추가되면
두 곳을 모두 고쳐야 하고 한쪽을 빠뜨리면 다른 테스트 파일이 IntegrityError로 깨지므로
여기로 모았다.

admin API를 거치지 않고 ORM으로 직접 생성한다 - 공개 read 경로 자체가 검증 대상이라
생성 경로와 원인을 분리한다.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.user import User
from src.models.work import Episode, Work


async def make_work(db_session: AsyncSession, author: User, **overrides) -> Work:
    work = Work(
        author_id=author.id,
        title=overrides.pop("title", "테스트작"),
        is_published=overrides.pop("is_published", True),
        **overrides,
    )
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    return work


async def make_episode(db_session: AsyncSession, work: Work, **overrides) -> Episode:
    ep = Episode(
        work_id=work.id,
        episode_no=overrides.pop("episode_no", 1),
        title=overrides.pop("title", "1화"),
        is_published=overrides.pop("is_published", True),
        **overrides,
    )
    db_session.add(ep)
    await db_session.commit()
    await db_session.refresh(ep)
    return ep
