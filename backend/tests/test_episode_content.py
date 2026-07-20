"""무료 구간 회차 본문 API 테스트 (M2 그룹 B2 - 보안 그룹).

인증 불요(무료 구간은 비로그인 열람)라 async_client를 쿠키 없이 그대로 쓴다.

presigned 발급은 presign_spy로 대체하고 **호출 인자까지** 본다. 절단과 치환의 순서가
뒤집혀 유료 구간 키에 서명이 나가도 최종 응답은 멀쩡해 보이기 때문에(잘린 뒤라 응답엔
없음), 응답 검사만으로는 절대 잡히지 않는다.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.user import User
from src.services import episode_read_service, r2_service
from tests.factories import PAYWALL as _PAYWALL
from tests.factories import doc as _doc
from tests.factories import img as _img
from tests.factories import make_episode as _make_episode
from tests.factories import make_work as _make_work
from tests.factories import para as _para

FREE_KEY = "works/w/episodes/e/free-page.webp"
PAID_KEY = "works/w/episodes/e/paid-page.webp"

FREE_TEXT = "무료 본문입니다"
PAID_TEXT = "유료 본문입니다"


def _content_url(episode_id: uuid.UUID | str) -> str:
    return f"/episodes/{episode_id}/content"


def _image_nodes(node: object) -> list[dict]:
    """문서 트리 전체에서 image 노드를 모은다(중첩 포함).

    "원본 키가 응답에 없다"는 넓은 단언은 presigned URL이 구조상 키를 경로에 포함해
    쓸 수 없다. 대신 **모든** image 노드의 attrs가 {"src"}뿐임을 확인하는 것이 그
    자리를 메운다 - 특정 인덱스 하나만 보면 중첩 경로의 회귀를 놓친다.
    """
    if not isinstance(node, dict):
        return []
    found = [node] if node.get("type") == "image" else []
    for child in node.get("content") or []:
        found.extend(_image_nodes(child))
    return found


@pytest.fixture(autouse=True)
def presign_spy(monkeypatch) -> list[list[str]]:
    """presign_get_urls 호출 인자를 기록하고 결정적 URL을 돌려준다.

    autouse - 어떤 테스트도 실수로 실제 R2에 서명을 요청하지 못하게 한다(conftest의
    _stub_hibp와 같은 이유). 반환값은 호출별 키 목록의 리스트.
    """
    calls: list[list[str]] = []

    async def _fake(keys):
        calls.append(list(keys))
        return [f"https://r2.example/{k}?sig=SIGNED" for k in keys]

    monkeypatch.setattr(r2_service, "presign_get_urls", _fake)
    return calls


async def _partial_paid_episode(db_session: AsyncSession, user: User):
    """앞부분 무료(글+이미지), 경계, 뒷부분 유료(글+이미지)인 공개 회차."""
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=False,
        image_keys=[FREE_KEY, PAID_KEY],
        content=_doc(
            _para(FREE_TEXT),
            _img(FREE_KEY),
            _PAYWALL,
            _para(PAID_TEXT),
            _img(PAID_KEY),
        ),
    )
    return work, ep


# ---------------------------------------------------------------------------
# 절단 - 무엇이 나가고 무엇이 안 나가는가
# ---------------------------------------------------------------------------


async def test_free_episode_returns_whole_document(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=True,
        image_keys=[FREE_KEY],
        content=_doc(_para("첫 문단"), _img(FREE_KEY), _para("끝 문단")),
    )

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["episode_id"] == str(ep.id)
    assert body["has_paid_part"] is False

    nodes = body["content"]["content"]
    assert [n["type"] for n in nodes] == ["paragraph", "image", "paragraph"]
    assert nodes[0]["content"][0]["text"] == "첫 문단"
    assert nodes[2]["content"][0]["text"] == "끝 문단"


async def test_partial_paid_returns_only_free_part(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    _, ep = await _partial_paid_episode(db_session, user)

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_paid_part"] is True

    nodes = body["content"]["content"]
    # 경계 이전 2개만. paywall 노드 자체도 나가지 않는다.
    assert [n["type"] for n in nodes] == ["paragraph", "image"]
    assert nodes[0]["content"][0]["text"] == FREE_TEXT


async def test_paid_section_text_absent_from_response(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 유료 유출은 이미지만의 문제가 아니다 - 글도 유료로 연재할 수 있다.
    _, ep = await _partial_paid_episode(db_session, user)

    resp = await async_client.get(_content_url(ep.id))
    assert PAID_TEXT not in resp.text
    assert FREE_TEXT in resp.text


async def test_paid_section_key_absent_from_response(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    """유료 구간 키는 응답 어디에도 없다.

    ⚠️ 무료 구간 키는 이 단언의 대상이 아니다 - 실제 presigned URL은 구조상 키를
    경로에 포함하므로(`{endpoint}/{bucket}/{key}?X-Amz-...`) "응답에 키 문자열이
    없다"는 이미지가 나가는 한 성립할 수 없다. 지켜야 할 성질은 (a) 유료 구간 키가
    아예 없을 것, (b) 무료 구간 키도 **맨 키로는** 나가지 않을 것(= attrs에 key가
    남지 않음, test_image_attrs_replaced_not_extended)이다.
    """
    _, ep = await _partial_paid_episode(db_session, user)

    resp = await async_client.get(_content_url(ep.id))
    assert PAID_KEY not in resp.text
    assert "sig=SIGNED" in resp.text


async def test_image_attrs_replaced_not_extended(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # attrs에 src를 "추가"하면 key가 남아 원본 키가 새어 나간다.
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=True,
        image_keys=[FREE_KEY],
        # 최상위 + paragraph 중첩 둘 다 - 특정 인덱스만 보면 중첩 회귀를 놓친다.
        content=_doc(_img(FREE_KEY), {"type": "paragraph", "content": [_img(FREE_KEY)]}),
    )

    resp = await async_client.get(_content_url(ep.id))
    images = _image_nodes(resp.json()["content"])
    assert len(images) == 2
    for image in images:
        assert set(image["attrs"]) == {"src"}


async def test_paywall_at_front_returns_empty_content(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=False,
        image_keys=[PAID_KEY],
        content=_doc(_PAYWALL, _para(PAID_TEXT), _img(PAID_KEY)),
    )

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == {"type": "doc", "content": []}
    assert body["has_paid_part"] is True
    assert PAID_TEXT not in resp.text


# ---------------------------------------------------------------------------
# presign - 유료 구간 키에 서명이 나가지 않는가
# ---------------------------------------------------------------------------


async def test_paid_section_keys_are_never_signed(
    async_client: AsyncClient, db_session: AsyncSession, user: User, presign_spy: list[list[str]]
):
    """절단 -> 치환 순서의 유일한 탐지 수단.

    순서가 뒤집히면 문서 전체를 훑어 유료 구간 키까지 서명이 발급된다. 그 뒤에 잘라도
    서명은 이미 나갔고, 최종 응답은 정상으로 보인다.
    """
    _, ep = await _partial_paid_episode(db_session, user)

    await async_client.get(_content_url(ep.id))

    assert presign_spy == [[FREE_KEY]]
    assert PAID_KEY not in [key for call in presign_spy for key in call]


async def test_paywall_at_front_signs_nothing(
    async_client: AsyncClient, db_session: AsyncSession, user: User, presign_spy: list[list[str]]
):
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=False,
        image_keys=[PAID_KEY],
        content=_doc(_PAYWALL, _img(PAID_KEY)),
    )

    await async_client.get(_content_url(ep.id))
    # 호출 여부가 아니라 "서명된 키가 하나도 없음"을 본다 - 키가 비었을 때 호출을
    # 생략하는 최적화가 들어와도 검증 의도는 그대로 지켜진다.
    assert [key for call in presign_spy for key in call] == []


async def test_duplicate_key_is_signed_once(
    async_client: AsyncClient, db_session: AsyncSession, user: User, presign_spy: list[list[str]]
):
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=True,
        image_keys=[FREE_KEY],
        content=_doc(_img(FREE_KEY), _para("사이"), _img(FREE_KEY)),
    )

    resp = await async_client.get(_content_url(ep.id))
    assert presign_spy == [[FREE_KEY]]

    nodes = resp.json()["content"]["content"]
    assert nodes[0]["attrs"]["src"] == nodes[2]["attrs"]["src"]


async def test_nested_image_inside_paragraph_is_signed(
    async_client: AsyncClient, db_session: AsyncSession, user: User, presign_spy: list[list[str]]
):
    # image는 paragraph 안에 중첩될 수 있다 - 최상위만 훑으면 키가 그대로 새어 나간다.
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=True,
        image_keys=[FREE_KEY],
        content=_doc({"type": "paragraph", "content": [_img(FREE_KEY)]}),
    )

    resp = await async_client.get(_content_url(ep.id))
    assert presign_spy == [[FREE_KEY]]

    nested = resp.json()["content"]["content"][0]["content"][0]
    assert set(nested["attrs"]) == {"src"}
    assert nested["attrs"]["src"].endswith("?sig=SIGNED")


# ---------------------------------------------------------------------------
# 노출 게이트 - 404
# ---------------------------------------------------------------------------


async def test_image_without_key_is_dropped_not_500(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    """attrs가 없는 image 노드는 통째로 버린다(500 금지).

    API 쓰기 경로는 validate_content(episode_service)를 타므로 이런 문서가 정상
    경로로는 안 들어오지만, 수동 DB 편집·마이그레이션으로 생기면 공개 읽기
    엔드포인트가 죽는다. 원본 키를 남기거나 빈 src를 내보내지 않고 버리는 쪽이 안전.
    """
    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session,
        work,
        is_free=True,
        image_keys=[FREE_KEY],
        content=_doc(_para("본문"), {"type": "image"}, _img(FREE_KEY)),
    )

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 200

    images = _image_nodes(resp.json()["content"])
    assert len(images) == 1  # key 없는 노드는 빠지고 정상 이미지만 남는다
    assert set(images[0]["attrs"]) == {"src"}


async def test_dropped_image_is_logged(
    async_client: AsyncClient, db_session: AsyncSession, user: User, monkeypatch
):
    """노드를 조용히 버리지 않는다 - 독자는 200을 받지만 서버는 알아야 한다.

    로그가 없으면 "그림이 안 나온다"는 신고가 들어올 때까지 아무도 모른다.
    """
    warnings: list[tuple] = []

    def _capture(event: str, **kw):
        warnings.append((event, kw))

    monkeypatch.setattr(episode_read_service.logger, "warning", _capture)

    work = await _make_work(db_session, user)
    ep = await _make_episode(
        db_session, work, is_free=True, content=_doc({"type": "image"}, {"type": "image"})
    )

    await async_client.get(_content_url(ep.id))

    assert len(warnings) == 1
    event, kw = warnings[0]
    assert event == "episode_content_image_dropped"
    assert kw["episode_id"] == str(ep.id)
    assert kw["dropped_count"] == 2


async def test_no_log_when_nothing_dropped(
    async_client: AsyncClient, db_session: AsyncSession, user: User, monkeypatch
):
    # 정상 문서에서 경고가 뜨면 로그가 소음이 되어 아무도 안 본다.
    warnings: list[tuple] = []
    monkeypatch.setattr(
        episode_read_service.logger, "warning", lambda event, **kw: warnings.append((event, kw))
    )

    _, ep = await _partial_paid_episode(db_session, user)
    await async_client.get(_content_url(ep.id))

    assert warnings == []


async def test_unpublished_episode_404(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    work = await _make_work(db_session, user)
    ep = await _make_episode(db_session, work, is_published=False, content=_doc(_para(PAID_TEXT)))

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 404
    assert PAID_TEXT not in resp.text


async def test_hidden_work_episode_404(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    """작품을 숨기면(is_published=false) 회차 ID 직접 접근도 막혀야 한다.

    회차 행의 is_published는 true로 남아 있으므로, Episode만 검사하는 admin 패턴을
    복사하면 여기서 본문이 그대로 나간다.
    """
    work = await _make_work(db_session, user, is_published=False)
    ep = await _make_episode(db_session, work, content=_doc(_para(PAID_TEXT)))

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 404
    assert PAID_TEXT not in resp.text


async def test_soft_deleted_work_episode_404(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # soft delete는 에피소드를 남긴다 - 내려간 작품이 계속 열람되면 안 된다.
    work = await _make_work(db_session, user)
    ep = await _make_episode(db_session, work, content=_doc(_para(PAID_TEXT)))
    work.deleted_at = datetime.now(UTC)
    db_session.add(work)
    await db_session.commit()

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 404
    assert PAID_TEXT not in resp.text


async def test_nonexistent_episode_404(async_client: AsyncClient):
    resp = await async_client.get(_content_url(uuid.uuid4()))
    assert resp.status_code == 404


async def test_404_is_not_cached(async_client: AsyncClient, db_session: AsyncSession, user: User):
    """404도 no-store여야 한다.

    404는 HTTP 명세상 기본 캐시 가능 상태 코드라, 명시적 헤더가 없으면 heuristic
    캐싱 대상이 된다. 예약 공개 회차를 공개 전에 열어본 독자의 브라우저가 그 404를
    캐시하면, 공개 시각이 지나도 계속 404를 본다(스케줄러 자동 공개 - M1.5 E1).
    """
    work = await _make_work(db_session, user)
    ep = await _make_episode(db_session, work, is_published=False)

    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 404
    assert resp.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# 캐시 헤더 / 인증
# ---------------------------------------------------------------------------


async def test_response_is_not_cached(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 본문에 presigned URL이 실려 있어 중간 캐시에 남으면 만료 전까지 재사용된다.
    _, ep = await _partial_paid_episode(db_session, user)

    resp = await async_client.get(_content_url(ep.id))
    assert resp.headers["cache-control"] == "no-store"


async def test_anonymous_reader_can_fetch_free_content(
    async_client: AsyncClient, db_session: AsyncSession, user: User
):
    # 무료 구간은 로그인 불요(진행도 저장만 인증 필요 - C1).
    _, ep = await _partial_paid_episode(db_session, user)

    assert not async_client.cookies
    resp = await async_client.get(_content_url(ep.id))
    assert resp.status_code == 200
