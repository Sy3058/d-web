"""에피소드 서비스 (M1.5 D3, ADM-03).

구조 A(장당 업로드 + JSON 메타 분리 - 2026-07-10 council 검증 후 확정):
draft 생성이 이미지보다 먼저라 public_id 발급 실패가 업로드 전에 발각되고,
이미지는 단건 append라 메모리·재시도·R2 미참조 파일(orphan)이 전부 1장 단위다.

표시 순서·구성의 진실은 F3 재설계(2026-07-15)로 **content 문서**로 이동했고,
image_keys는 업로드 매니페스트(이 회차가 소유한 R2 키 전량)다. 키 파일명은
uuid(순수 식별자, 순서 의미 없음) - 순번 파일명은 동시 업로드가 stale 스냅샷으로
같은 번호를 계산해 살아있는 객체를 덮어쓰는 구멍이라 리뷰에서 폐기(2026-07-10 리뷰 ①·⑦).
"""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.content_doc import (
    content_image_keys,
    derive_is_free,
    empty_doc,
    has_meaningful_content,
    validate_content,
)
from src.lib.exceptions import EpisodeConflictError, EpisodeValidationError
from src.models.work import Episode, Work
from src.schemas.work import EpisodeCreate, EpisodeUpdate
from src.services import r2_service
from src.services.image_service import MAX_IMAGES_PER_EPISODE, THUMB_WIDTH, convert_to_webp

_STALE_EPISODE = "회차가 다른 요청으로 먼저 변경되었습니다 - 새로고침 후 다시 시도하세요"
_PUBLISHED_CONTENT_GUARD = (
    "공개 회차의 본문은 발행 액션(is_published 동반)으로만 수정할 수 있습니다"
    " - 임시저장은 draft를 사용하세요"
)
_DRAFT_KEYS_REMOVED = "image_keys 축소가 임시저장본(draft)이 참조하는 키를 제거합니다"
_PUBLIC_ID_EXHAUSTED = "회차 식별자 발급에 반복 실패했습니다 - 다시 시도해 주세요"
_REORDER_SET_MISMATCH = "목록이 바뀌었습니다(회차 추가·삭제) - 새로고침 후 다시 정렬해 주세요"

_PUBLIC_ID_MIN = 10_000_000
_PUBLIC_ID_MAX = 99_999_999
_PUBLIC_ID_MAX_ATTEMPTS = 5

logger = structlog.get_logger(__name__)


def _generate_public_id() -> int:
    return secrets.randbelow(_PUBLIC_ID_MAX - _PUBLIC_ID_MIN + 1) + _PUBLIC_ID_MIN


async def create_episode(work_id: uuid.UUID, data: EpisodeCreate, session: AsyncSession) -> Episode:
    """draft 생성(is_published=false, 빈 문서).

    public_id(독자 URL 조회키)는 서버가 무작위 발급한다(회차 번호 폐기, DECISIONS
    2026-07-28) - 클라이언트 입력이 아니라 secrets.randbelow로 뽑고 충돌은
    UNIQUE(public_id)가 최종 백스톱(C1 태그와 동일 계열). 라우터가 work_id를
    미리 404 검증하므로(admin_episodes._work_or_404) 여기서 잡히는 IntegrityError는
    항상 public_id 충돌이다. rollback()은 세션의 ORM 인스턴스를 전부 만료시키므로
    재시도마다 새 Episode 인스턴스를 만든다 - 만료된 인스턴스를 재사용하면 다음
    커밋에서 async 밖 lazy load(MissingGreenlet)로 죽는다.

    is_free=True 명시: is_free는 content 파생 컬럼이고 빈 문서 = 무료가 정합
    (derive_is_free(EMPTY_DOC) == True). 모델 컬럼 기본값 false에 맡기면
    "내용 없는 draft가 유료"라는 모순 상태로 시작한다.
    """
    payload = data.model_dump()
    # 표시 순서는 작품 안에서 max+1. UNIQUE가 없으므로 동시 생성이 같은 값을 잡아도
    # 에러가 아니라 동점이고 (created_at, id)가 순서를 확정한다 - episode_no와 달리
    # 409를 낼 이유가 없다. soft delete된 회차도 max에 포함해서, 되살렸을 때 뒤에
    # 생긴 회차에게 자리를 뺏기지 않게 한다.
    order_stmt = select(func.coalesce(func.max(Episode.sort_order), 0)).where(
        Episode.work_id == work_id
    )
    next_sort_order = (await session.exec(order_stmt)).one() + 1

    for attempt in range(_PUBLIC_ID_MAX_ATTEMPTS):
        # 로그에 쓰려고 지역 변수로 먼저 잡는다 - rollback 뒤에 episode.public_id를 읽으면
        # 만료된 인스턴스의 lazy load라 MissingGreenlet으로 죽는다(위 독스트링과 같은 함정).
        public_id = _generate_public_id()
        episode = Episode(
            **payload,
            work_id=work_id,
            is_free=True,
            public_id=public_id,
            sort_order=next_sort_order,
        )
        session.add(episode)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            # 충돌 자체는 정상 동작(UNIQUE가 백스톱)이지만 조용히 넘기면 키스페이스가
            # 좁아져도 알 방법이 없다. 충돌 확률은 회차 수의 **제곱**에 비례해 커지므로
            # (생일 문제), 이 로그의 빈도가 public_id 자릿수를 늘릴 시점을 알려주는
            # 유일한 신호다.
            logger.warning(
                "episode_public_id_collision",
                work_id=str(work_id),
                public_id=public_id,
                attempt=attempt + 1,
            )
            if attempt == _PUBLIC_ID_MAX_ATTEMPTS - 1:
                raise EpisodeConflictError(_PUBLIC_ID_EXHAUSTED) from exc
            continue
        return episode
    raise AssertionError("unreachable - loop always returns or raises")


