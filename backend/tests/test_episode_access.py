import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from src.config import settings
from src.models.payment import (
    PaymentOrderStatus,
    Purchase,
    PurchaseStatus,
)
from src.models.user import User
from src.models.work import Episode, Work
from src.services.episode_access_service import (
    EpisodeAccessResult,
    EpisodeAccessScope,
    resolve_episode_access,
)
from tests.factories import PAYWALL, doc, make_episode, make_work, para
from tests.factories import make_purchase as _purchase


def test_result_is_immutable():
    result = EpisodeAccessResult(EpisodeAccessScope.FULL)
    with pytest.raises(FrozenInstanceError):
        result.scope = EpisodeAccessScope.PREVIEW


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "is_free", "expected"),
    [
        (doc(para("무료")), False, "full"),
        (doc(para("미리보기"), PAYWALL, para("유료")), True, "preview"),
        (doc(para("무료"), PAYWALL, {"type": "paragraph"}), False, "full"),
        ({"type": "doc", "content": "broken"}, True, "preview"),
        (doc({"type": "unknown"}), True, "preview"),
    ],
)
async def test_public_access_uses_validated_document(db_session, user, content, is_free, expected):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=content, is_free=is_free)
    assert await resolve_episode_access(None, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope(expected)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden", ["work", "episode", "both"])
async def test_purchase_allows_unpublished_content(db_session, user, hidden):
    work = await make_work(db_session, user, is_published=hidden == "episode")
    episode = await make_episode(
        db_session, work, is_published=hidden == "work", content=doc(PAYWALL, para("유료"))
    )
    assert (await resolve_episode_access(None, episode.id, db_session)).scope == "unavailable"
    purchase, order = await _purchase(db_session, user, episode)
    order.status = PaymentOrderStatus.REVIEW_REQUIRED
    await db_session.commit()
    assert await resolve_episode_access(user.id, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope.FULL, purchase.id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(PurchaseStatus))
async def test_only_active_purchase_grants_full(db_session, user, status):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    purchase, _ = await _purchase(db_session, user, episode, status=status)
    expected = (
        EpisodeAccessResult(EpisodeAccessScope.FULL, purchase.id)
        if status == PurchaseStatus.ACTIVE
        else EpisodeAccessResult(EpisodeAccessScope.PREVIEW)
    )
    assert await resolve_episode_access(user.id, episode.id, db_session) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["test", "live"])
async def test_purchase_is_scoped_to_current_environment(
    db_session, user, monkeypatch, environment
):
    monkeypatch.setattr(settings, "payment_environment", "live")
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    purchase, _ = await _purchase(db_session, user, episode, environment=environment)
    expected = (
        EpisodeAccessResult(EpisodeAccessScope.FULL, purchase.id)
        if environment == "live"
        else EpisodeAccessResult(EpisodeAccessScope.PREVIEW)
    )
    assert await resolve_episode_access(user.id, episode.id, db_session) == expected


@pytest.mark.asyncio
async def test_other_user_or_episode_purchase_cannot_grant_access(db_session, user, existing_user):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    other_episode = await make_episode(db_session, work, content=doc(PAYWALL, para("다른 회차")))
    await _purchase(db_session, existing_user, episode)
    await _purchase(db_session, user, other_episode)
    assert await resolve_episode_access(user.id, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope.PREVIEW
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", ["work", "episode", "user"])
async def test_deletion_overrides_purchase_and_reads_latest_columns(db_session, user, deleted):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    await _purchase(db_session, user, episode)
    model, instance = {"work": (Work, work), "episode": (Episode, episode), "user": (User, user)}[
        deleted
    ]
    await db_session.exec(
        update(model)
        .where(model.id == instance.id)
        .values(deleted_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert instance.deleted_at is None
    expected = "preview" if deleted == "user" else "unavailable"
    assert (await resolve_episode_access(user.id, episode.id, db_session)).scope == expected


@pytest.mark.asyncio
async def test_missing_episode_is_unavailable(db_session):
    assert await resolve_episode_access(None, uuid.uuid4(), db_session) == EpisodeAccessResult(
        EpisodeAccessScope.UNAVAILABLE
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("published", [True, False])
async def test_malformed_document_fails_closed_even_with_purchase(db_session, user, published):
    work = await make_work(db_session, user)
    episode = await make_episode(
        db_session, work, is_published=published, content=doc({"type": "unknown"})
    )
    await _purchase(db_session, user, episode)
    assert await resolve_episode_access(user.id, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope.PREVIEW if published else EpisodeAccessScope.UNAVAILABLE
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("image_keys", [None, {}, "key", [None], [["key"]]])
async def test_malformed_image_manifest_fails_closed(db_session, user, image_keys):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(para("무료")), image_keys=image_keys)
    assert await resolve_episode_access(None, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope.PREVIEW
    )


@pytest.mark.asyncio
async def test_purchase_revocation_reads_latest_columns(db_session, user):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(PAYWALL, para("유료")))
    purchase, _ = await _purchase(db_session, user, episode)
    assert (await resolve_episode_access(user.id, episode.id, db_session)).scope == "full"
    await db_session.exec(
        update(Purchase)
        .where(Purchase.id == purchase.id)
        .values(status=PurchaseStatus.REFUND_PENDING)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert purchase.status == PurchaseStatus.ACTIVE
    assert await resolve_episode_access(user.id, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope.PREVIEW
    )


@pytest.mark.asyncio
async def test_unpublication_reads_latest_columns(db_session, user):
    work = await make_work(db_session, user)
    episode = await make_episode(db_session, work, content=doc(para("무료")))
    await db_session.exec(
        update(Episode)
        .where(Episode.id == episode.id)
        .values(is_published=False)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    assert episode.is_published is True
    assert await resolve_episode_access(None, episode.id, db_session) == EpisodeAccessResult(
        EpisodeAccessScope.UNAVAILABLE
    )
