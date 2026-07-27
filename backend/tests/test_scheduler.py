"""스케줄러 잡 테스트 (M1.5 E1, ADM-04 + #57).

잡 본체(session 주입 순수 함수)에 conftest test_engine 세션을 직접 주입해
검증한다 - APScheduler 기동 없이 잡 로직만(트리거·리스너는 라이브러리 영역).
published_at/expires_at은 timestamptz라 픽스처 시각은 전부 tz-aware(UTC)로
구성한다(naive는 asyncpg에서 어긋남 - MISTAKES).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.scheduler import cleanup_expired_tokens, publish_due_episodes
from src.models.user import EmailVerification, RefreshToken, TrustedDevice, User
from src.models.work import Episode, Work


def _past(minutes: int = 5) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def _future(days: int = 1) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


@pytest_asyncio.fixture
async def work(db_session: AsyncSession, user: User) -> Work:
    w = Work(title="스케줄러 작품", author_id=user.id)
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _make_episode(
    session: AsyncSession,
    work: Work,
    no: int,
    *,
    published_at: datetime | None,
    is_published: bool = False,
    pages: int = 1,
) -> Episode:
    # F3 재설계: 공개 가드의 기준은 content 문서(pages=0 = EMPTY_DOC = 빈 본문).
    keys = [f"works/{work.id}/episodes/{no}/{i}.webp" for i in range(pages)]
    ep = Episode(
        work_id=work.id,
        episode_no=no,
        title=f"{no}화",
        image_keys=keys,
        content={
            "type": "doc",
            "content": [{"type": "image", "attrs": {"key": k}} for k in keys],
        },
        is_published=is_published,
        published_at=published_at,
    )
    session.add(ep)
    await session.commit()
    await session.refresh(ep)
    return ep


# ---------------------------------------------------------------------------
# 공개 전환 잡
# ---------------------------------------------------------------------------


async def test_publish_due_past_episode(db_session: AsyncSession, work: Work):
    # DoD: 과거 시각 예약도 다음 틱에 공개된다
    ep = await _make_episode(db_session, work, 1, published_at=_past())
    assert await publish_due_episodes(db_session) == 1
    await db_session.refresh(ep)
    assert ep.is_published is True
    assert ep.published_at is not None  # 공개 시각 데이터로 보존(NULL 리셋 안 함)


async def test_future_reservation_stays_draft(db_session: AsyncSession, work: Work):
    ep = await _make_episode(db_session, work, 1, published_at=_future())
    assert await publish_due_episodes(db_session) == 0
    await db_session.refresh(ep)
    assert ep.is_published is False


async def test_empty_draft_reservation_not_published(db_session: AsyncSession, work: Work):
    # D3 인계 + F3: 빈 본문(EMPTY_DOC) draft는 예약 시각이 지나도 공개하지 않는다
    ep = await _make_episode(db_session, work, 1, published_at=_past(), pages=0)
    assert await publish_due_episodes(db_session) == 0
    await db_session.refresh(ep)
    assert ep.is_published is False


async def test_plain_draft_untouched(db_session: AsyncSession, work: Work):
    # published_at NULL(예약 없음) draft는 폴링 대상이 아니다
    ep = await _make_episode(db_session, work, 1, published_at=None)
    assert await publish_due_episodes(db_session) == 0
    await db_session.refresh(ep)
    assert ep.is_published is False


async def test_second_run_idempotent(db_session: AsyncSession, work: Work):
    # 멱등: 한 번 공개된 행은 폴링 대상에서 영구히 빠진다(중복 발화 무해)
    await _make_episode(db_session, work, 1, published_at=_past())
    assert await publish_due_episodes(db_session) == 1
    assert await publish_due_episodes(db_session) == 0


async def test_deleted_episode_not_republished(db_session: AsyncSession, work: Work):
    # #85 가드. soft delete는 published_at도 NULL로 밀어서 정상 경로로는 "삭제됐는데
    # 예약이 남은" 이 상태가 안 만들어진다 - 그래서 행을 직접 만들어 deleted_at 조건
    # 자체를 검증한다. 이 잡은 비공개→공개를 자동으로 뒤집는 유일한 경로고 그 전환은
    # 되돌릴 수 없으니, 삭제 정책이 바뀌어도 가드가 살아 있는지 여기서 잡아야 한다.
    ep = await _make_episode(db_session, work, 1, published_at=_past())
    ep.deleted_at = datetime.now(UTC)
    db_session.add(ep)
    await db_session.commit()

    assert await publish_due_episodes(db_session) == 0
    await db_session.refresh(ep)
    assert ep.is_published is False


# ---------------------------------------------------------------------------
# 만료 토큰 cleanup 잡 (#57)
# ---------------------------------------------------------------------------


def _refresh(user: User, *, expires_at: datetime, revoked_at: datetime | None = None):
    return RefreshToken(
        user_id=user.id,
        token_hash=f"hash-{uuid.uuid4().hex}",  # UNIQUE 인덱스 - 행마다 고유값
        expires_at=expires_at,
        original_issued_at=_past(minutes=60),
        revoked_at=revoked_at,
    )


async def test_cleanup_deletes_expired_keeps_valid_and_revoked(
    db_session: AsyncSession, user: User
):
    expired = _refresh(user, expires_at=_past())
    valid = _refresh(user, expires_at=_future())
    # revoked라도 미만료면 보존 - 회전 재사용 탐지(M1 C4)의 근거 데이터
    revoked_unexpired = _refresh(user, expires_at=_future(), revoked_at=_past())
    db_session.add_all([expired, valid, revoked_unexpired])
    await db_session.commit()

    deleted = await cleanup_expired_tokens(db_session)

    assert deleted["refresh_tokens"] == 1
    remaining = {t.token_hash for t in (await db_session.exec(select(RefreshToken))).all()}
    assert remaining == {valid.token_hash, revoked_unexpired.token_hash}


async def test_cleanup_covers_trusted_devices_and_email_verifications(
    db_session: AsyncSession, user: User
):
    db_session.add_all(
        [
            TrustedDevice(user_id=user.id, token_hash=f"td-{uuid.uuid4().hex}", expires_at=_past()),
            TrustedDevice(
                user_id=user.id, token_hash=f"td-{uuid.uuid4().hex}", expires_at=_future()
            ),
            EmailVerification(user_id=user.id, token=f"ev-{uuid.uuid4().hex}", expires_at=_past()),
            EmailVerification(
                user_id=user.id, token=f"ev-{uuid.uuid4().hex}", expires_at=_future()
            ),
        ]
    )
    await db_session.commit()

    deleted = await cleanup_expired_tokens(db_session)

    assert deleted["trusted_devices"] == 1
    assert deleted["email_verifications"] == 1