async def list_episodes(work_id: uuid.UUID, session: AsyncSession) -> Sequence[Episode]:
    # sort_order(작가 지정) 우선, created_at·id는 tie-breaker다(회차 번호 폐기,
    # DECISIONS 2026-07-28). sort_order에 UNIQUE가 없어 동점이 정상적으로 생기므로
    # tie-breaker는 장식이 아니라 순서를 확정하는 필수 요소다.
    # published_at으로 정렬하지 않는 이유: 내렸다 재공개해도 원래 자리를 유지해야
    # 하는데 published_at 정렬이면 재공개 시 맨 뒤로 밀린다.
    result = await session.exec(
        select(Episode)
        .where(Episode.work_id == work_id, Episode.deleted_at.is_(None))
        .order_by(Episode.sort_order, Episode.created_at, Episode.id)
    )
    return result.all()


async def reorder_episodes(
    work_id: uuid.UUID, episode_ids: Sequence[uuid.UUID], session: AsyncSession
) -> Sequence[Episode]:
    """작가가 끌어 놓은 순서대로 sort_order를 1..N으로 재배정한다.

    부분 목록을 받지 않는다 - 살아있는 회차 **전량과 정확히 일치하는 집합**이어야 하고
    아니면 409다. 부분 갱신을 허용하면 다른 탭에서 회차를 추가·삭제한 뒤 stale한 목록으로
    요청했을 때 빠진 회차가 조용히 엉뚱한 자리로 밀리는데, "순서"는 전체 집합에 대한
    진술이라 부분 적용이 의미를 갖지 않는다. 집합 비교가 곧 낙관적 동시성 검사 역할을
    한다(별도 버전 토큰 불요).

    soft delete된 회차는 대상이 아니다(list_episodes가 이미 제외). 그래서 재배열 후
    삭제 회차의 sort_order는 살아있는 회차와 겹칠 수 있는데, UNIQUE가 없어 문제가
    아니고 되살리면 tie-breaker가 자리를 정한다.
    """
    current = await list_episodes(work_id, session)
    requested = list(episode_ids)
    if len(requested) != len(set(requested)) or set(requested) != {e.id for e in current}:
        raise EpisodeConflictError(_REORDER_SET_MISMATCH)

    for position, episode_id in enumerate(requested, start=1):
        await session.exec(
            update(Episode)
            .where(Episode.id == episode_id)
            .values(sort_order=position)
            .execution_options(synchronize_session=False)
        )
    await session.commit()
    # bulk UPDATE(synchronize_session=False)는 인메모리 객체를 안 맞춰주고, 세션이
    # expire_on_commit=False(lib/db.py)라 커밋도 만료시키지 않는다. 그 상태로 다시
    # 조회하면 identity map이 **로드된 옛 속성을 그대로 둔 채** 같은 인스턴스를 돌려줘
    # 행 순서만 맞고 sort_order 값은 옛것이 나간다(2026-08-03 실측: 응답 순서는
    # [c,a,b]인데 sort_order가 [3,1,2]). refresh를 N번 도는 대신 만료만 표시해
    # 아래 SELECT 한 번이 값을 덮어쓰게 한다.
    for episode in current:
        session.expire(episode)
    return await list_episodes(work_id, session)


