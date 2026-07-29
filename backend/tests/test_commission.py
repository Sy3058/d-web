"""커미션 카드·사이트 문구 API 테스트 (M2 그룹 G).

admin 인가 경계는 test_admin_works.py와 같은 방식(create_access_token + 쿠키 직접 set).
R2는 전부 mock - 샘플 업로드·삭제가 **공개 버킷 인자**로 호출되는지를 함께 고정한다
(테스트가 전부 mock이라 버킷 라우팅 회귀는 실서버에서만 드러남 - M2 D 리스크 항목).
"""

import uuid
from datetime import UTC, datetime
from io import BytesIO

import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.auth import access_cookie_name, create_access_token
from src.models.commission import CommissionItem, SiteText
from src.models.user import RoleEnum, User
from src.services import auth_service, r2_service
from src.services.commission_service import MAX_SAMPLES_PER_ITEM

ITEMS_URL = "/admin/commission-items"
PUBLIC_ITEMS_URL = "/commission-items"
PUBLIC_BASE = "https://cover.example.com"


def _png(width: int = 100, height: int = 100) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color=(120, 30, 200)).save(buf, format="PNG")
    return buf.getvalue()


async def _authed(client: AsyncClient, user: User) -> None:
    token = create_access_token(str(user.id))
    client.cookies.set(access_cookie_name(), token, domain="test.example")


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = await auth_service.create_user("owner@example.com", "OwnerPass1!", "작가", db_session)
    user.role = RoleEnum.OWNER
    user.totp_confirmed_at = datetime.now(UTC)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def owner_client(async_client: AsyncClient, owner: User) -> AsyncClient:
    await _authed(async_client, owner)
    return async_client


