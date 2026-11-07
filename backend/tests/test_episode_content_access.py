"""콘텐츠 권한 경계와 전문 발급/환불 CAS의 통합 테스트."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.dml import Update
from sqlmodel import select

from src.config import settings
from src.lib import auth
from src.lib.exceptions import EpisodeAccessConflictError
from src.models.payment import Purchase, PurchaseStatus
from src.models.work import Episode
from src.services import episode_access_service, episode_read_service, r2_service
from tests.factories import PAYWALL, doc, img, make_episode, make_purchase, make_work, para

pytestmark = pytest.mark.asyncio
FREE_KEY = "works/w/episodes/e/free.webp"
PAID_KEY = "works/w/episodes/e/paid.webp"


@pytest.fixture
def presign_spy(monkeypatch):
    spy = AsyncMock(side_effect=lambda keys: [f"https://signed.example/{key}" for key in keys])
    monkeypatch.setattr(r2_service, "presign_get_urls", spy)
    return spy


async def paid_episode(session, user, **overrides):
    work = await make_work(session, user)
    return await make_episode(
        session,
        work,
        content=doc(para("무료"), img(FREE_KEY), PAYWALL, para("유료"), img(PAID_KEY)),
        image_keys=[FREE_KEY, PAID_KEY],
        **overrides,
    )


def login(client, user):
    client.cookies.set(
        auth.access_cookie_name(), auth.create_access_token(str(user.id)), domain="test.example"
    )


def content_url(episode):
    return f"/episodes/{episode.id}/content"


async def purchase_state(session, purchase_id):
    return (
        await session.exec(
            select(Purchase.status, Purchase.first_viewed_at).where(Purchase.id == purchase_id)
        )
    ).one()


@pytest.mark.parametrize("credential", ["absent", "forged", "expired", "deleted", "missing_user"])
async def test_unusable_auth_is_preview_without_cookie_mutation(
    async_client, db_session, user, presign_spy, credential
):
    episode = await paid_episode(db_session, user)
    purchase, _ = await make_purchase(db_session, user, episode)
    if credential == "deleted":
        user.deleted_at = datetime.now(UTC)
        await db_session.commit()
    if credential != "absent":
        if credential == "expired":
            token = jwt.encode(
                {
                    "sub": str(user.id),
                    "typ": "access",
                    "exp": datetime.now(UTC) - timedelta(hours=1),
                },
                settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
            )
        elif credential == "forged":
            token = jwt.encode(
                {"sub": str(user.id), "typ": "access"},
                "wrong-secret-0123456789abcdef0123456789abcdef",
                algorithm=settings.jwt_algorithm,
            )
        else:
            token = auth.create_access_token(
                str(uuid.uuid4() if credential == "missing_user" else user.id)
            )
        async_client.cookies.set(auth.access_cookie_name(), token, domain="test.example")

    response = await async_client.get(content_url(episode))

    assert response.status_code == 200
    assert response.json()["access_scope"] == "preview"
    assert response.json()["has_paid_part"] is True
    assert "유료" not in response.text
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    presign_spy.assert_awaited_once_with([FREE_KEY])
    assert (await purchase_state(db_session, purchase.id)).first_viewed_at is None


@pytest.mark.parametrize(
    "failure", [HTTPException(503, "unavailable"), SQLAlchemyError("db failure")]
)
async def test_optional_auth_propagates_non_auth_failures(monkeypatch, failure):
    monkeypatch.setattr(auth, "get_current_user", AsyncMock(side_effect=failure))
    with pytest.raises(type(failure)) as exc:
        await auth.get_optional_user(None, None)
    assert exc.value is failure


@pytest.mark.parametrize("published", [True, False])
async def test_active_purchase_gets_full_and_records_only_first_issue(
    async_client, db_session, user, presign_spy, published
):
    episode = await paid_episode(db_session, user, is_published=published)
    purchase, _ = await make_purchase(db_session, user, episode)
    login(async_client, user)

    first = await async_client.get(content_url(episode))

    assert first.status_code == 200
    body = first.json()
    assert body["access_scope"] == "full"
    assert body["has_paid_part"] is False
    assert "유료" in first.text
    assert "paywall" not in first.text
    assert all("key" not in node.get("attrs", {}) for node in body["content"]["content"])
    presign_spy.assert_awaited_once_with([FREE_KEY, PAID_KEY])
    first_viewed_at = (await purchase_state(db_session, purchase.id)).first_viewed_at
    assert first_viewed_at is not None

    repeat = await async_client.get(content_url(episode))

    assert repeat.status_code == 200
    assert repeat.json()["access_scope"] == "full"
    assert (await purchase_state(db_session, purchase.id)).first_viewed_at == first_viewed_at
    assert repeat.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "status",
    [PurchaseStatus.REFUND_PENDING, PurchaseStatus.REFUNDED, PurchaseStatus.REVIEW_REQUIRED],
)
async def test_inactive_purchase_only_signs_preview(
    async_client, db_session, user, presign_spy, status
):
    episode = await paid_episode(db_session, user)
    await make_purchase(db_session, user, episode, status=status)
    login(async_client, user)

    response = await async_client.get(content_url(episode))

    assert response.status_code == 200
    assert response.json()["access_scope"] == "preview"
    presign_spy.assert_awaited_once_with([FREE_KEY])


async def test_other_environment_purchase_only_signs_preview(
    async_client, db_session, user, presign_spy, monkeypatch
):
    monkeypatch.setattr(settings, "payment_environment", "live")
    episode = await paid_episode(db_session, user)
    await make_purchase(db_session, user, episode, environment="test")
    login(async_client, user)

    response = await async_client.get(content_url(episode))

    assert response.status_code == 200
    assert response.json()["access_scope"] == "preview"
    presign_spy.assert_awaited_once_with([FREE_KEY])


async def test_other_users_purchase_only_signs_preview(
    async_client, db_session, user, existing_user, presign_spy
):
    episode = await paid_episode(db_session, user)
    await make_purchase(db_session, existing_user, episode)
    login(async_client, user)
    response = await async_client.get(content_url(episode))
    assert response.status_code == 200
    assert response.json()["access_scope"] == "preview"
    presign_spy.assert_awaited_once_with([FREE_KEY])


async def test_malformed_purchase_document_cannot_get_full(
    async_client, db_session, user, presign_spy
):
    episode = await paid_episode(db_session, user)
    episode.content = doc(img(FREE_KEY), PAYWALL, {"type": "unknown", "backup_key": PAID_KEY})
    await db_session.commit()
    purchase, _ = await make_purchase(db_session, user, episode)
    login(async_client, user)

    response = await async_client.get(content_url(episode))

    assert response.status_code == 200
    assert response.json()["access_scope"] == "preview"
    assert PAID_KEY not in response.text
    presign_spy.assert_awaited_once_with([FREE_KEY])
    assert (await purchase_state(db_session, purchase.id)).first_viewed_at is None


async def test_presign_failure_does_not_record_first_issue(
    db_session, user, presign_spy, monkeypatch
):
    episode = await paid_episode(db_session, user)
    purchase, _ = await make_purchase(db_session, user, episode)
    presign_spy.side_effect = RuntimeError("presign failed")
    commit = AsyncMock(wraps=db_session.commit)
    monkeypatch.setattr(db_session, "commit", commit)

    with pytest.raises(RuntimeError, match="presign failed"):
        await episode_read_service.get_content(episode.id, db_session, user_id=user.id)

    commit.assert_not_awaited()
    assert (await purchase_state(db_session, purchase.id)).first_viewed_at is None


@pytest.mark.parametrize("already_viewed", [False, True])
async def test_refund_during_presign_discards_full_response(
    async_client, db_session, session_factory, user, presign_spy, already_viewed
):
    episode = await paid_episode(db_session, user)
    purchase, _ = await make_purchase(db_session, user, episode)
    viewed_at = datetime.now(UTC) - timedelta(minutes=1) if already_viewed else None
    purchase.first_viewed_at = viewed_at
    await db_session.commit()
    login(async_client, user)

    async def refund_while_signing(keys):
        async with session_factory() as refund_session:
            await refund_session.exec(
                update(Purchase)
                .where(Purchase.id == purchase.id)
                .values(status=PurchaseStatus.REFUND_PENDING)
                .execution_options(synchronize_session=False)
            )
            await refund_session.commit()
        return [f"https://signed.example/{key}" for key in keys]

    presign_spy.side_effect = refund_while_signing

    response = await async_client.get(content_url(episode))

    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert "https://signed.example" not in response.text
    assert "유료" not in response.text
    # ORM에 남은 active 값을 신뢰하지 않고 새 DB 컬럼을 검사해야 한다.
    assert purchase.status == PurchaseStatus.ACTIVE
    state = await purchase_state(db_session, purchase.id)
    assert state.status == PurchaseStatus.REFUND_PENDING
    assert state.first_viewed_at == viewed_at


async def test_commit_failure_prevents_full_return(
    async_client, db_session, session_factory, user, presign_spy, monkeypatch
):
    episode = await paid_episode(db_session, user)
    purchase, _ = await make_purchase(db_session, user, episode)
    episode_id, purchase_id, user_id = episode.id, purchase.id, user.id
    login(async_client, user)
    monkeypatch.setattr(
        db_session, "commit", AsyncMock(side_effect=SQLAlchemyError("commit failed"))
    )

    with pytest.raises(SQLAlchemyError, match="commit failed"):
        await async_client.get(f"/episodes/{episode_id}/content")

    presign_spy.assert_awaited_once_with([FREE_KEY, PAID_KEY])
    await db_session.rollback()
    async with session_factory() as check_session:
        assert (await purchase_state(check_session, purchase_id)).first_viewed_at is None
        assert (
            await episode_access_service.resolve_episode_access(user_id, episode_id, check_session)
        ).scope == "full"


@pytest.mark.parametrize("purchased", [False, True])
async def test_free_full_records_issue_only_for_purchase_backed_access(
    async_client, db_session, user, presign_spy, purchased
):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(para("무료")))
    purchase = None
    if purchased:
        purchase, _ = await make_purchase(db_session, user, episode)
        login(async_client, user)
    response = await async_client.get(content_url(episode))
    assert response.status_code == 200
    assert response.json()["access_scope"] == "full"
    if purchase:
        assert (await purchase_state(db_session, purchase.id)).first_viewed_at is not None
    else:
        assert (await db_session.exec(select(Purchase.id))).all() == []


async def test_response_uses_resolver_document_snapshot(
    db_session, session_factory, user, presign_spy, monkeypatch
):
    work = await make_work(db_session, user)
    episode = await make_episode(
        db_session,
        work,
        content=doc(para("원래 무료"), img(FREE_KEY)),
        image_keys=[FREE_KEY, PAID_KEY],
    )
    original_load = episode_access_service.load_episode_access

    async def replace_document_after_snapshot(user_id, episode_id, session):
        snapshot = await original_load(user_id, episode_id, session)
        async with session_factory() as editor_session:
            await editor_session.exec(
                update(Episode)
                .where(Episode.id == episode_id)
                .values(content=doc(PAYWALL, para("새 유료"), img(PAID_KEY)))
                .execution_options(synchronize_session=False)
            )
            await editor_session.commit()
        return snapshot

    monkeypatch.setattr(
        episode_access_service, "load_episode_access", replace_document_after_snapshot
    )
    result = await episode_read_service.get_content(episode.id, db_session)
    assert result.access_scope == "full"
    assert "원래 무료" in repr(result.content)
    assert "새 유료" not in repr(result.content)
    presign_spy.assert_awaited_once_with([FREE_KEY])


async def test_two_concurrent_first_issues_have_one_winner(
    db_session, session_factory, user, presign_spy, monkeypatch
):
    episode = await paid_episode(db_session, user)
    purchase, _ = await make_purchase(db_session, user, episode)
    barrier = asyncio.Barrier(2)

    async def issue():
        async with session_factory() as session:
            execute = session.exec

            async def wait_before_update(statement, *args, **kwargs):
                if isinstance(statement, Update):
                    # 최초 snapshot SELECT가 끝난 두 독립 세션만 UPDATE로 진입한다.
                    await barrier.wait()
                return await execute(statement, *args, **kwargs)

            monkeypatch.setattr(session, "exec", wait_before_update)
            try:
                return await episode_read_service.get_content(episode.id, session, user_id=user.id)
            except EpisodeAccessConflictError as exc:
                return exc

    results = await asyncio.wait_for(asyncio.gather(issue(), issue()), timeout=10)

    assert sum(isinstance(result, EpisodeAccessConflictError) for result in results) == 1
    assert sum(getattr(result, "access_scope", None) == "full" for result in results) == 1
    assert (await purchase_state(db_session, purchase.id)).first_viewed_at is not None


@pytest.mark.parametrize("winner", ["view", "refund"])
async def test_first_issue_and_refund_cas_have_one_winner(
    db_session, session_factory, user, presign_spy, monkeypatch, winner
):
    episode = await paid_episode(db_session, user)
    purchase, _ = await make_purchase(db_session, user, episode)
    barrier = asyncio.Barrier(2)
    winner_updated = asyncio.Event()
    loser_attempting = asyncio.Event()

    async def synchronized_update(side, execute, statement, *args, **kwargs):
        # 양쪽 모두 SELECT를 끝낸 뒤 UPDATE 직전에서 만난다.
        await barrier.wait()
        if side != winner:
            await winner_updated.wait()
            loser_attempting.set()
            return await execute(statement, *args, **kwargs)
        result = await execute(statement, *args, **kwargs)
        # 승자가 행 잠금을 보유한 동안 패자도 UPDATE에 진입시켜 PostgreSQL 경합을 만든다.
        winner_updated.set()
        await loser_attempting.wait()
        return result

    async def issue():
        async with session_factory() as session:
            execute = session.exec

            async def execute_with_barrier(statement, *args, **kwargs):
                if isinstance(statement, Update):
                    return await synchronized_update("view", execute, statement, *args, **kwargs)
                return await execute(statement, *args, **kwargs)

            monkeypatch.setattr(session, "exec", execute_with_barrier)
            try:
                return await episode_read_service.get_content(episode.id, session, user_id=user.id)
            except EpisodeAccessConflictError:
                return None

    async def refund():
        async with session_factory() as session:
            status, first_viewed_at = await purchase_state(session, purchase.id)
            assert status == PurchaseStatus.ACTIVE
            assert first_viewed_at is None
            # 환불 서비스는 후속 범위다. 합의된 동일 행 자격 CAS만 여기서 모사한다.
            result = await synchronized_update(
                "refund",
                session.exec,
                update(Purchase)
                .where(
                    Purchase.id == purchase.id,
                    Purchase.status == PurchaseStatus.ACTIVE,
                    Purchase.first_viewed_at.is_(None),
                    Purchase.paid_at > datetime.now(UTC) - timedelta(hours=168),
                )
                .values(status=PurchaseStatus.REFUND_PENDING)
                .returning(Purchase.id)
                .execution_options(synchronize_session=False),
            )
            won = result.first() is not None
            await session.commit()
            return won

    content, refund_won = await asyncio.wait_for(asyncio.gather(issue(), refund()), timeout=10)

    assert (content is not None) + refund_won == 1
    state = await purchase_state(db_session, purchase.id)
    if winner == "view":
        assert content.access_scope == "full"
        assert state.status == PurchaseStatus.ACTIVE
        assert state.first_viewed_at is not None
    else:
        assert content is None
        assert state.status == PurchaseStatus.REFUND_PENDING
        assert state.first_viewed_at is None
