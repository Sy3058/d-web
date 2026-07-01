"""작품/에피소드 도메인 모델 테스트 (M1.5 A1).

round-trip(기본값) + 제약(UNIQUE/CASCADE) + image_keys 순서 보존. db_session·user 픽스처 사용.
FK 부모(author/work)를 먼저 만든 뒤 자식을 INSERT한다(MISTAKES: FK INSERT는 부모 먼저).
"""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from src.models.user import User
from src.models.work import Episode, Tag, Work, WorkStatus, WorkTag


async def _make_work(db_session, author: User, **overrides) -> Work:
    work = Work(author_id=author.id, title=overrides.pop("title", "테스트작"), **overrides)
    db_session.add(work)
    await db_session.commit()
    await db_session.refresh(work)
    return work


# ---------------------------------------------------------------------------
# round-trip + 기본값
# ---------------------------------------------------------------------------


async def test_work_defaults_round_trip(db_session, user: User):
    work = await _make_work(db_session, user)

    assert work.id is not None
    assert work.author_id == user.id
    assert work.episode_base_price == 500
    assert work.bundle_discount_rate == Decimal("0.1")
    assert work.status == WorkStatus.ONGOING
    assert work.created_at is not None
    assert work.updated_at is not None
    assert work.deleted_at is None


async def test_episode_defaults_round_trip(db_session, user: User):
    work = await _make_work(db_session, user)
    ep = Episode(work_id=work.id, episode_no=1, title="1화")
    db_session.add(ep)
    await db_session.commit()
    await db_session.refresh(ep)

    assert ep.id is not None
    assert ep.image_keys == []
    assert ep.is_free is False
    assert ep.is_published is False
    assert ep.price is None
    assert ep.published_at is None
    assert ep.created_at is not None


async def test_episode_image_keys_order_preserved(db_session, user: User):
    work = await _make_work(db_session, user)
    keys = ["001.webp", "002.webp", "003.webp"]
    ep = Episode(work_id=work.id, episode_no=1, title="1화", image_keys=keys)
    db_session.add(ep)
    await db_session.commit()
    await db_session.refresh(ep)

    assert ep.image_keys == keys  # 배열 인덱스 = 페이지 순서


# ---------------------------------------------------------------------------
# 제약
# ---------------------------------------------------------------------------


async def test_episode_unique_work_id_episode_no(db_session, user: User):
    work = await _make_work(db_session, user)
    db_session.add(Episode(work_id=work.id, episode_no=1, title="1화"))
    await db_session.commit()

    db_session.add(Episode(work_id=work.id, episode_no=1, title="중복 회차"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_tag_name_unique(db_session):
    db_session.add(Tag(name="로맨스"))
    await db_session.commit()

    db_session.add(Tag(name="로맨스"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_works_tags_cascade_on_work_delete(db_session, user: User):
    work = await _make_work(db_session, user)
    tag = Tag(name="판타지")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    db_session.add(WorkTag(work_id=work.id, tag_id=tag.id))
    await db_session.commit()

    # 작품 하드 삭제 → works_tags 행이 ON DELETE CASCADE로 함께 사라진다
    await db_session.delete(work)
    await db_session.commit()

    rows = (await db_session.exec(select(WorkTag).where(WorkTag.work_id == work.id))).all()
    assert rows == []
    # 태그 자체는 남는다(작품-태그 연결만 끊김)
    assert (await db_session.exec(select(Tag).where(Tag.id == tag.id))).first() is not None