@pytest_asyncio.fixture
async def r2_calls(monkeypatch) -> dict[str, list[dict]]:
    """upload/delete 호출을 bucket 인자까지 기록(test_admin_episodes.r2_calls와 동일 목적)."""
    calls: dict[str, list[dict]] = {"upload": [], "delete": []}

    async def fake_upload(
        key: str, data: bytes, content_type: str = "image/webp", *, bucket: str | None = None
    ) -> str:
        calls["upload"].append({"key": key, "bucket": bucket})
        return key

    async def fake_delete(key: str, *, bucket: str | None = None) -> None:
        calls["delete"].append({"key": key, "bucket": bucket})

    monkeypatch.setattr(r2_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(r2_service, "delete_object", fake_delete)
    return calls


async def _create_item(client: AsyncClient, **fields) -> dict:
    resp = await client.post(
        ITEMS_URL, json={"title": "두상 일러스트", "price_text": "50,000원~", **fields}
    )
    assert resp.status_code == 201
    return resp.json()


async def _set_sample_keys(db_session: AsyncSession, item_id: str, keys: list[str]) -> None:
    """업로드 API를 우회해 매니페스트를 직접 세팅(상한·부분집합 케이스 준비용)."""
    item = await db_session.get(CommissionItem, uuid.UUID(item_id))
    assert item is not None
    item.sample_image_keys = keys
    db_session.add(item)
    await db_session.commit()


# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


async def test_admin_unauthenticated_401(async_client: AsyncClient):
    resp = await async_client.get(ITEMS_URL)
    assert resp.status_code == 401


async def test_admin_reader_forbidden_403(async_client: AsyncClient, existing_user: User):
    await _authed(async_client, existing_user)
    # 인가는 라우팅 뒤 핸들러 앞에서 걸리므로 존재하지 않는 더미 id로도 403이 먼저다 -
    # 전 엔드포인트를 훑어야 의존성 시그니처 정리 중 OwnerDep가 빠지는 회귀를 잡는다.
    dummy = "00000000-0000-0000-0000-000000000000"
    for method, url, kwargs in [
        ("get", ITEMS_URL, {}),
        ("post", ITEMS_URL, {"json": {"title": "x", "price_text": "y"}}),
        ("put", f"{ITEMS_URL}/{dummy}", {"json": {"title": "x"}}),
        ("delete", f"{ITEMS_URL}/{dummy}", {}),
        ("post", f"{ITEMS_URL}/{dummy}/images", {"files": {"image": ("s.png", b"x", "image/png")}}),
        ("get", "/admin/site-texts/landing_intro", {}),
        ("put", "/admin/site-texts/landing_intro", {"json": {"body": "x"}}),
    ]:
        resp = await getattr(async_client, method)(url, **kwargs)
        assert resp.status_code == 403, (method, url)


# ---------------------------------------------------------------------------
# 카드 CRUD
# ---------------------------------------------------------------------------


async def test_create_item_defaults(owner_client: AsyncClient):
    body = await _create_item(owner_client)
    assert body["is_open"] is True
    assert body["sort_order"] == 0
    assert body["sample_image_keys"] == []
    assert body["sample_images"] == []
    assert body["description"] is None
    assert body["duration_text"] is None


async def test_create_item_ignores_sample_keys_injection(owner_client: AsyncClient):
    # 매니페스트는 업로드 엔드포인트 전용 - 생성 입력의 임의 키는 조용히 무시돼야 한다
    # (schemas.CommissionItemCreate에 필드 자체가 없다).
    body = await _create_item(owner_client, sample_image_keys=["evil/key.webp"])
    assert body["sample_image_keys"] == []


async def test_update_item_partial(owner_client: AsyncClient):
    item = await _create_item(owner_client)
    resp = await owner_client.put(
        f"{ITEMS_URL}/{item['id']}", json={"title": "전신 일러스트", "is_open": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "전신 일러스트"
    assert body["is_open"] is False
    assert body["price_text"] == "50,000원~"  # 미전송 필드 유지


async def test_update_item_explicit_null_422(owner_client: AsyncClient):
    item = await _create_item(owner_client)
    resp = await owner_client.put(f"{ITEMS_URL}/{item['id']}", json={"price_text": None})
    assert resp.status_code == 422


async def test_list_items_sorted(owner_client: AsyncClient):
    for order, title in [(2, "셋째"), (0, "첫째"), (1, "둘째")]:
        await _create_item(owner_client, title=title, sort_order=order)
    resp = await owner_client.get(ITEMS_URL)
    assert resp.status_code == 200
    assert [i["title"] for i in resp.json()] == ["첫째", "둘째", "셋째"]


async def test_delete_item_cleans_public_samples(
    owner_client: AsyncClient, db_session: AsyncSession, r2_calls: dict
):
    item = await _create_item(owner_client)
    keys = [f"commission/{item['id']}/{i}.webp" for i in range(2)]
    await _set_sample_keys(db_session, item["id"], keys)

    resp = await owner_client.delete(f"{ITEMS_URL}/{item['id']}")
    assert resp.status_code == 204
    assert (await owner_client.get(ITEMS_URL)).json() == []
    # 커밋 성공 후 공개 버킷에서 샘플 전량 정리
    assert [c["key"] for c in r2_calls["delete"]] == keys
    assert all(c["bucket"] == settings.r2_public_bucket for c in r2_calls["delete"])


# ---------------------------------------------------------------------------
# 샘플 업로드
# ---------------------------------------------------------------------------


async def test_upload_sample_public_bucket_and_key_format(
    owner_client: AsyncClient, r2_calls: dict
):
    item = await _create_item(owner_client)
    resp = await owner_client.post(
        f"{ITEMS_URL}/{item['id']}/images", files={"image": ("s.png", _png(), "image/png")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sample_image_keys"]) == 1
    key = body["sample_image_keys"][0]
    assert key.startswith(f"commission/{item['id']}/")
    assert key.endswith(".webp")
    # 원고 버킷(dweb)이 아니라 공개 버킷으로 - mock 호출 인자가 유일한 탐지 수단
    assert r2_calls["upload"] == [{"key": key, "bucket": settings.r2_public_bucket}]


async def test_upload_sample_consecutive_appends_preserve_order(
    owner_client: AsyncClient, r2_calls: dict
):
    """같은 카드에 2회 연속 업로드 - append 계약(누적 + 순서 보존) 고정.

    빈 카드 1회 업로드만 보면 expected_len 오염(항상 0)과 append→덮어쓰기 회귀가
    전부 통과한다(리뷰 뮤테이션 실측 - MISTAKES "시작값=기대값이면 판별력 0").
    2회째가 있어야 "이전 키가 그 자리에 남는다"는 성질이 처음 검증된다.
    """
    item = await _create_item(owner_client)
    first = await owner_client.post(
        f"{ITEMS_URL}/{item['id']}/images", files={"image": ("a.png", _png(), "image/png")}
    )
    assert first.status_code == 200
    first_key = first.json()["sample_image_keys"][0]

    second = await owner_client.post(
        f"{ITEMS_URL}/{item['id']}/images", files={"image": ("b.png", _png(), "image/png")}
    )
    assert second.status_code == 200
    keys = second.json()["sample_image_keys"]
    assert len(keys) == 2
    assert keys[0] == first_key  # 덮어쓰기 회귀면 1장만 남거나 첫 키가 사라진다
    assert keys[1] != first_key


async def test_upload_sample_cap_409(
    owner_client: AsyncClient, db_session: AsyncSession, r2_calls: dict
):
    item = await _create_item(owner_client)
    await _set_sample_keys(
        db_session,
        item["id"],
        [f"commission/{item['id']}/{i}.webp" for i in range(MAX_SAMPLES_PER_ITEM)],
    )
    resp = await owner_client.post(
        f"{ITEMS_URL}/{item['id']}/images", files={"image": ("s.png", _png(), "image/png")}
    )
    assert resp.status_code == 409
    assert r2_calls["upload"] == []  # 선검증에서 끊겨 업로드 자체가 없음


async def test_upload_sample_invalid_image_422(owner_client: AsyncClient, r2_calls: dict):
    item = await _create_item(owner_client)
    resp = await owner_client.post(
        f"{ITEMS_URL}/{item['id']}/images",
        files={"image": ("s.png", b"not an image", "image/png")},
    )
    assert resp.status_code == 422
    assert r2_calls["upload"] == []


# ---------------------------------------------------------------------------
# 매니페스트 축소(재배열·삭제)
# ---------------------------------------------------------------------------


async def test_update_samples_rejects_foreign_and_duplicate(
    owner_client: AsyncClient, db_session: AsyncSession, r2_calls: dict
):
    item = await _create_item(owner_client)
    mine = f"commission/{item['id']}/a.webp"
    await _set_sample_keys(db_session, item["id"], [mine])

    foreign = await owner_client.put(
        f"{ITEMS_URL}/{item['id']}", json={"sample_image_keys": ["commission/other/b.webp"]}
    )
    assert foreign.status_code == 422

    duplicate = await owner_client.put(
        f"{ITEMS_URL}/{item['id']}", json={"sample_image_keys": [mine, mine]}
    )
    assert duplicate.status_code == 422
    assert r2_calls["delete"] == []  # 검증 실패 경로에서 삭제 부작용 없음


async def test_update_samples_removal_deletes_public_objects(
    owner_client: AsyncClient, db_session: AsyncSession, r2_calls: dict
):
    item = await _create_item(owner_client)
    keep = f"commission/{item['id']}/keep.webp"
    drop = f"commission/{item['id']}/drop.webp"
    await _set_sample_keys(db_session, item["id"], [keep, drop])

    resp = await owner_client.put(f"{ITEMS_URL}/{item['id']}", json={"sample_image_keys": [keep]})
    assert resp.status_code == 200
    assert resp.json()["sample_image_keys"] == [keep]
    assert r2_calls["delete"] == [{"key": drop, "bucket": settings.r2_public_bucket}]


# ---------------------------------------------------------------------------
# 공개 조회
# ---------------------------------------------------------------------------


async def test_public_list_shape(
    async_client: AsyncClient,
    owner_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", PUBLIC_BASE)
    first = await _create_item(owner_client, title="열림", sort_order=0)
    closed = await _create_item(owner_client, title="마감", sort_order=1, is_open=False)
    key = f"commission/{first['id']}/a.webp"
    await _set_sample_keys(db_session, first["id"], [key])

    async_client.cookies.clear()  # 비로그인 보장(owner_client와 같은 jar 공유)
    resp = await async_client.get(PUBLIC_ITEMS_URL)
    assert resp.status_code == 200
    items = resp.json()
    assert [i["title"] for i in items] == ["열림", "마감"]
    assert items[1]["is_open"] is False  # 마감 카드도 목록에 남는다(배지 표시)
    assert items[0]["sample_image_urls"] == [f"{PUBLIC_BASE}/{key}"]
    # 공개 응답 계약: 키 문자열 필드 부재(B2 계약과 표면 일치)
    assert "sample_image_keys" not in items[0]
    assert "sample_images" not in items[0]
    assert str(closed["id"]) == items[1]["id"]


async def test_public_list_urls_empty_when_base_unset(
    async_client: AsyncClient, owner_client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "")
    item = await _create_item(owner_client)
    await _set_sample_keys(db_session, item["id"], [f"commission/{item['id']}/a.webp"])

    async_client.cookies.clear()
    resp = await async_client.get(PUBLIC_ITEMS_URL)
    assert resp.status_code == 200
    # base 미설정(dev 초기)이면 깨진 상대경로 대신 빈 배열로 접는다
    assert resp.json()[0]["sample_image_urls"] == []


# ---------------------------------------------------------------------------
# 사이트 문구
# ---------------------------------------------------------------------------


async def test_admin_site_text_default_when_missing(owner_client: AsyncClient):
    # 행 미시딩 상태의 첫 진입 - 404가 아니라 빈 기본값(첫 편집이 막히지 않게)
    resp = await owner_client.get("/admin/site-texts/landing_intro")
    assert resp.status_code == 200
    assert resp.json() == {"key": "landing_intro", "body": "", "updated_at": None}


async def test_site_text_upsert_roundtrip(owner_client: AsyncClient, async_client: AsyncClient):
    put1 = await owner_client.put("/admin/site-texts/commission_notes", json={"body": "첫 문구"})
    assert put1.status_code == 200
    assert put1.json()["body"] == "첫 문구"
    assert put1.json()["updated_at"] is not None

    put2 = await owner_client.put("/admin/site-texts/commission_notes", json={"body": "수정 문구"})
    assert put2.status_code == 200
    # ON CONFLICT DO UPDATE는 onupdate=func.now()를 발동시키지 않아 set_ 명시가 계약이다
    # (서비스 docstring 경고) - 재저장 시 updated_at 전진을 단언해 그 계약을 고정한다.
    assert datetime.fromisoformat(put2.json()["updated_at"]) > datetime.fromisoformat(
        put1.json()["updated_at"]
    )

    async_client.cookies.clear()
    public = await async_client.get("/site-texts/commission_notes")
    assert public.status_code == 200
    assert public.json()["body"] == "수정 문구"


async def test_public_site_text_missing_404_no_store(async_client: AsyncClient):
    resp = await async_client.get("/site-texts/landing_intro")
    assert resp.status_code == 404
    # 미저장 404가 캐시되면 저장 후에도 404가 보인다(routers/works.py와 같은 근거)
    assert resp.headers["cache-control"] == "no-store"


async def test_public_site_text_unknown_key_422(async_client: AsyncClient):
    resp = await async_client.get("/site-texts/nonexistent_key")
    assert resp.status_code == 422


async def test_site_text_body_too_long_422(owner_client: AsyncClient):
    resp = await owner_client.put("/admin/site-texts/landing_intro", json={"body": "가" * 10_001})
    assert resp.status_code == 422


async def test_site_text_rows_isolated_by_key(owner_client: AsyncClient, db_session: AsyncSession):
    await owner_client.put("/admin/site-texts/landing_intro", json={"body": "소개"})
    row = await db_session.get(SiteText, "commission_notes")
    assert row is None  # 다른 슬롯에 흘러 쓰지 않음
