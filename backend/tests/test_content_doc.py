"""본문 문서 검증기(lib/content_doc) 단위 테스트 (F3 재설계, 2026-07-15).

DB 불필요한 순수 함수 검증. API 경유 통합 계약(422 매핑, is_free 저장)은
test_admin_episodes.py의 "PUT content" 섹션이 담당한다.
"""

import pytest

from src.lib.content_doc import (
    MAX_CONTENT_DEPTH,
    MAX_CONTENT_NODES,
    MAX_CONTENT_TEXT_CHARS,
    derive_is_free,
    empty_doc,
    has_meaningful_content,
    validate_content,
)
from src.lib.exceptions import EpisodeValidationError

KEY = "works/w/episodes/e/page.webp"


def _doc(*nodes: dict) -> dict:
    return {"type": "doc", "content": list(nodes)}


def _para(text: str, marks: list[dict] | None = None) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks is not None:
        node["marks"] = marks
    return {"type": "paragraph", "content": [node]}


def _img(key: str = KEY) -> dict:
    return {"type": "image", "attrs": {"key": key}}


_PAYWALL = {"type": "paywall"}


# ---------------------------------------------------------------------------
# validate_content: 구조·화이트리스트
# ---------------------------------------------------------------------------


def test_valid_document_passes():
    doc = _doc(
        _para("무료 분량", marks=[{"type": "bold"}]),
        _img(),
        {"type": "horizontalRule"},
        _PAYWALL,
        _para("유료 분량"),
    )
    validate_content(doc, {KEY})  # raise 없음 = 통과


def test_root_must_be_doc():
    with pytest.raises(EpisodeValidationError):
        validate_content({"type": "paragraph", "content": []}, set())
    with pytest.raises(EpisodeValidationError):
        validate_content("not a dict", set())


def test_unknown_node_type_rejected():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "iframe"}), set())


def test_nested_doc_rejected():
    # doc은 루트 전용 - 자식으로 숨어 들어오면 위조 문서.
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "doc", "content": []}), set())


def test_leaf_node_cannot_have_children():
    smuggled = {"type": "image", "attrs": {"key": KEY}, "content": [{"type": "text", "text": "x"}]}
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(smuggled), {KEY})


def test_unknown_mark_rejected():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=[{"type": "textStyle"}])), set())


def test_marks_only_on_text_nodes():
    # 리뷰 M1(a): 비-text 노드에 link 마크를 실으면 href 스킴 검사를 우회했다.
    node = {
        "type": "paragraph",
        "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}],
        "content": [{"type": "text", "text": "x"}],
    }
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(node), set())


def test_node_attrs_whitelist():
    # 리뷰 M1(b): 임의 속성이 저장되면 화이트리스트 방어선이 렌더러 신뢰로 퇴화한다.
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "paragraph", "attrs": {"onclick": "x"}}), set())
    smuggled = {"type": "image", "attrs": {"key": KEY, "onerror": "alert(1)"}}
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(smuggled), {KEY})


def test_mark_attrs_whitelist():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=[{"type": "bold", "attrs": {"style": "x"}}])), set())
    # link는 href만 - TipTap 기본 확장의 target/rel/class도 에디터(PR②)에서 제거한다.
    extra = [{"type": "link", "attrs": {"href": "https://example.com", "target": "_blank"}}]
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=extra)), set())


# ---------------------------------------------------------------------------
# validate_content: paywall 규칙
# ---------------------------------------------------------------------------


def test_two_paywalls_rejected():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_PAYWALL, _para("x"), _PAYWALL), set())


def test_nested_paywall_rejected():
    # 최상위 전용 - paragraph 안에 숨긴 경계는 서버 절단(M3) 기준을 흐린다.
    nested = {"type": "paragraph", "content": [dict(_PAYWALL)]}
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(nested), set())


# ---------------------------------------------------------------------------
# validate_content: 이미지 키 소유 / 링크 스킴
# ---------------------------------------------------------------------------


def test_image_key_must_be_owned():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_img("works/other/steal.webp")), {KEY})


def test_image_without_key_rejected():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "image", "attrs": {}}), {KEY})


@pytest.mark.parametrize(
    "href", ["javascript:alert(1)", "data:text/html;base64,x", "ftp://x", "//evil.example", 123]
)
def test_link_href_scheme_whitelist(href):
    marks = [{"type": "link", "attrs": {"href": href}}]
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=marks)), set())


def test_https_link_passes():
    marks = [{"type": "link", "attrs": {"href": "https://example.com/post"}}]
    validate_content(_doc(_para("x", marks=marks)), set())


# ---------------------------------------------------------------------------
# validate_content: DoS 상한
# ---------------------------------------------------------------------------


def test_node_count_limit():
    nodes = [{"type": "horizontalRule"} for _ in range(MAX_CONTENT_NODES + 1)]
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(*nodes), set())


def test_text_char_limit():
    # 노드 수 상한에 안 걸리게 큰 텍스트 몇 덩어리로 글자 수 상한만 초과시킨다.
    chunk = "가" * (MAX_CONTENT_TEXT_CHARS // 2 + 1)
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para(chunk), _para(chunk)), set())


def test_depth_limit():
    node: dict = {"type": "text", "text": "x"}
    for _ in range(MAX_CONTENT_DEPTH + 1):
        node = {"type": "paragraph", "content": [node]}
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(node), set())


# ---------------------------------------------------------------------------
# has_meaningful_content / derive_is_free
# ---------------------------------------------------------------------------


def test_empty_doc_not_meaningful():
    assert has_meaningful_content(empty_doc()) is False


def test_whitespace_and_decorations_not_meaningful():
    doc = _doc({"type": "paragraph"}, {"type": "horizontalRule"}, _para("   "), _PAYWALL)
    assert has_meaningful_content(doc) is False


def test_image_or_text_is_meaningful():
    assert has_meaningful_content(_doc(_img())) is True
    assert has_meaningful_content(_doc(_para("본문"))) is True


def test_no_paywall_is_free():
    assert derive_is_free(_doc(_para("전부"), _img())) is True


def test_paywall_with_paid_tail_is_paid():
    assert derive_is_free(_doc(_para("미리보기"), _PAYWALL, _img())) is False


def test_paywall_at_front_full_paid():
    # 경계가 맨 앞 = 미리보기 0의 전체 유료.
    assert derive_is_free(_doc(_PAYWALL, _para("본편"))) is False


def test_paywall_with_meaningless_tail_is_free():
    doc = _doc(_para("전부 무료"), _PAYWALL, {"type": "paragraph"}, _para("  "))
    assert derive_is_free(doc) is True
