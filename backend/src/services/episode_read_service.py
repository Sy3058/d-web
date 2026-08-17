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

_LEAF_NODE_TYPES = frozenset({"hardBreak", "horizontalRule"})
_MARK_TYPES_WITHOUT_ATTRS = frozenset({"bold", "italic", "underline", "strike"})
_SAFE_LINK_PREFIXES = ("http://", "https://")


class _ProjectionStats:
    __slots__ = (
        "dropped_images",
        "dropped_marks",
        "dropped_nodes",
        "seen_nodes",
        "stripped_fields",
        "text_chars",
    )

    def __init__(self) -> None:
        self.dropped_images = 0
        self.dropped_marks = 0
        self.dropped_nodes = 0
        self.seen_nodes = 0
        self.stripped_fields = 0
        self.text_chars = 0


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


def _project_safe_marks(marks: Any, stats: _ProjectionStats) -> list[dict[str, Any]]:
    """저장 mark에서 공개 가능한 필드만 새 객체로 투영한다."""
    if not isinstance(marks, list):
        stats.dropped_marks += 1
        return []

    projected: list[dict[str, Any]] = []
    for mark in marks:
        if not isinstance(mark, dict):
            stats.dropped_marks += 1
            continue
        mark_type = mark.get("type")
        if not isinstance(mark_type, str):
            stats.dropped_marks += 1
            continue
        if mark_type in _MARK_TYPES_WITHOUT_ATTRS:
            stats.stripped_fields += len(set(mark) - {"type"})
            projected.append({"type": mark_type})
            continue
        if mark_type != "link":
            stats.dropped_marks += 1
            continue

        attrs = mark.get("attrs")
        href = attrs.get("href") if isinstance(attrs, dict) else None
        if not isinstance(href, str) or not href.startswith(_SAFE_LINK_PREFIXES):
            stats.dropped_marks += 1
            continue
        stats.stripped_fields += len(set(mark) - {"type", "attrs"})
        stats.stripped_fields += len(set(attrs) - {"href"})
        projected.append({"type": "link", "attrs": {"href": href}})
    return projected


def _project_safe_nodes(
    nodes: list[Any], stats: _ProjectionStats, *, depth: int = 1
) -> list[dict[str, Any]]:
    """오염된 저장 노드에서도 공개 가능한 저장 형태만 새 트리로 투영한다.

    image key는 아직 서버 내부에만 남긴다. 이 결과에서만 키를 수집해야 leaf의 불법
    content나 알 수 없는 노드 아래에 숨은 키가 presign 대상에 들어가지 않는다.
    """
    if depth > content_doc.MAX_CONTENT_DEPTH:
        stats.dropped_nodes += len(nodes)
        return []

    projected: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        if stats.seen_nodes >= content_doc.MAX_CONTENT_NODES:
            stats.dropped_nodes += len(nodes) - index
            break
        stats.seen_nodes += 1

        if not isinstance(node, dict):
            stats.dropped_nodes += 1
            continue

        node_type = node.get("type")
        if not isinstance(node_type, str):
            stats.dropped_nodes += 1
            continue
        if node_type == "paragraph":
            safe_node: dict[str, Any] = {"type": "paragraph"}
            stats.stripped_fields += len(set(node) - {"type", "content"})
            if "content" in node:
                children = node["content"]
                if not isinstance(children, list):
                    stats.dropped_nodes += 1
                    continue
                safe_node["content"] = _project_safe_nodes(children, stats, depth=depth + 1)
            projected.append(safe_node)
            continue

        if node_type == "text":
            text = node.get("text")
            if not isinstance(text, str) or not text:
                stats.dropped_nodes += 1
                continue
            if stats.text_chars + len(text) > content_doc.MAX_CONTENT_TEXT_CHARS:
                stats.dropped_nodes += 1
                continue
            stats.text_chars += len(text)
            safe_node = {"type": "text", "text": text}
            stats.stripped_fields += len(set(node) - {"type", "text", "marks"})
            if "marks" in node:
                safe_node["marks"] = _project_safe_marks(node["marks"], stats)
            projected.append(safe_node)
            continue

        if node_type in _LEAF_NODE_TYPES:
            stats.stripped_fields += len(set(node) - {"type"})
            projected.append({"type": node_type})
            continue

        if node_type == "image":
            attrs = node.get("attrs")
            key = attrs.get("key") if isinstance(attrs, dict) else None
            if not isinstance(key, str):
                stats.dropped_images += 1
                continue
            stats.stripped_fields += len(set(node) - {"type", "attrs"})
            stats.stripped_fields += len(set(attrs) - {"key"})
            projected.append({"type": "image", "attrs": {"key": key}})
            continue

        # doc은 루트 전용이고 paywall은 최상위 절단에서 제거되어야 한다. 중첩되거나
        # 알 수 없는 타입은 의미를 추측하지 않고 노드 단위로 닫는다.
        stats.dropped_nodes += 1
    return projected


def _iter_image_keys(nodes: list[dict[str, Any]]) -> Iterator[str]:
    """안전하게 투영된 노드 트리에서 image key를 등장 순서대로 훑는다."""
    for node in nodes:
        if node.get("type") == "image":
            key = (node.get("attrs") or {}).get("key")
            if isinstance(key, str):
                yield key
            continue
        children = node.get("content")
        if isinstance(children, list):
            yield from _iter_image_keys(children)