async def get_episode(
    work_id: uuid.UUID, episode_id: uuid.UUID, session: AsyncSession
) -> Episode | None:
    """work 스코프 + soft-delete 확인 단건 조회.

    Work를 join해 deleted_at까지 한 쿼리로 거른다 - 안 거르면 삭제된 작품의
    에피소드에 업로드·수정·공개가 통과하는 비대칭이 생긴다(생성·목록은 404인데
    업로드·PUT은 200 - 2026-07-10 리뷰 ⑤).

    회차 자신의 deleted_at도 같이 본다(#85). 이 함수가 라우터의 _episode_or_404
    관문이라, 여기서 걸러야 삭제된 회차의 수정·이미지 업로드·재공개가 전부 404가
    된다 - 특히 PUT이 막혀야 "삭제 ⟹ 비공개" 불변식을 되돌릴 경로가 없어진다.
    """
    result = await session.exec(
        select(Episode)
        .join(Work, Work.id == Episode.work_id)  # type: ignore[arg-type]
        .where(
            Episode.id == episode_id,
            Episode.work_id == work_id,
            Episode.deleted_at.is_(None),  # type: ignore[union-attr]
            Work.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.first()


async def append_image(
    work_id: uuid.UUID,
    episode_id: uuid.UUID,
    expected_len: int,
    webp: bytes,
    session: AsyncSession,
) -> Episode:
    """변환 완료된 WebP 1장을 R2에 올리고 image_keys 끝에 원자적으로 붙인다.

    호출자(라우터)는 에피소드 존재 확인 후 **읽기 트랜잭션을 닫고**(rollback)
    변환까지 마친 뒤 진입한다 - 변환(CPU 수 초)·R2 업로드(재시도 시 분 단위)
    동안 DB 커넥션을 점유하지 않기 위해(리뷰 ⑨). expected_len은 그 시점 스냅샷.

    R2 업로드가 DB보다 먼저다(외부 호출과 DB 트랜잭션 분리) - 조건부 UPDATE가
    지면 방금 올린 객체 1개가 미참조 파일로 남는다(수용: uuid 키라 살아있는 키와의
    충돌은 불가능, 미참조 파일 정리는 후속 노트). 반대 순서(DB 먼저)면 업로드 실패
    시 DB가 없는 키를 가리켜 뷰어가 깨진다 - 미참조 파일이 깨진 참조보다 싸다.
    """
    key = r2_service.episode_page_key(work_id, episode_id)
    await r2_service.upload_bytes(key, webp)

    # 낙관적 조건부 UPDATE 하나로 append와 장수 상한을 원자화한다. 길이 기대값이
    # 어긋나면(동시 append·재배열이 먼저 커밋) 0행 매칭 - check-then-act 없이
    # DB가 단일 승자를 보장하고, 상한 검사도 같은 문장이라 51장 race가 불가능.
    result = await session.exec(
        update(Episode)
        .where(
            Episode.id == episode_id,
            func.jsonb_array_length(Episode.image_keys) == expected_len,
            func.jsonb_array_length(Episode.image_keys) < MAX_IMAGES_PER_EPISODE,
        )
        .values(image_keys=Episode.image_keys.op("||")(func.jsonb_build_array(key)))
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise EpisodeConflictError(_STALE_EPISODE)
    await session.commit()

    episode = await get_episode(work_id, episode_id, session)
    if episode is None:
        # UPDATE 성공 직후 소실 = 동시 삭제 계열 - 방어적 충돌 처리
        raise EpisodeConflictError(_STALE_EPISODE)
    return episode


def _validate_reorder(current: list[str], new: list[str]) -> None:
    """재배열 = 기존 키의 **중복 없는 부분집합**(순서 자유, 삭제 허용, 주입·복제 금지).

    set 비교만 하면 같은 키를 두 번 넣은 배열이 통과한다(council - multiset 검사).
    제거된 키의 R2 객체는 미참조 파일로 남긴다(정리 후속 노트 - 스토리지 저가, 차단 아님).
    """
    if len(new) != len(set(new)):
        raise EpisodeValidationError("image_keys에 중복 키가 있습니다")
    if not set(new) <= set(current):
        raise EpisodeValidationError("image_keys에 이 회차의 키가 아닌 값이 있습니다")


async def update_episode(episode: Episode, data: EpisodeUpdate, session: AsyncSession) -> Episode:
    """메타 부분수정 + 본문(content) 저장 + 매니페스트 정리 + 썸네일 선택 + 공개 전환.

    **검증 전부 → 실행** 순서(validate-then-mutate): 검증 실패 raise 경로에서
    세션에 dirty 변이가 남지 않는다(리뷰 ⑧). thumbnail은 최종 image_keys와 발행본
    content 이미지 키 양쪽을 기준으로 검증하고, 어느 쪽에서든 선택 페이지가 제거되면
    자동 NULL 처리한다.

    content(F3 재설계): 최종 image_keys 기준으로 lib/content_doc 검증(화이트리스트·
    상한·이미지 키 소유·paywall 규칙). 유의미 내용이 없으면 EMPTY_DOC으로 정규화
    (스케줄러의 SQL 공개 가드 성립 조건). is_free는 저장되는 문서에서 파생 -
    직접 입력 폐지.

    image_keys **또는 content** 변경이 포함되면 append와 같은 **길이-가드 조건부
    UPDATE**로 실행한다 - 인플라이트 업로드가 먼저 커밋됐으면 rowcount 0 → 409로
    거부해, 200을 받은 업로드 결과를 stale 배열이 조용히 지우는 유실(리뷰 ②)과,
    stale 매니페스트 스냅샷으로 검증된 content가 커밋돼 "content 이미지 키 ⊆
    image_keys" 불변식이 깨지는 것(F3 리뷰 m1)을 막는다. 메타만 바꾸는 요청은
    ORM 경로(메타 lost update는 단일 owner 수용, 버전 컬럼 후속). 길이 가드로도
    못 막던 역순 경합(content·thumbnail을 서로 stale한 스냅샷으로 검증)은 해당 두
    컬럼의 로드값도 WHERE 조건에 넣어 409로 닫는다. 전 필드 lost update의 일반 해법인
    버전 컬럼은 별도 범위다 - see #75.

    공개 시맨틱(리뷰 ③): true 전환 시 published_at이 요청에 없고 NULL·미래면
    now 스탬프(공개 회차는 항상 유효한 공개 시각 보유 - M2 정렬·partial 인덱스
    계약). false 전환 시 published_at은 페이로드와 무관하게 항상 NULL 초기화
    (E1 재공개 차단 - 재예약은 별도 요청). 공개 결과 상태는 본문에 유의미
    콘텐츠(글/이미지) 필요(빈 draft 공개·공개 회차 본문 전삭제 차단 - 리뷰 ④
    계승. 예약만 걸린 draft는 허용, E1이 공개 전환 시점에 재검사).

    편집본 분리(#86): draft(봉투 {title, subtitle, content})는 발행본과 별개로
    저장·버리기(null)만 되고 content·is_published·is_free를 건드리지 않는다.
    **공개 회차의 content는 is_published를 동반한 요청만 덮을 수 있다** - 위반은
    409. 로드 시점엔 비공개였다가 스케줄러가 공개 전환한 race는 조건부 UPDATE의
    is_published=false 가드가 원자적으로 닫는다(#86 사고의 race 재발 경로).
    content 쓰기는 draft를 항상 NULL로 비운다(발행 = 편집본 소진).
    """
    changes = data.model_dump(exclude_unset=True)
    new_keys: list[str] | None = changes.pop("image_keys", None)
    expected_len = len(episode.image_keys)
    draft_sent = "draft" in changes

    if new_keys is not None:
        _validate_reorder(episode.image_keys, new_keys)
    final_keys = episode.image_keys if new_keys is None else new_keys

    final_content = changes.get("content", episode.content)
    if "content" in changes or new_keys is not None:
        validate_content(final_content, set(final_keys))
    if "content" in changes:
        if episode.is_published and "is_published" not in changes:
            raise EpisodeConflictError(_PUBLISHED_CONTENT_GUARD)
        if not has_meaningful_content(final_content):
            final_content = empty_doc()
            changes["content"] = final_content
        changes["is_free"] = derive_is_free(final_content)
        changes["draft"] = None

    if draft_sent and changes["draft"] is not None:
        # 봉투 형태(title 등)는 스키마(EpisodeDraft)가 보장, 문서 검증은 발행본과 동일
        # 기준 - 임시저장이라고 임의 키 주입·상한 초과가 허용되면 발행 시점 검증이
        # 뚫리는 게 아니라 "검증 안 된 문서가 DB에 산다"가 이미 사고다.
        validate_content(changes["draft"]["content"], set(final_keys))
    elif not draft_sent and "content" not in changes and new_keys is not None:
        stored_draft = episode.draft
        if stored_draft is not None:
            try:
                validate_content(stored_draft.get("content"), set(final_keys))
            except EpisodeValidationError as exc:
                raise EpisodeValidationError(_DRAFT_KEYS_REMOVED) from exc

    final_content_keys = content_image_keys(final_content)
    if "thumbnail" in changes:
        requested_thumbnail = changes["thumbnail"]
        if requested_thumbnail is not None and (
            requested_thumbnail not in final_keys or requested_thumbnail not in final_content_keys
        ):
            raise EpisodeValidationError("thumbnail은 최종 본문에 포함된 이미지 키여야 합니다")
    elif (
        ("content" in changes or new_keys is not None)
        and episode.thumbnail is not None
        and (episode.thumbnail not in final_keys or episode.thumbnail not in final_content_keys)
    ):
        changes["thumbnail"] = None

    final_published = changes.get("is_published", episode.is_published)
    if final_published and not has_meaningful_content(final_content):
        raise EpisodeValidationError("공개 회차에는 본문 내용(글 또는 이미지)이 필요합니다")
    if "is_published" in changes:
        if changes["is_published"]:
            planned = changes.get("published_at", episode.published_at)
            if planned is None or planned > datetime.now(UTC):
                planned = datetime.now(UTC)
                changes["published_at"] = planned
            # E3: 최초 공개 시각은 한 번만 스탬프(재공개해도 안 갱신) - 독자 표시용.
            # func.coalesce 대신 Python 값인 이유: 이 아래 두 커밋 경로 중 ORM setattr
            # 경로(:setattr(episode, field, value))는 SQL 표현식을 대입하면 SQLAlchemy가
            # 그대로 바인드 파라미터로 취급해 깨진다 - Core update().values()에서만
            # SQL 표현식이 안전하다. published_at과 동일하게 이미 로드된 episode
            # 인스턴스 값으로 판단(기존 코드와 같은 위험 감수 수준 - 아래 참고).
            if episode.first_published_at is None:
                changes["first_published_at"] = planned
        else:
            # 페이로드에 published_at이 동봉돼도 무시하고 항상 예약 해제. 동봉 값은
            # 대부분 관리자 폼의 stale 에코인데, 과거 시각이 남으면 E1 폴링이 내린
            # 회차를 다음 틱(60초)에 재공개한다(E1 계획 리뷰 Critical). 잡은 DB
            # 상태만으로 "예약"과 "수동 하차"를 구분할 수 없어 방어는 쓰기 경로
            # 몫이다. "내리면서 재예약"은 별도 요청으로.
            changes["published_at"] = None

    # 썸네일 공개 축소본(M2 D2). 원본 다운로드·변환은 DB write 전에 끝내되, 고정 공개
    # 키 upload는 stale 조건부 UPDATE가 행을 잡은 뒤에만 실행한다. 409 요청이 공개 객체를
    # 먼저 덮는 경로를 막고, upload 실패 시 아직 commit 전이라 DB를 rollback할 수 있다.
    old_thumbnail = episode.thumbnail
    new_thumbnail = changes.get("thumbnail", old_thumbnail)
    thumbnail_changed = new_thumbnail != old_thumbnail
    should_delete_public_thumb = (
        thumbnail_changed and new_thumbnail is None and old_thumbnail is not None
    )
    thumb_webp: bytes | None = None
    if thumbnail_changed and new_thumbnail is not None:
        page_bytes = await r2_service.download_bytes(new_thumbnail)
        thumb_webp = await convert_to_webp(page_bytes, target_width=THUMB_WIDTH)

    invariant_write = new_keys is not None or "content" in changes or "thumbnail" in changes
    if invariant_write or changes.get("draft") is not None:
        if new_keys is not None:
            changes["image_keys"] = new_keys
        conditions = [
            Episode.id == episode.id,
            func.jsonb_array_length(Episode.image_keys) == expected_len,
        ]
        if invariant_write:
            # content·thumbnail은 서로의 유효성 근거다. 둘 중 하나가 로드 뒤 바뀌었다면
            # stale 스냅샷으로 검증한 요청을 409로 거부해 불변식의 역순 경합을 닫는다.
            conditions.append(Episode.content == episode.content)
            conditions.append(
                Episode.thumbnail.is_(None)
                if old_thumbnail is None
                else Episode.thumbnail == old_thumbnail
            )
        if "content" in changes and "is_published" not in changes:
            # 위 409 가드의 원자 버전: 로드 시점엔 비공개였어도 커밋 순간 공개 상태면
            # (스케줄러 전환 race) 이 행이 매칭되지 않아 임시저장이 라이브를 못 덮는다.
            conditions.append(Episode.is_published.is_(False))
        result = await session.exec(
            update(Episode)
            .where(*conditions)
            .values(**changes)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            await session.rollback()
            raise EpisodeConflictError(_STALE_EPISODE)
        if thumb_webp is not None:
            try:
                await r2_service.upload_bytes(
                    r2_service.episode_thumb_key(episode.work_id, episode.id),
                    thumb_webp,
                    bucket=settings.r2_public_bucket,
                )
            except Exception:
                await session.rollback()
                raise
        await session.commit()
        # bulk UPDATE(synchronize_session=False)는 인메모리 객체를 안 맞춰주므로 재로드.
        await session.refresh(episode)
        if should_delete_public_thumb:
            # DB 커밋 성공 **후**에만 삭제(실패해도 무해한 미참조 파일로 남게).
            await r2_service.delete_object(
                r2_service.episode_thumb_key(episode.work_id, episode.id),
                bucket=settings.r2_public_bucket,
            )
        return episode

    for field, value in changes.items():
        setattr(episode, field, value)
    session.add(episode)
    await session.commit()
    if should_delete_public_thumb:
        await r2_service.delete_object(
            r2_service.episode_thumb_key(episode.work_id, episode.id),
            bucket=settings.r2_public_bucket,
        )
    return episode


async def soft_delete_episode(episode: Episode, session: AsyncSession) -> None:
    """회차 soft delete (#85). deleted_at 스탬프와 공개 해제를 한 UPDATE로 원자화한다.

    행을 남기는 이유(번호 폐기로 재작성, 2026-07-29): M3 purchases.episode_id가 ON DELETE
    절 없이(기본 RESTRICT) episodes(id)를 참조하도록 설계돼 있다(DB_SCHEMA §purchases) -
    구매·환불 기록이 걸린 회차는 하드 삭제가 애초에 불가능해진다. 되살리는 API는 없다.

    deleted_at IS NULL 조건부 UPDATE라 동시 삭제는 한쪽만 이긴다(rowcount 0 = 409).
    나눠 쓰면 "삭제됐는데 아직 공개"인 창이 생기는데, 그 사이 독자 요청 하나가
    통과하면 되돌릴 수 없다.

    공개 버킷의 썸네일 축소본은 DB 커밋 **후** 지운다(update_episode의 썸네일 해제와
    같은 순서·같은 이유 - 먼저 지웠다가 DB가 실패하면 DB가 없는 객체를 가리킨다).
    원고와 달리 이건 서명 없이 열리는 공개 객체라, 남기면 회차를 내린 뒤에도 URL을
    아는 사람에게 계속 서빙된다. 페이지 원본에서 다시 만들 수 있는 파생물이라 지워도
    복구 가능성은 줄지 않는다. image_keys의 원고는 건드리지 않는다(soft delete의 요점).
    """
    thumbnail = episode.thumbnail
    work_id = episode.work_id
    episode_id = episode.id

    result = await session.exec(
        update(Episode)
        .where(Episode.id == episode_id, Episode.deleted_at.is_(None))
        .values(deleted_at=func.now(), is_published=False, published_at=None)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise EpisodeConflictError(_STALE_EPISODE)
    await session.commit()

    if thumbnail is not None:
        try:
            await r2_service.delete_object(
                r2_service.episode_thumb_key(work_id, episode_id),
                bucket=settings.r2_public_bucket,
            )
        except Exception:
            # 삭제는 이미 커밋됐다. 여기서 예외를 올리면 "5xx인데 실제로는 삭제됨"이 되고,
            # 관리자가 재시도하면 404가 나와 상태를 오해한다. 남는 건 공개 축소본 하나뿐이라
            # (원고 아님) 실패를 로그로만 남기고 삭제 자체는 성공으로 응답한다.
            # update_episode의 같은 호출과 다른 처리인 이유: 거기선 커밋 뒤 응답할 본문이
            # 남아 있지만, 여기선 204라 되돌릴 것도 알릴 것도 없다.
            logger.warning(
                "episode_public_thumb_delete_failed",
                episode_id=str(episode_id),
                exc_info=True,
            )
