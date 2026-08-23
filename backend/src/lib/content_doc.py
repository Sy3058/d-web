"""에피소드 본문(TipTap/ProseMirror JSON 문서) 검증 (F3 재설계, 2026-07-15).

본문은 HTML이 아니라 **스키마 제한 JSON**으로 저장한다 - 노드·마크 화이트리스트가
곧 방어선이라 임의 태그·속성이 존재할 수 없고(XSS 원천 차단), 렌더러(admin TipTap
에디터, M2 뷰어 generateHTML)는 여기와 같은 화이트리스트 스키마로만 해석해야 한다.

- image 노드 attrs.key = R2 키(URL 아님). 이 회차 image_keys(업로드 매니페스트)의
  부분집합만 허용 - 임의 키 주입 차단(다른 회차·작품 원고 참조 금지).
- paywall 노드 = 유료 경계. **문서 최상위에만, 최대 1개.** 경계 이후 = 유료.
  미구매 독자 응답은 M3에서 이 경계 기준으로 서버가 잘라 반환한다(클라 숨김 금지).
- is_free는 이 문서에서 파생된다(경계 뒤 유의미 콘텐츠 없음 = 전체 무료) -
  목록·M2 무료구간 SQL용 비정규화 컬럼이고 직접 입력은 폐지됐다.
"""

from typing import Any

from src.lib.exceptions import EpisodeValidationError

# 에디터(admin)·M2 뷰어 렌더 스키마와 함께 지켜야 하는 단일 화이트리스트(툴바 미니멀).
ALLOWED_NODE_TYPES = frozenset(
    {"doc", "paragraph", "text", "hardBreak", "image", "paywall", "horizontalRule"}
)
_ALLOWED_DOC_FIELDS = frozenset({"type", "content"})
_ALLOWED_NODE_FIELDS: dict[str, frozenset[str]] = {
    "paragraph": frozenset({"type", "content"}),
    "text": frozenset({"type", "text", "marks"}),
    "hardBreak": frozenset({"type"}),
    "image": frozenset({"type", "attrs"}),
    "paywall": frozenset({"type"}),
    "horizontalRule": frozenset({"type"}),
}
# 자식(content)을 가질 수 있는 노드. text·이미지·경계·구분선 밑에 뭔가 달려오면 위조 문서다.
_PARENT_NODE_TYPES = frozenset({"paragraph"})
ALLOWED_MARK_TYPES = frozenset({"bold", "italic", "underline", "strike", "link"})
_ALLOWED_MARK_FIELDS: dict[str, frozenset[str]] = {
    "bold": frozenset({"type"}),
    "italic": frozenset({"type"}),
    "underline": frozenset({"type"}),
    "strike": frozenset({"type"}),
    "link": frozenset({"type", "attrs"}),
}
_ALLOWED_LINK_PREFIXES = ("http://", "https://")
# 노드·마크가 가질 수 있는 attrs 키(미등재 = attrs 불허). 임의 속성이 저장되면
# "화이트리스트가 곧 방어선"이 "렌더러가 버려주면 안전"으로 퇴화한다(리뷰 M1).
# ⚠️ TipTap 기본 Link 확장은 target/rel/class attr까지 직렬화한다 - 에디터(PR②)는
# href만 남기게 확장을 설정하고, rel/target은 렌더러가 강제 부여한다.
_ALLOWED_NODE_ATTRS: dict[str, frozenset[str]] = {"image": frozenset({"key"})}
_ALLOWED_MARK_ATTRS: dict[str, frozenset[str]] = {"link": frozenset({"href"})}

# DoS 방어 상한. JSONB 한 행에 들어가는 문서라 여유 있게 잡되 무한은 금지.
MAX_CONTENT_NODES = 3_000
MAX_CONTENT_TEXT_CHARS = 100_000
MAX_CONTENT_DEPTH = 20

# "전부 빈 문서"의 정규형. 스케줄러의 공개 가드가 SQL(jsonb_array_length(content->'content'))
# 만으로 "내용 없음"을 판별할 수 있도록, 유의미 노드가 하나도 없는 문서는 이걸로 접는다
# (빈 paragraph만 있는 문서를 그대로 두면 배열 길이 > 0이라 빈 회차가 예약 공개된다).
EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": []}


def empty_doc() -> dict[str, Any]:
    """EMPTY_DOC의 새 인스턴스(공유 dict 변이 방지)."""
    return {"type": "doc", "content": []}