def _project_public_nodes(
    nodes: list[dict[str, Any]], url_by_key: dict[str, str], stats: _ProjectionStats
) -> list[dict[str, Any]]:
    """안전한 저장 형태를 공개 응답 형태로 새로 조립한다."""
    rebuilt: list[dict[str, Any]] = []
    for node in nodes:
        node_type = node["type"]
        if node_type == "image":
            key = node["attrs"]["key"]
            url = url_by_key.get(key)
            if url is None:
                stats.dropped_images += 1
                continue
            rebuilt.append({"type": "image", "attrs": {"src": url}})
            continue

        if node_type == "paragraph":
            public_node: dict[str, Any] = {"type": "paragraph"}
            if "content" in node:
                public_node["content"] = _project_public_nodes(node["content"], url_by_key, stats)
            rebuilt.append(public_node)
            continue

        if node_type == "text":
            public_node = {"type": "text", "text": node["text"]}
            if "marks" in node:
                public_marks: list[dict[str, Any]] = []
                for mark in node["marks"]:
                    if mark["type"] == "link":
                        public_marks.append(
                            {"type": "link", "attrs": {"href": mark["attrs"]["href"]}}
                        )
                    else:
                        public_marks.append({"type": mark["type"]})
                public_node["marks"] = public_marks
            rebuilt.append(public_node)
            continue

        rebuilt.append({"type": node_type})
    return rebuilt


async def _substitute_image_urls(
    doc: dict[str, Any],
) -> tuple[dict[str, Any], _ProjectionStats]:
    """무료 문서를 안전하게 투영하고 image key를 presigned URL로 치환한다."""
    stats = _ProjectionStats()
    raw_nodes = doc.get("content") or []
    nodes = _project_safe_nodes(raw_nodes, stats)
    # dict.fromkeys = 순서 보존 중복 제거. 같은 이미지를 두 번 쓴 문서에서 서명을
    # 두 번 발급할 이유가 없다.
    keys = list(dict.fromkeys(_iter_image_keys(nodes)))
    urls = await r2_service.presign_get_urls(keys)
    # strict=True: presign_get_urls의 "같은 순서·같은 길이" 계약이 깨지면 조용히
    # 짝이 밀린 URL을 내보내는 대신 여기서 터진다.
    url_by_key = dict(zip(keys, urls, strict=True))
    public_nodes = _project_public_nodes(nodes, url_by_key, stats)
    return {"type": "doc", "content": public_nodes}, stats


async def get_free_content(episode_id: uuid.UUID, session: AsyncSession) -> EpisodeContent | None:
    """무료 구간 본문. 노출 불가한 회차면 None(라우터가 404로 매핑)."""
    row = await _fetch_public_episode(episode_id, session)
    if row is None:
        return None
    found_id, content = row

    if (
        not isinstance(content, dict)
        or content.get("type") != "doc"
        or ("content" in content and not isinstance(content["content"], list))
    ):
        logger.warning(
            "episode_content_document_dropped",
            episode_id=str(found_id),
            dropped_count=1,
        )
        return EpisodeContent(
            episode_id=found_id,
            content=content_doc.empty_doc(),
            # 문서 의미를 해석할 수 없을 때 "전부 무료"로 열지 않는다.
            has_paid_part=True,
        )

    # ⚠️ 순서 고정: 절단이 먼저다. 치환을 먼저 하면 _substitute_image_urls가 문서 전체를
    # 훑어 **유료 구간 키에도 서명이 발급**된다. 그 뒤에 잘라내면 최종 응답은 멀쩡해 보여서
    # 응답 검사로는 잡히지 않는다 - tests/test_episode_content.py의
    # test_paid_section_keys_are_never_signed(presign 호출 인자 검사)가 유일한 방어선이다.
    free_doc, has_paid_part = content_doc.split_at_paywall(content)
    free_doc, stats = await _substitute_image_urls(free_doc)

    if stats.dropped_images:
        # 독자에겐 200이 나가지만 이미지가 빠진 본문이다. 로그가 없으면 "그림이 안 나온다"는
        # 신고가 들어올 때까지 아무도 모른다(키는 개인정보가 아니나 개수만 남긴다).
        logger.warning(
            "episode_content_image_dropped",
            episode_id=str(found_id),
            dropped_count=stats.dropped_images,
        )
    if stats.dropped_nodes or stats.dropped_marks or stats.stripped_fields:
        # 오염값 자체는 원고 키·본문일 수 있어 기록하지 않는다. 어떤 데이터가 정리됐는지는
        # 개수만으로 관측하고, 공개 응답은 정상 형제 노드를 유지한 채 fail-closed한다.
        logger.warning(
            "episode_content_invalid_part_sanitized",
            episode_id=str(found_id),
            dropped_node_count=stats.dropped_nodes,
            dropped_mark_count=stats.dropped_marks,
            stripped_field_count=stats.stripped_fields,
        )

    return EpisodeContent(
        episode_id=found_id,
        content=free_doc,
        has_paid_part=has_paid_part,
    )
