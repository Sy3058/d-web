"""본문 문서 검증기(lib/content_doc) 단위 테스트 (F3 재설계, 2026-07-15).

DB 불필요한 순수 함수 검증. API 경유 통합 계약(422 매핑, is_free 저장)은
test_admin_episodes.py의 "PUT content" 섹션이 담당한다.
"""

import copy

import pytest

from src.lib.content_doc import (
    MAX_CONTENT_DEPTH,
    MAX_CONTENT_NODES,
    MAX_CONTENT_TEXT_CHARS,
    content_image_keys,
    derive_is_free,
    empty_doc,
    has_meaningful_content,
    split_at_paywall,
    validate_content,
)
from src.lib.exceptions import EpisodeValidationError
from tests.factories import CONTENT_KEY as KEY
from tests.factories import PAYWALL as _PAYWALL
from tests.factories import doc as _doc
from tests.factories import img as _img
from tests.factories import para as _para

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


def test_root_unknown_top_level_field_rejected():
    doc = {"type": "doc", "content": [], "backup_key": "paid-key"}
    with pytest.raises(EpisodeValidationError):
        validate_content(doc, set())


def test_unknown_node_type_rejected():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "iframe"}), set())


def test_unhashable_node_type_rejected_as_validation_error():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": []}), set())


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


def test_unhashable_mark_type_rejected_as_validation_error():
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=[{"type": []}])), set())


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


@pytest.mark.parametrize(
    "node",
    [
        {"type": "paragraph", "backup_key": "paid-key"},
        {"type": "text", "text": "x", "backup_key": "paid-key"},
        {"type": "hardBreak", "backup_key": "paid-key"},
        {"type": "image", "attrs": {"key": KEY}, "backup_key": "paid-key"},
        {"type": "paywall", "backup_key": "paid-key"},
        {"type": "horizontalRule", "backup_key": "paid-key"},
    ],
)
def test_node_unknown_top_level_field_rejected(node):
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(node), {KEY})


def test_mark_unknown_top_level_field_rejected():
    marks = [{"type": "bold", "backup_key": "paid-key"}]
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=marks)), set())


@pytest.mark.parametrize("content", [None, False, "", 0, []])
def test_leaf_content_field_rejected_even_when_falsy(content):
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "hardBreak", "content": content}), set())


@pytest.mark.parametrize("content", [None, False, "", 0, {}])
def test_parent_content_field_must_be_list_when_present(content):
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "paragraph", "content": content}), set())


@pytest.mark.parametrize("node_type", ["paragraph", "hardBreak", "paywall", "horizontalRule"])
def test_empty_attrs_rejected_when_node_has_no_attrs(node_type):
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": node_type, "attrs": {}}), set())


@pytest.mark.parametrize("marks", [None, []])
def test_marks_field_rejected_on_non_text_even_when_falsy(marks):
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "paragraph", "marks": marks}), set())


@pytest.mark.parametrize("marks", [None, False, "", 0, {}])
def test_text_marks_field_must_be_list_when_present(marks):
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc({"type": "text", "text": "x", "marks": marks}), set())


def test_empty_attrs_rejected_on_mark_without_attrs():
    marks = [{"type": "bold", "attrs": {}}]
    with pytest.raises(EpisodeValidationError):
        validate_content(_doc(_para("x", marks=marks)), set())


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


def test_meaningful_check_handles_deep_corrupt_tree_without_recursion_error():
    node: dict = {"type": "text", "text": "유료 본문"}
    for _ in range(1_100):
        node = {"type": "paragraph", "content": [node]}

    free, has_paid = split_at_paywall(_doc(_PAYWALL, node))

    assert free == _doc()
    assert has_paid is True


def test_content_image_keys_collects_nested_unique_keys():
    nested = {
        "type": "paragraph",
        "content": [_img(KEY), {"type": "paragraph", "content": [_img("nested-key")]}],
    }
    assert content_image_keys(_doc(_img(KEY), nested, _img("last-key"))) == {
        KEY,
        "nested-key",
        "last-key",
    }


def test_content_image_keys_ignores_malformed_nodes():
    doc = _doc(
        {"type": "image", "attrs": {}},
        {"type": "image", "attrs": {"key": 123}},
        {"type": "paragraph", "content": [None, "bad"]},
    )
    assert content_image_keys(doc) == set()


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


# ---------------------------------------------------------------------------
# split_at_paywall: 독자 응답 절단 (M2 B2)
# ---------------------------------------------------------------------------


def test_split_without_paywall_keeps_every_node():
    doc = _doc(_para("첫 문단"), _img(), _para("끝 문단"))
    free, has_paid = split_at_paywall(doc)
    assert free["content"] == doc["content"]  # 순서·내용 그대로
    assert has_paid is False


def test_split_drops_the_paywall_node_itself():
    # 경계는 본문이 아니라 메타(has_paid_part)로 나간다 - 노드가 남으면 뷰어가
    # 잠금 상자를 본문 안에 한 번, 플래그로 또 한 번 그린다.
    free, has_paid = split_at_paywall(_doc(_para("미리보기"), _PAYWALL, _para("본편")))
    assert free["content"] == [_para("미리보기")]
    assert has_paid is True


def test_split_at_front_yields_empty_free_part():
    free, has_paid = split_at_paywall(_doc(_PAYWALL, _para("본편"), _img()))
    assert free == {"type": "doc", "content": []}
    assert has_paid is True


def test_split_meaningless_tail_is_not_paid_part():
    # 경계 뒤에 빈 문단만 남은 문서는 "유료 있음"이 아니다.
    doc = _doc(_para("전부 무료"), _PAYWALL, {"type": "paragraph"}, _para("   "))
    free, has_paid = split_at_paywall(doc)
    assert free["content"] == [_para("전부 무료")]
    assert has_paid is False


def test_split_does_not_mutate_input():
    doc = _doc(_para("미리보기"), _PAYWALL, _para("본편"))
    before = copy.deepcopy(doc)
    split_at_paywall(doc)
    assert doc == before


@pytest.mark.parametrize(
    "doc",
    [
        _doc(),
        _doc(_para("전부 무료")),
        _doc(_para("미리보기"), _PAYWALL, _para("본편")),
        _doc(_PAYWALL, _para("본편")),
        _doc(_para("전부 무료"), _PAYWALL),
        _doc(_para("전부 무료"), _PAYWALL, _para("   ")),
        _doc(_para("전부 무료"), _PAYWALL, {"type": "horizontalRule"}),
        _doc(_para("미리보기"), _PAYWALL, _img()),
    ],
)
def test_split_has_paid_part_agrees_with_derive_is_free(doc):
    """경계 해석의 단일 출처 감시.

    is_free 컬럼은 derive_is_free가 쓰고, 절단은 split_at_paywall이 한다. 두 함수가
    경계를 다르게 읽으면 "무료 배지인데 잠금이 뜨는" 회차가 생긴다. 리팩터로 한쪽만
    바뀌는 순간 여기서 깨진다.
    """
    _, has_paid = split_at_paywall(doc)
    assert has_paid is (not derive_is_free(doc))