class _Counters:
    __slots__ = ("nodes", "text_chars", "paywalls")

    def __init__(self) -> None:
        self.nodes = 0
        self.text_chars = 0
        self.paywalls = 0


def validate_content(doc: Any, allowed_image_keys: set[str]) -> None:
    """문서 구조·화이트리스트·상한·이미지 키 소유를 검증한다. 위반 = EpisodeValidationError."""
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise EpisodeValidationError("content는 type=doc 문서여야 합니다")
    if not set(doc) <= _ALLOWED_DOC_FIELDS:
        raise EpisodeValidationError("content 문서에 허용되지 않는 필드가 있습니다")
    top = doc.get("content", [])
    if not isinstance(top, list):
        raise EpisodeValidationError("content.content는 노드 배열이어야 합니다")
    counters = _Counters()
    for node in top:
        _validate_node(node, allowed_image_keys, counters, depth=1)


def _validate_node(
    node: Any, allowed_image_keys: set[str], counters: _Counters, depth: int
) -> None:
    if depth > MAX_CONTENT_DEPTH:
        raise EpisodeValidationError(f"content 중첩 깊이가 {MAX_CONTENT_DEPTH}를 넘습니다")
    if not isinstance(node, dict):
        raise EpisodeValidationError("content 노드는 객체여야 합니다")

    node_type = node.get("type")
    if not isinstance(node_type, str) or node_type not in ALLOWED_NODE_TYPES or node_type == "doc":
        raise EpisodeValidationError(f"허용되지 않는 노드 타입입니다: {node_type!r}")
    if not set(node) <= _ALLOWED_NODE_FIELDS[node_type]:
        raise EpisodeValidationError(f"{node_type} 노드에 허용되지 않는 필드가 있습니다")

    counters.nodes += 1
    if counters.nodes > MAX_CONTENT_NODES:
        raise EpisodeValidationError(f"content 노드 수가 {MAX_CONTENT_NODES}를 넘습니다")

    attrs = node.get("attrs")
    if "attrs" in node:
        if not isinstance(attrs, dict):
            raise EpisodeValidationError("노드 attrs는 객체여야 합니다")
        if not set(attrs) <= _ALLOWED_NODE_ATTRS.get(node_type, frozenset()):
            raise EpisodeValidationError(f"{node_type} 노드에 허용되지 않는 속성이 있습니다")

    if node_type == "paywall":
        if depth != 1:
            raise EpisodeValidationError("유료 경계는 문서 최상위에만 둘 수 있습니다")
        counters.paywalls += 1
        if counters.paywalls > 1:
            raise EpisodeValidationError("유료 경계는 하나만 둘 수 있습니다")

    if node_type == "text":
        text = node.get("text")
        if not isinstance(text, str) or not text:
            raise EpisodeValidationError("text 노드에는 문자열 text가 필요합니다")
        counters.text_chars += len(text)
        if counters.text_chars > MAX_CONTENT_TEXT_CHARS:
            raise EpisodeValidationError(f"본문 글자 수가 {MAX_CONTENT_TEXT_CHARS}를 넘습니다")
        if "marks" in node:
            _validate_marks(node["marks"])

    if node_type == "image":
        key = attrs.get("key") if isinstance(attrs, dict) else None
        if not isinstance(key, str) or key not in allowed_image_keys:
            raise EpisodeValidationError("이 회차에 업로드된 이미지 키가 아닙니다")

    if "content" in node:
        children = node["content"]
        if node_type not in _PARENT_NODE_TYPES:
            raise EpisodeValidationError(f"{node_type} 노드는 자식을 가질 수 없습니다")
        if not isinstance(children, list):
            raise EpisodeValidationError("노드 content는 배열이어야 합니다")
        for child in children:
            _validate_node(child, allowed_image_keys, counters, depth + 1)


def _validate_marks(marks: Any) -> None:
    if not isinstance(marks, list):
        raise EpisodeValidationError("marks는 배열이어야 합니다")
    for mark in marks:
        if not isinstance(mark, dict):
            raise EpisodeValidationError("mark는 객체여야 합니다")
        mark_type = mark.get("type")
        if not isinstance(mark_type, str) or mark_type not in ALLOWED_MARK_TYPES:
            raise EpisodeValidationError(f"허용되지 않는 마크입니다: {mark_type!r}")
        if not set(mark) <= _ALLOWED_MARK_FIELDS[mark_type]:
            raise EpisodeValidationError(f"{mark_type} 마크에 허용되지 않는 필드가 있습니다")
        attrs = mark.get("attrs")
        if "attrs" in mark:
            if not isinstance(attrs, dict):
                raise EpisodeValidationError("마크 attrs는 객체여야 합니다")
            if not set(attrs) <= _ALLOWED_MARK_ATTRS.get(mark_type, frozenset()):
                raise EpisodeValidationError(f"{mark_type} 마크에 허용되지 않는 속성이 있습니다")
        if mark_type == "link":
            href = (attrs or {}).get("href")
            # javascript: 등 스킴 주입 차단 - 절대 URL http(s)만
            if not isinstance(href, str) or not href.startswith(_ALLOWED_LINK_PREFIXES):
                raise EpisodeValidationError("링크는 http(s) URL만 허용됩니다")


