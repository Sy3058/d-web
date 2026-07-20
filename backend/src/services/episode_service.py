"""에피소드 서비스 (M1.5 D3, ADM-03).

구조 A(장당 업로드 + JSON 메타 분리 - 2026-07-10 council 검증 후 확정):
draft 생성이 이미지보다 먼저라 episode_no 충돌이 업로드 전에 발각되고,
이미지는 단건 append라 메모리·재시도·R2 미참조 파일(orphan)이 전부 1장 단위다.

표시 순서·구성의 진실은 F3 재설계(2026-07-15)로 **content 문서**로 이동했고,
image_keys는 업로드 매니페스트(이 회차가 소유한 R2 키 전량)다. 키 파일명은
uuid(순수 식별자, 순서 의미 없음) - 순번 파일명은 동시 업로드가 stale 스냅샷으로
같은 번호를 계산해 살아있는 객체를 덮어쓰는 구멍이라 리뷰에서 폐기(2026-07-10 리뷰 ①·⑦).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.content_doc import (
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

_DUPLICATE_EPISODE_NO = "이미 존재하는 회차 번호입니다"
_STALE_EPISODE = "회차가 다른 요청으로 먼저 변경되었습니다 - 새로고침 후 다시 시도하세요"


async def create_episode(work_id: uuid.UUID, data: EpisodeCreate, session: AsyncSession) -> Episode:
    """draft 생성(is_published=false, 빈 문서).

    episode_no 생략 = 해당 작품 max+1 자동 할당(F3 에디터의 "캔버스 먼저" 흐름 -
    작가는 발행 모달에서야 번호를 정한다). 동시 생성이 같은 max를 읽는 경합은
    UNIQUE(work_id, episode_no)가 최종 백스톱 - check-then-insert 경합은 SELECT
    선검사로 못 막고 DB 제약만이 단일 직렬화 권위다(C1 태그와 동일 계열).
    구조 A라 이 409는 이미지 업로드 전에 즉시 반환된다.

    is_free=True 명시: is_free는 content 파생 컬럼이고 빈 문서 = 무료가 정합
    (derive_is_free(EMPTY_DOC) == True). 모델 컬럼 기본값 false에 맡기면
    "내용 없는 draft가 유료"라는 모순 상태로 시작한다.
    """
    payload = data.model_dump()
    if payload["episode_no"] is None:
        result = await session.exec(
            select(func.coalesce(func.max(Episode.episode_no), 0)).where(Episode.work_id == work_id)
        )
        payload["episode_no"] = result.one() + 1
    episode = Episode(**payload, work_id=work_id, is_free=True)
    session.add(episode)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise EpisodeConflictError(_DUPLICATE_EPISODE_NO) from exc
    return episode


async def list_episodes(work_id: uuid.UUID, session: AsyncSession) -> Sequence[Episode]:
    result = await session.exec(
        select(Episode).where(Episode.work_id == work_id).order_by(Episode.episode_no)
    )
    return result.all()


async def get_episode(
    work_id: uuid.UUID, episode_id: uuid.UUID, session: AsyncSession
) -> Episode | None:
    """work 스코프 + soft-delete 확인 단건 조회.

    Work를 join해 deleted_at까지 한 쿼리로 거른다 - 안 거르면 삭제된 작품의
    에피소드에 업로드·수정·공개가 통과하는 비대칭이 생긴다(생성·목록은 404인데
    업로드·PUT은 200 - 2026-07-10 리뷰 ⑤).
    """
    result = await session.exec(
        select(Episode)
        .join(Work, Work.id == Episode.work_id)  # type: ignore[arg-type]
        .where(
            Episode.id == episode_id,
            Episode.work_id == work_id,
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
    세션에 dirty 변이가 남지 않는다(리뷰 ⑧). thumbnail은 최종 image_keys 기준
    검증(재배열과 같은 요청에 와도 정합), 정리로 선택 페이지가 제거되면 자동
    NULL(조회측이 첫 페이지 fallback).

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
    못 막는 역순 경합(content 저장 후 매니페스트 축소가 stale content를 재검증)은
    같은 버전 컬럼 후속에서 닫는다 - see #75.

    공개 시맨틱(리뷰 ③): true 전환 시 published_at이 요청에 없고 NULL·미래면
    now 스탬프(공개 회차는 항상 유효한 공개 시각 보유 - M2 정렬·partial 인덱스
    계약). false 전환 시 published_at은 페이로드와 무관하게 항상 NULL 초기화
    (E1 재공개 차단 - 재예약은 별도 요청). 공개 결과 상태는 본문에 유의미
    콘텐츠(글/이미지) 필요(빈 draft 공개·공개 회차 본문 전삭제 차단 - 리뷰 ④
    계승. 예약만 걸린 draft는 허용, E1이 공개 전환 시점에 재검사).
    """
    changes = data.model_dump(exclude_unset=True)
    new_keys: list[str] | None = changes.pop("image_keys", None)
    expected_len = len(episode.image_keys)

    if new_keys is not None:
        _validate_reorder(episode.image_keys, new_keys)
    final_keys = episode.image_keys if new_keys is None else new_keys

    final_content = changes.get("content", episode.content)
    if "content" in changes or new_keys is not None:
        validate_content(final_content, set(final_keys))
    if "content" in changes:
        if not has_meaningful_content(final_content):
            final_content = empty_doc()
            changes["content"] = final_content
        changes["is_free"] = derive_is_free(final_content)

    if "thumbnail" in changes:
        if changes["thumbnail"] is not None and changes["thumbnail"] not in final_keys:
            raise EpisodeValidationError("thumbnail은 이 회차에 업로드된 페이지 키여야 합니다")
    elif episode.thumbnail is not None and episode.thumbnail not in final_keys:
        changes["thumbnail"] = None

    final_published = changes.get("is_published", episode.is_published)
    if final_published and not has_meaningful_content(final_content):
        raise EpisodeValidationError("공개 회차에는 본문 내용(글 또는 이미지)이 필요합니다")
    if "is_published" in changes:
        if changes["is_published"]:
            planned = changes.get("published_at", episode.published_at)
            if planned is None or planned > datetime.now(UTC):
                changes["published_at"] = datetime.now(UTC)
        else:
            # 페이로드에 published_at이 동봉돼도 무시하고 항상 예약 해제. 동봉 값은
            # 대부분 관리자 폼의 stale 에코인데, 과거 시각이 남으면 E1 폴링이 내린
            # 회차를 다음 틱(60초)에 재공개한다(E1 계획 리뷰 Critical). 잡은 DB
            # 상태만으로 "예약"과 "수동 하차"를 구분할 수 없어 방어는 쓰기 경로
            # 몫이다. "내리면서 재예약"은 별도 요청으로.
            changes["published_at"] = None

    # 썸네일 공개 축소본(M2 D2) - 검증(raise 가능 구간)이 전부 끝난 뒤, DB 커밋 전에
    # 실행한다. old_thumbnail은 아래 두 커밋 분기 각각의 성공 직후 삭제 판단에 재사용.
    old_thumbnail = episode.thumbnail
    new_thumbnail = changes.get("thumbnail", old_thumbnail)
    thumbnail_changed = new_thumbnail != old_thumbnail
    should_delete_public_thumb = (
        thumbnail_changed and new_thumbnail is None and old_thumbnail is not None
    )
    if thumbnail_changed and new_thumbnail is not None:
        page_bytes = await r2_service.download_bytes(new_thumbnail)
        thumb_webp = await convert_to_webp(page_bytes, target_width=THUMB_WIDTH)
        await r2_service.upload_bytes(
            r2_service.episode_thumb_key(episode.work_id, episode.id),
            thumb_webp,
            bucket=settings.r2_public_bucket,
        )

    if new_keys is not None or "content" in changes:
        if new_keys is not None:
            changes["image_keys"] = new_keys
        try:
            result = await session.exec(
                update(Episode)
                .where(
                    Episode.id == episode.id,
                    func.jsonb_array_length(Episode.image_keys) == expected_len,
                )
                .values(**changes)
                .execution_options(synchronize_session=False)
            )
        except IntegrityError as exc:
            await session.rollback()
            raise EpisodeConflictError(_DUPLICATE_EPISODE_NO) from exc
        if result.rowcount != 1:
            await session.rollback()
            raise EpisodeConflictError(_STALE_EPISODE)
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
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise EpisodeConflictError(_DUPLICATE_EPISODE_NO) from exc
    if should_delete_public_thumb:
        await r2_service.delete_object(
            r2_service.episode_thumb_key(episode.work_id, episode.id),
            bucket=settings.r2_public_bucket,
        )
    return episode
