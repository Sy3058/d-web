"""무료 구간 회차 본문 조회 서비스 (M2 그룹 B2 - 보안 그룹).

독자에게 회차 본문을 내보내는 유일한 경로. 유료 구간(글·이미지)·미공개 회차·숨긴
작품의 회차·원본 R2 키가 응답에 실리지 않게 막는 방어선이 전부 이 모듈에 있다.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib import content_doc
from src.models.work import Episode, Work
from src.schemas.viewer import EpisodeContent
from src.services import catalog_service, r2_service

logger = structlog.get_logger(__name__)


async def _fetch_public_episode(
    episode_id: uuid.UUID, session: AsyncSession
) -> tuple[uuid.UUID, dict[str, Any]] | None:
    """독자에게 노출 가능한 회차의 (id, content) (회차 공개 + 소속 작품이 공개·미삭제).

    엔티티가 아니라 두 컬럼만 읽는다. Episode를 통째로 로딩하면 읽기 경로에서 쓰지 않는
    image_keys(회차당 수십 개 키가 담긴 JSONB)가 뷰어 진입마다 실려오고, defer로 지연시키면
    나중에 누가 그 인스턴스의 image_keys를 건드렸을 때 async 밖 lazy load가 걸려
    MissingGreenlet으로 죽는다(models/work.py가 Work.episode_count에 대해 경고하는 함정).
    """
    result = await session.exec(
        select(Episode.id, Episode.content)
        .join(Work, Work.id == Episode.work_id)
        .where(
            Episode.id == episode_id,
            # 회차 자신의 공개·미삭제(#85). 회차만 보는 것으로는 부족하다 - 아래 작품
            # 필터가 같이 있어야 한다.
            *catalog_service.public_episode_filters(),
            # ⚠️ 작품을 숨기거나(is_published=false) soft delete해도 **회차 행은 그대로
            # 남으므로**, 회차 ID를 아는 사람이 직접 접근하면 내려간 작품이 계속 읽힌다.
            # admin episode_service.get_episode가 작품의 deleted_at만 보고 is_published는
            # 안 보는 건 관리자가 비공개 작품도 봐야 해서고, 그 패턴을 독자 경로로
            # 복사하면 안 된다(public_work_filters docstring 경고).
            *catalog_service.public_work_filters(),
        )
    )
    return result.first()


def _iter_image_keys(nodes: list[Any]) -> Iterator[str]:
    """문서 노드 트리에서 image 노드의 R2 키를 등장 순서대로 훑는다."""
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") == "image":
            key = (node.get("attrs") or {}).get("key")
            if isinstance(key, str):
                yield key
        children = node.get("content")
        if isinstance(children, list):
            # image는 화이트리스트상 자식을 못 갖지만 paragraph 안에 중첩될 수 있어
            # 최상위만 훑으면 놓친다(content_doc._PARENT_NODE_TYPES).
            yield from _iter_image_keys(children)


def _replace_image_keys(
    nodes: list[Any], url_by_key: dict[str, str], dropped: list[Any]
) -> list[Any]:
    """image 노드의 attrs를 presigned URL로 교체한 새 노드 트리를 만든다.

    서명 URL을 못 만든 image는 버리고 dropped에 쌓는다 - 호출자가 그 사실을 로그로
    남길 수 있어야 한다(조용한 콘텐츠 유실 방지).
    """
    rebuilt: list[Any] = []
    for node in nodes:
        if not isinstance(node, dict):
            rebuilt.append(node)
            continue
        # 제자리 수정 금지 - split_at_paywall은 노드 dict를 새로 만들지 않고 슬라이스로
        # 공유하므로, 여기서 고치면 세션이 들고 있는 ORM 인스턴스의 content가 오염된다.
        # 이후 누가 이 경로에 flush를 유발하는 코드를 넣으면 만료되는 presigned URL이
        # 원고 키 자리에 영구 저장된다. 재조립이면 그 가능성 자체가 없다.
        new_node = dict(node)
        if node.get("type") == "image":
            key = (node.get("attrs") or {}).get("key")
            url = url_by_key.get(key) if isinstance(key, str) else None
            if url is None:
                # 서명 URL을 만들 수 없는 image는 노드째 버린다. 정상 문서에선 일어나지
                # 않지만(쓰기 경로가 validate_content를 탄다), 수동 DB 편집·마이그레이션으로
                # attrs 없는 노드가 생겼을 때 공개 읽기 경로가 500으로 죽지 않게 한다.
                # 원본 키를 남기거나 빈 src를 내보내는 선택지는 유출·깨진 렌더라 배제.
                dropped.append(key)
                continue
            # attrs를 통째로 교체한다(src 추가가 아니라) - key를 남기면 원본 R2 키가
            # 응답에 그대로 실린다.
            new_node["attrs"] = {"src": url}
        children = node.get("content")
        if isinstance(children, list):
            new_node["content"] = _replace_image_keys(children, url_by_key, dropped)
        rebuilt.append(new_node)
    return rebuilt


async def _substitute_image_urls(doc: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    """문서 안 image 키를 presigned GET URL로 치환한 (새 문서, 폐기된 키 목록)."""
    nodes = doc.get("content") or []
    # dict.fromkeys = 순서 보존 중복 제거. 같은 이미지를 두 번 쓴 문서에서 서명을
    # 두 번 발급할 이유가 없다.
    keys = list(dict.fromkeys(_iter_image_keys(nodes)))
    urls = await r2_service.presign_get_urls(keys)
    # strict=True: presign_get_urls의 "같은 순서·같은 길이" 계약이 깨지면 조용히
    # 짝이 밀린 URL을 내보내는 대신 여기서 터진다.
    url_by_key = dict(zip(keys, urls, strict=True))
    dropped: list[Any] = []
    return {**doc, "content": _replace_image_keys(nodes, url_by_key, dropped)}, dropped


async def get_free_content(episode_id: uuid.UUID, session: AsyncSession) -> EpisodeContent | None:
    """무료 구간 본문. 노출 불가한 회차면 None(라우터가 404로 매핑)."""
    row = await _fetch_public_episode(episode_id, session)
    if row is None:
        return None
    found_id, content = row

    # ⚠️ 순서 고정: 절단이 먼저다. 치환을 먼저 하면 _substitute_image_urls가 문서 전체를
    # 훑어 **유료 구간 키에도 서명이 발급**된다. 그 뒤에 잘라내면 최종 응답은 멀쩡해 보여서
    # 응답 검사로는 잡히지 않는다 - tests/test_episode_content.py의
    # test_paid_section_keys_are_never_signed(presign 호출 인자 검사)가 유일한 방어선이다.
    free_doc, has_paid_part = content_doc.split_at_paywall(content)
    free_doc, dropped = await _substitute_image_urls(free_doc)

    if dropped:
        # 독자에겐 200이 나가지만 이미지가 빠진 본문이다. 로그가 없으면 "그림이 안 나온다"는
        # 신고가 들어올 때까지 아무도 모른다(키는 개인정보가 아니나 개수만 남긴다).
        logger.warning(
            "episode_content_image_dropped",
            episode_id=str(found_id),
            dropped_count=len(dropped),
        )

    return EpisodeContent(
        episode_id=found_id,
        content=free_doc,
        has_paid_part=has_paid_part,
    )