def _is_meaningful(node: Any) -> bool:
    """독자에게 보이는 내용이 있는 노드인가 (이미지, 공백 아닌 텍스트)."""
    stack = [node]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        if current.get("type") == "image":
            return True
        if current.get("type") == "text":
            text = current.get("text")
            if isinstance(text, str) and text.strip():
                return True
        children = current.get("content")
        if isinstance(children, list):
            stack.extend(children)
    return False


def has_meaningful_content(doc: Any) -> bool:
    """공개 가능 여부의 기준 - 빈 paragraph·구분선·경계만 있는 문서는 내용 없음."""
    if not isinstance(doc, dict):
        return False
    return any(_is_meaningful(node) for node in doc.get("content") or [])


def content_image_keys(doc: Any) -> set[str]:
    """본문이 실제로 참조하는 image key 집합을 중첩 깊이와 무관하게 반환한다.

    쓰기 경로에서는 validate_content 뒤에 호출하지만, 과거 데이터 감사와 thumbnail-only
    요청은 저장된 JSON을 직접 읽으므로 비정상 노드는 무시하는 fail-closed 추출기다.
    """
    keys: set[str] = set()
    stack = [doc]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        if current.get("type") == "image":
            attrs = current.get("attrs")
            key = attrs.get("key") if isinstance(attrs, dict) else None
            if isinstance(key, str):
                keys.add(key)
        children = current.get("content")
        if isinstance(children, list):
            stack.extend(children)
    return keys


def derive_is_free(doc: dict[str, Any]) -> bool:
    """경계(paywall) 뒤에 유의미 콘텐츠가 없으면 전체 무료.

    경계 없음 = 무료(에디터 기본 - 작가가 상자를 위로 옮겨야 유료가 된다,
    DECISIONS "가격 기본값 무료" 정합). 경계가 맨 앞 = 미리보기 0의 전체 유료.
    """
    top = doc.get("content") or []
    for index, node in enumerate(top):
        if isinstance(node, dict) and node.get("type") == "paywall":
            return not any(_is_meaningful(rest) for rest in top[index + 1 :])
    return True


def split_at_paywall(doc: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """무료 구간 문서와 유료 구간 존재 여부를 반환한다 (M2 B2 독자 응답용).

    반환: (경계 이전 노드만 담은 doc, has_paid_part)

    ⚠️ episodes.is_free를 보지 않고 **항상** 같은 경로로 자른다. is_free는 목록 SQL용
    파생 컬럼(models/work.py)이고 진실은 이 문서다 - "is_free면 절단 생략"으로 분기하면
    컬럼이 문서와 어긋나는 순간(쓰기 경로 버그·과거 데이터·수동 UPDATE) 유료 구간이
    통째로 나간다. 분기가 없으면 컬럼이 틀려도 피해는 목록 배지 오표시에 그친다.
    파생 컬럼은 필터·표시용이고 보안 결정은 원본을 본다.

    has_paid_part는 derive_is_free와 **같은 기준**(_is_meaningful)이어야 한다. 경계 뒤에
    빈 문단만 남은 문서를 "유료 있음"으로 잡으면 무료 회차에 잠금 UI가 뜬다.
    """
    top = doc.get("content") or []
    for index, node in enumerate(top):
        if isinstance(node, dict) and node.get("type") == "paywall":
            # 경계 노드 자체는 응답에 넣지 않는다(top[:index+1]이 아닌 이유) - 잠금 표시는
            # has_paid_part가 담당하므로, 노드까지 실리면 뷰어가 본문 안에 한 번·플래그로
            # 또 한 번 그린다.
            free_nodes = top[:index]
            has_paid_part = any(_is_meaningful(rest) for rest in top[index + 1 :])
            return {"type": "doc", "content": free_nodes}, has_paid_part
    return {"type": "doc", "content": list(top)}, False
