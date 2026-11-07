"""인가된 범위의 본문만 안전하게 투영·서명하고 전문 발급을 확정한다."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import update
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib import content_doc
from src.lib.exceptions import EpisodeAccessConflictError
from src.models.payment import Purchase, PurchaseStatus
from src.schemas.viewer import EpisodeContent
from src.services import episode_access_service, r2_service
from src.services.episode_access_service import EpisodeAccessScope, EpisodeAccessSnapshot

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
    """인가된 문서를 안전하게 투영하고 image key를 presigned URL로 치환한다."""
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


async def _confirm_full_issue(
    episode_id: uuid.UUID,
    user_id: uuid.UUID,
    snapshot: EpisodeAccessSnapshot,
    session: AsyncSession,
) -> None:
    """presign 성공 후 동일 구매 행에서 환불과 첫 발급의 단일 승자를 정한다."""
    eligible = episode_access_service.active_purchase_query(user_id).where(
        Purchase.id == snapshot.access.purchase_id,
        Purchase.episode_id == episode_id,
    )
    if snapshot.first_viewed_at is not None:
        if (await session.exec(eligible)).first() is None:
            raise EpisodeAccessConflictError
        return

    issued_id = (
        await session.exec(
            update(Purchase)
            .where(
                Purchase.id.in_(eligible),
                Purchase.status == PurchaseStatus.ACTIVE,
                Purchase.first_viewed_at.is_(None),
            )
            .values(first_viewed_at=datetime.now(UTC))
            .returning(Purchase.id)
            .execution_options(synchronize_session=False)
        )
    ).first()
    if issued_id is None:
        # 다른 첫 발급이 먼저 끝났더라도 재열람으로 우회하지 않는다.
        raise EpisodeAccessConflictError
    await session.commit()


async def get_content(
    episode_id: uuid.UUID, session: AsyncSession, *, user_id: uuid.UUID | None = None
) -> EpisodeContent | None:
    """resolver와 동일한 문서 스냅샷을 투영한다. 노출 불가면 None(404)."""
    snapshot = await episode_access_service.load_episode_access(user_id, episode_id, session)
    scope = snapshot.access.scope
    if scope == EpisodeAccessScope.UNAVAILABLE:
        return None
    content = snapshot.content

    if (
        not isinstance(content, dict)
        or content.get("type") != "doc"
        or ("content" in content and not isinstance(content["content"], list))
    ):
        logger.warning(
            "episode_content_document_dropped",
            episode_id=str(episode_id),
            dropped_count=1,
        )
        return EpisodeContent(
            episode_id=episode_id,
            access_scope="preview",
            content=content_doc.empty_doc(),
            # 문서 의미를 해석할 수 없을 때 "전부 무료"로 열지 않는다.
            has_paid_part=True,
        )

    # ⚠️ 순서 고정: 절단이 먼저다. 치환을 먼저 하면 _substitute_image_urls가 문서 전체를
    # 훑어 **유료 구간 키에도 서명이 발급**된다. 그 뒤에 잘라내면 최종 응답은 멀쩡해 보여서
    # 응답 검사로는 잡히지 않는다 - tests/test_episode_content.py의
    # test_paid_section_keys_are_never_signed(presign 호출 인자 검사)가 유일한 방어선이다.
    if scope == EpisodeAccessScope.FULL:
        allowed_doc = {
            "type": "doc",
            "content": [node for node in content.get("content", []) if node["type"] != "paywall"],
        }
        has_paid_part = False
    else:
        allowed_doc, has_paid_part = content_doc.split_at_paywall(content)
    public_doc, stats = await _substitute_image_urls(allowed_doc)

    if stats.dropped_images:
        # 독자에겐 200이 나가지만 이미지가 빠진 본문이다. 로그가 없으면 "그림이 안 나온다"는
        # 신고가 들어올 때까지 아무도 모른다(키는 개인정보가 아니나 개수만 남긴다).
        logger.warning(
            "episode_content_image_dropped",
            episode_id=str(episode_id),
            dropped_count=stats.dropped_images,
        )
    if stats.dropped_nodes or stats.dropped_marks or stats.stripped_fields:
        # 오염값 자체는 원고 키·본문일 수 있어 기록하지 않는다. 어떤 데이터가 정리됐는지는
        # 개수만으로 관측하고, 공개 응답은 정상 형제 노드를 유지한 채 fail-closed한다.
        logger.warning(
            "episode_content_invalid_part_sanitized",
            episode_id=str(episode_id),
            dropped_node_count=stats.dropped_nodes,
            dropped_mark_count=stats.dropped_marks,
            stripped_field_count=stats.stripped_fields,
        )

    if snapshot.access.purchase_id is not None:
        await _confirm_full_issue(episode_id, user_id, snapshot, session)

    return EpisodeContent(
        episode_id=episode_id,
        access_scope=scope.value,
        content=public_doc,
        has_paid_part=has_paid_part,
    )
