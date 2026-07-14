"""작품 CRUD 서비스 (M1.5 C1).

router는 HTTP 매핑만(404 등), 여기는 순수 DB 로직 + 트랜잭션 경계.
태그는 이름으로 get-or-create 후 works_tags에 연결한다(tags.name UNIQUE가 동시성 백스톱 - A1).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.work import Tag, Work
from src.schemas.work import WorkCreate, WorkUpdate
from src.services import r2_service


async def _select_tags_by_name(names: list[str], session: AsyncSession) -> dict[str, Tag]:
    result = await session.exec(select(Tag).where(Tag.name.in_(names)))
    return {tag.name: tag for tag in result.all()}


async def _get_or_create_tags(names: list[str], session: AsyncSession) -> list[Tag]:
    """이름 리스트를 Tag 행으로 해석한다. 없는 이름은 배치로 한 번에 생성.

    생성 flush는 SAVEPOINT(begin_nested) 안에서 한다. 동시 요청이 같은 이름을 먼저
    커밋해 UNIQUE 충돌이 나도 SAVEPOINT만 롤백되고, 호출자가 로드해 둔 다른 객체
    (update 경로의 work 등)는 만료되지 않는다 - 세션 전체 rollback()은 로드된 객체를
    전부 expire시켜 이후 work.tags 대입이 동기 lazy load(MissingGreenlet)로 죽는다
    (2026-07-09 리뷰 발견). 충돌 시 재조회로 커밋된 행을 재사용하고, 그래도 없는
    이름은 그대로 전파한다 - 재-flush 재시도는 2차 충돌이 미처리로 터지는 데다
    단일 owner 운영에선 복구할 가치가 없어 두지 않는다.
    """
    # 방어적 dedup(순서 유지): HTTP 경로는 스키마가 이미 걸러주지만, 검증을 우회하는
    # 호출자(스크립트 등)가 중복을 넘기면 works_tags 복합 PK 충돌로 500이 나므로 여기서도 거른다.
    names = list(dict.fromkeys(names))
    if not names:
        return []
    found = await _select_tags_by_name(names, session)
    missing = [name for name in names if name not in found]
    if not missing:
        return [found[name] for name in names]

    new_tags = [Tag(name=name) for name in missing]
    try:
        async with session.begin_nested():
            session.add_all(new_tags)
            await session.flush()
    except IntegrityError:
        # 경합 상대가 커밋한 행을 재사용. 그래도 없는 이름이면 KeyError 전파(비정상 상태).
        found = await _select_tags_by_name(names, session)
    else:
        found.update({tag.name: tag for tag in new_tags})
    return [found[name] for name in names]


async def _load_episode_count(work: Work, session: AsyncSession) -> None:
    """episode_count(column_property)를 커밋 후 다시 채운다.

    column_property는 컬럼이 아니라 SQL 표현식이라 (a) INSERT/UPDATE RETURNING으로 받을 수
    없고(eager_defaults 대상 아님), (b) flush 후에는 값이 달라졌을 수 있다고 보고 만료된다.
    만료된 채로 응답 직렬화가 읽으면 lazy load가 async 밖에서 터진다(MissingGreenlet).
    """
    await session.refresh(work, attribute_names=["episode_count"])


async def create_work(data: WorkCreate, author_id: uuid.UUID, session: AsyncSession) -> Work:
    """작품 생성. author_id는 라우터가 require_owner 결과로 넘긴다(클라 입력 무시).

    필드 복사는 model_dump 기반 - 수동 나열은 WorkCreate에 필드가 늘 때 여기를 빠뜨려도
    에러 없이 값만 조용히 유실되는 함정이 있다(2026-07-09 리뷰). commit 후 refresh는
    불필요: expire_on_commit=False라 대입해 둔 tags가 그대로 살아 있고, 서버 계산 컬럼은
    INSERT RETURNING(eager_defaults)으로 이미 채워진다.
    """
    tags = await _get_or_create_tags(data.tag_names, session)
    work = Work(**data.model_dump(exclude={"tag_names"}), author_id=author_id, tags=tags)
    session.add(work)
    await session.commit()
    await _load_episode_count(work, session)
    return work


async def list_works(session: AsyncSession) -> Sequence[Work]:
    """soft-delete 제외, 최신순. selectinload로 태그까지 한 쿼리에 로드(N+1 방지)."""
    result = await session.exec(
        select(Work)
        .where(Work.deleted_at.is_(None))  # type: ignore[union-attr]
        .options(selectinload(Work.tags))
        .order_by(Work.created_at.desc())  # type: ignore[union-attr]
    )
    return result.all()


async def get_work(
    work_id: uuid.UUID, session: AsyncSession, *, with_tags: bool = True
) -> Work | None:
    """soft-delete 제외 단건 조회. 없으면 None(404 매핑은 라우터).

    with_tags=False는 태그를 읽지 않는 경로(삭제의 존재 확인)용 - 응답에 태그가 나가거나
    work.tags를 대입(update)할 경로는 반드시 True로 로드해 둬야 한다(N+1/lazy load 규칙).
    """
    stmt = select(Work).where(Work.id == work_id, Work.deleted_at.is_(None))  # type: ignore[union-attr]
    if with_tags:
        stmt = stmt.options(selectinload(Work.tags))
    result = await session.exec(stmt)
    return result.first()


async def update_work(work: Work, data: WorkUpdate, session: AsyncSession) -> Work:
    """부분 수정(exclude_unset). tag_names 미제공=유지, []=전부 해제, 리스트=전체 교체.

    commit 후 refresh는 불필요 - updated_at 등 서버 계산 컬럼은 UPDATE RETURNING
    (eager_defaults)으로 즉시 채워지고, tags는 로드/대입된 상태 그대로다.
    """
    new_tags = None
    if data.tag_names is not None:
        new_tags = await _get_or_create_tags(data.tag_names, session)

    changes = data.model_dump(exclude_unset=True, exclude={"tag_names"})
    for field, value in changes.items():
        setattr(work, field, value)
    if new_tags is not None:
        work.tags = new_tags
        # 다대다 연결만 바뀌면 works 행 UPDATE 자체가 없어 onupdate가 발화하지 않는다
        # (2026-07-09 리뷰) - DB 시계로 명시 갱신해 태그 변경도 최종 수정 시각에 반영.
        work.updated_at = func.now()  # type: ignore[assignment]

    session.add(work)
    await session.commit()
    await _load_episode_count(work, session)
    return work


async def soft_delete_work(work: Work, session: AsyncSession) -> None:
    """deleted_at 세팅만(하드 삭제·CASCADE 금지 - A1 결정). 에피소드는 그대로 남는다."""
    work.deleted_at = datetime.now(UTC)
    session.add(work)
    await session.commit()


async def set_cover_image(work: Work, webp: bytes, session: AsyncSession) -> Work:
    """변환 완료된 표지 WebP를 R2에 올리고 cover_image 키를 갱신한다 (M1.5 D3).

    표지는 작품당 1장 고정 키(works/{id}/cover.webp) - 재업로드는 같은 키를
    덮어쓰므로 미참조 파일(orphan)이 생기지 않고 DB 값도 사실상 불변이다. C1의 "키 문자열
    직접 수용"(WorkCreate/Update.cover_image)은 하위호환으로 유지된다.
    """
    key = await r2_service.upload_bytes(r2_service.cover_key(work.id), webp)
    work.cover_image = key
    session.add(work)
    await session.commit()
    await _load_episode_count(work, session)
    return work
