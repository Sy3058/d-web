"""에피소드 관리 API 테스트 (M1.5 D3, ADM-03).

구조 A(장당 업로드 + JSON 메타 분리) 계약 검증. R2는 upload_bytes를 가로채
키만 기록한다(hermetic - 실연결은 D1 스모크로 기확인). 인가 픽스처는
test_admin_works.py와 동일 패턴(쿠키 직접 set - 로그인 플로우 재현 불필요).
"""

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import update
from sqlmodel.ext.asyncio.session import AsyncSession

from src.lib.auth import access_cookie_name, create_access_token
from src.lib.exceptions import EpisodeConflictError
from src.models.user import RoleEnum, User
from src.models.work import Episode
from src.schemas.work import EpisodeCreate, EpisodeUpdate, WorkCreate
from src.services import (
    auth_service,
    episode_service,
    image_service,
    r2_service,
    work_service,
)

WORKS_URL = "/admin/works"


def _episodes_url(work_id: str) -> str:
    return f"{WORKS_URL}/{work_id}/episodes"


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
async def uploaded_keys(monkeypatch) -> list[str]:
    """R2 업로드를 가로채 키만 기록. episode/work service 둘 다 r2_service 모듈
    속성을 런타임 조회(`r2_service.upload_bytes`)하므로 setattr 한 번으로 전 경로 mock."""
    keys: list[str] = []

    async def fake_upload(key: str, data: bytes, content_type: str = "image/webp") -> str:
        keys.append(key)
        return key

    monkeypatch.setattr(r2_service, "upload_bytes", fake_upload)
    return keys


async def _create_work_id(client: AsyncClient) -> str:
    resp = await client.post(WORKS_URL, json={"title": "작품"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_episode(client: AsyncClient, work_id: str, **fields) -> dict:
    resp = await client.post(
        _episodes_url(work_id), json={"episode_no": 1, "title": "1화", **fields}
    )
    assert resp.status_code == 201
    return resp.json()


async def _upload_image(
    client: AsyncClient, work_id: str, episode_id: str, content: bytes | None = None
):
    return await client.post(
        f"{_episodes_url(work_id)}/{episode_id}/images",
        files={"image": ("page.png", content if content is not None else _png(), "image/png")},
    )


async def _put(client: AsyncClient, work_id: str, episode_id: str, **body):
    return await client.put(f"{_episodes_url(work_id)}/{episode_id}", json=body)


async def _episode_with_pages(
    owner_client: AsyncClient, count: int = 3
) -> tuple[str, str, list[str]]:
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    for _ in range(count):
        resp = await _upload_image(owner_client, work_id, episode["id"])
    return work_id, episode["id"], resp.json()["image_keys"]


_MISSING = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


async def test_unauthenticated_401(async_client: AsyncClient):
    resp = await async_client.get(_episodes_url(_MISSING))
    assert resp.status_code == 401


async def test_reader_forbidden_403(async_client: AsyncClient, existing_user: User):
    await _authed(async_client, existing_user)
    resp = await async_client.get(_episodes_url(_MISSING))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# draft 생성 (POST 메타 JSON)
# ---------------------------------------------------------------------------


async def test_create_episode_draft_201(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    body = await _create_episode(owner_client, work_id, price=300, is_free=True)
    assert body["is_published"] is False
    assert body["image_keys"] == []
    assert body["thumbnail"] is None
    assert body["price"] == 300
    assert body["is_free"] is True


async def test_create_episode_duplicate_no_409_before_any_upload(owner_client: AsyncClient):
    # 구조 A의 핵심 이득: 회차 번호 충돌이 이미지 업로드 전에 즉시 발각된다.
    work_id = await _create_work_id(owner_client)
    await _create_episode(owner_client, work_id)
    resp = await owner_client.post(_episodes_url(work_id), json={"episode_no": 1, "title": "중복"})
    assert resp.status_code == 409


async def test_create_episode_work_not_found_404(owner_client: AsyncClient):
    resp = await owner_client.post(_episodes_url(_MISSING), json={"episode_no": 1, "title": "1화"})
    assert resp.status_code == 404


async def test_create_episode_ignores_thumbnail_injection(owner_client: AsyncClient):
    # EpisodeCreate에 thumbnail 필드가 없다 - 임의 R2 키를 실어 보내도 무시돼야 한다.
    work_id = await _create_work_id(owner_client)
    body = await _create_episode(owner_client, work_id, thumbnail="works/x/evil.webp")
    assert body["thumbnail"] is None


async def test_create_episode_naive_published_at_422(owner_client: AsyncClient):
    # 오프셋 없는 로컬 시각은 UTC로 오해석돼 예약이 9시간 밀린다 - AwareDatetime 422.
    work_id = await _create_work_id(owner_client)
    resp = await owner_client.post(
        _episodes_url(work_id),
        json={"episode_no": 1, "title": "1화", "published_at": "2026-07-15T10:00:00"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 이미지 단건 업로드 (append)
# ---------------------------------------------------------------------------


async def test_upload_images_appends_in_order(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    for expected_len in (1, 2, 3):
        resp = await _upload_image(owner_client, work_id, episode["id"])
        assert resp.status_code == 200
        assert len(resp.json()["image_keys"]) == expected_len
    keys = resp.json()["image_keys"]
    assert keys == uploaded_keys  # 배열 순서 = 업로드 순서 (순서 진실은 배열)
    assert len(set(keys)) == 3  # uuid 파일명 - 전부 유일
    prefix = f"works/{work_id}/episodes/{episode['id']}/"
    assert all(k.startswith(prefix) and k.endswith(".webp") for k in keys)


async def test_upload_image_nonimage_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _upload_image(owner_client, work_id, episode["id"], content=b"not an image")
    assert resp.status_code == 422
    assert uploaded_keys == []  # 검증 실패는 R2에 닿기 전 - 미참조 파일(orphan) 0


async def test_upload_image_too_large_422(
    owner_client: AsyncClient, uploaded_keys: list[str], monkeypatch
):
    # 상한은 image_service.MAX_IMAGE_BYTES 단일 출처 - 바운디드 read와 변환 검사가
    # 같은 상수를 참조하므로 여기 하나만 줄이면 21MB 실할당 없이 경로가 검증된다.
    monkeypatch.setattr(image_service, "MAX_IMAGE_BYTES", 10)
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _upload_image(owner_client, work_id, episode["id"])
    assert resp.status_code == 422
    assert uploaded_keys == []


async def test_upload_image_episode_not_found_404(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    resp = await _upload_image(owner_client, work_id, _MISSING)
    assert resp.status_code == 404


async def test_upload_image_wrong_work_scope_404(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 다른 작품 경로로 남의 에피소드에 접근하면 404 (work_id 스코프 조회).
    work_a = await _create_work_id(owner_client)
    work_b = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_a)
    resp = await _upload_image(owner_client, work_b, episode["id"])
    assert resp.status_code == 404


async def test_softdeleted_work_episode_404(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 리뷰 ⑤ 회귀: 삭제된 작품의 에피소드에 업로드·수정·공개가 통과하면 안 된다.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await owner_client.delete(f"{WORKS_URL}/{work_id}")
    assert resp.status_code == 204
    resp = await _upload_image(owner_client, work_id, episode_id)
    assert resp.status_code == 404
    resp = await _put(owner_client, work_id, episode_id, is_published=True)
    assert resp.status_code == 404


async def test_upload_image_limit_409(
    owner_client: AsyncClient, uploaded_keys: list[str], db_session: AsyncSession
):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    full = [f"works/{work_id}/episodes/{episode['id']}/{uuid.uuid4().hex}.webp" for _ in range(50)]
    await db_session.exec(
        update(Episode).where(Episode.id == uuid.UUID(episode["id"])).values(image_keys=full)
    )
    await db_session.commit()
    resp = await _upload_image(owner_client, work_id, episode["id"])
    assert resp.status_code == 409
    assert uploaded_keys == []  # 선검증에서 거부 - 변환·업로드 비용 0


async def test_append_image_stale_state_conflict(
    owner: User, uploaded_keys: list[str], db_session: AsyncSession
):
    """조건부 UPDATE의 경합 차단(rowcount=0): 스냅샷 길이가 stale이면 append 거부.

    동시 요청 재현 - 한 요청이 길이 0을 스냅샷한 뒤(커밋 전) 다른 요청이 먼저
    append를 커밋한 상황을, bulk UPDATE로 DB만 전진시켜 결정적으로 만든다.
    """
    work = await work_service.create_work(WorkCreate(title="경합"), owner.id, db_session)
    episode = await episode_service.create_episode(
        work.id, EpisodeCreate(episode_no=1, title="1화"), db_session
    )
    sneaky = f"works/{work.id}/episodes/{episode.id}/{uuid.uuid4().hex}.webp"
    await db_session.exec(
        update(Episode)
        .where(Episode.id == episode.id)
        .values(image_keys=[sneaky])
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()

    with pytest.raises(EpisodeConflictError):
        await episode_service.append_image(work.id, episode.id, 0, b"fake-webp", db_session)
    # R2 업로드는 DB보다 먼저라 미참조 파일 1개는 발생하나(수용된 트레이드오프), uuid 키라
    # 살아있는 키와 절대 충돌하지 않는다 - 리뷰 ① 회귀.
    assert len(uploaded_keys) == 1
    assert uploaded_keys[0] != sneaky


async def test_new_upload_never_collides_with_existing_keys(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    """중간 페이지 삭제 후 새 업로드가 살아있는 키와 절대 겹치지 않는다(uuid 파일명).

    순번 파일명 시절엔 len 기반이면 살아있는 키를, max+1이어도 동시 업로드가 서로를
    덮어쓸 수 있었다(리뷰 ①·⑦) - uuid는 구조적으로 충돌 불가.
    """
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, image_keys=[keys[0], keys[2]])
    assert resp.status_code == 200
    resp = await _upload_image(owner_client, work_id, episode_id)
    new_keys = resp.json()["image_keys"]
    assert new_keys[:2] == [keys[0], keys[2]]  # 살아있는 페이지 무손상
    assert new_keys[-1] not in keys  # 과거 키 재사용 없음


# ---------------------------------------------------------------------------
# PUT: 메타 부분수정 / 재배열·삭제 / 썸네일
# ---------------------------------------------------------------------------


async def test_update_meta_partial(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id, price=300)
    resp = await _put(owner_client, work_id, episode["id"], title="개정판 1화")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "개정판 1화"
    assert body["price"] == 300  # 미포함 필드 유지
    assert body["episode_no"] == 1


async def test_update_explicit_null_title_422(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _put(owner_client, work_id, episode["id"], title=None)
    assert resp.status_code == 422


async def test_update_duplicate_episode_no_409(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    await _create_episode(owner_client, work_id, episode_no=1)
    ep2 = await _create_episode(owner_client, work_id, episode_no=2, title="2화")
    resp = await _put(owner_client, work_id, ep2["id"], episode_no=1)
    assert resp.status_code == 409


async def test_reorder_reflected(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    reordered = [keys[2], keys[0], keys[1]]
    resp = await _put(owner_client, work_id, episode_id, image_keys=reordered)
    assert resp.status_code == 200
    assert resp.json()["image_keys"] == reordered  # 순서 진실 = 배열 (키 파일명 아님)


async def test_reorder_subset_deletes_page(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, image_keys=[keys[2], keys[0]])
    assert resp.status_code == 200
    assert resp.json()["image_keys"] == [keys[2], keys[0]]


async def test_reorder_duplicate_key_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    # set 비교였다면 통과했을 입력 - multiset 검증 회귀 테스트(council).
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, image_keys=[keys[0], keys[0], keys[1]])
    assert resp.status_code == 422


async def test_reorder_foreign_key_injection_422(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    evil = "works/other/episodes/other/000.webp"
    resp = await _put(owner_client, work_id, episode_id, image_keys=[*keys[:2], evil])
    assert resp.status_code == 422


async def test_reorder_stale_snapshot_conflict(
    owner: User, uploaded_keys: list[str], db_session: AsyncSession
):
    """리뷰 ② 회귀: 인플라이트 append가 먼저 커밋됐으면 stale 재배열은 409.

    무보호 last-write-wins였다면 200을 받은 업로드 결과가 조용히 지워졌을 시나리오.
    """
    work = await work_service.create_work(WorkCreate(title="재배열경합"), owner.id, db_session)
    episode = await episode_service.create_episode(
        work.id, EpisodeCreate(episode_no=1, title="1화"), db_session
    )
    appended = f"works/{work.id}/episodes/{episode.id}/{uuid.uuid4().hex}.webp"
    await db_session.exec(
        update(Episode)
        .where(Episode.id == episode.id)
        .values(image_keys=[appended])
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()

    # episode 인메모리 스냅샷은 여전히 0장 - 빈 배열 재배열(전체 삭제) 시도
    with pytest.raises(EpisodeConflictError):
        await episode_service.update_episode(episode, EpisodeUpdate(image_keys=[]), db_session)


async def test_thumbnail_select_from_pages(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 작가가 표지 일러스트 페이지(중간 컷)를 직접 대표로 지정하는 핵심 시나리오.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, thumbnail=keys[1])
    assert resp.status_code == 200
    assert resp.json()["thumbnail"] == keys[1]


async def test_thumbnail_not_uploaded_key_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, thumbnail="works/x/cover.webp")
    assert resp.status_code == 422


async def test_thumbnail_invalid_does_not_apply_reorder(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 리뷰 ⑧ 회귀(validate-then-mutate): 같은 요청의 유효한 재배열도 적용되면 안 된다.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(
        owner_client, work_id, episode_id, image_keys=keys[:2], thumbnail="works/x/evil.webp"
    )
    assert resp.status_code == 422
    resp = await owner_client.get(_episodes_url(work_id))
    assert resp.json()[0]["image_keys"] == keys  # 3장 그대로 - 부분 적용 없음


async def test_thumbnail_auto_reset_when_page_deleted(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    await _put(owner_client, work_id, episode_id, thumbnail=keys[2])
    resp = await _put(owner_client, work_id, episode_id, image_keys=keys[:2])
    assert resp.status_code == 200
    assert resp.json()["thumbnail"] is None  # 선택 페이지 삭제 -> stale 키 자동 해제


async def test_thumbnail_explicit_null_clears(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    await _put(owner_client, work_id, episode_id, thumbnail=keys[0])
    resp = await _put(owner_client, work_id, episode_id, thumbnail=None)
    assert resp.status_code == 200
    assert resp.json()["thumbnail"] is None


# ---------------------------------------------------------------------------
# 공개 (즉시/예약) - 리뷰 ③·④ 시맨틱
# ---------------------------------------------------------------------------


async def test_publish_immediately_stamps_published_at(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await _put(owner_client, work_id, episode_id, is_published=True)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is True
    assert body["published_at"] is not None  # 공개 회차는 항상 유효한 공개 시각 보유


async def test_publish_empty_episode_422(owner_client: AsyncClient):
    # 리뷰 ④: 이미지 0장 draft는 공개 불가.
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _put(owner_client, work_id, episode["id"], is_published=True)
    assert resp.status_code == 422


async def test_published_episode_cannot_drop_all_pages_422(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 리뷰 ④: 공개 상태에서 image_keys=[]로 전체 삭제도 불가.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    await _put(owner_client, work_id, episode_id, is_published=True)
    resp = await _put(owner_client, work_id, episode_id, image_keys=[])
    assert resp.status_code == 422


async def test_unpublish_clears_published_at(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 리뷰 ③: 비공개 전환 시 published_at을 안 지우면 E1 폴링이 다음 틱에 되살린다.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    await _put(owner_client, work_id, episode_id, is_published=True)
    resp = await _put(owner_client, work_id, episode_id, is_published=False)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is False
    assert body["published_at"] is None


async def test_unpublish_ignores_stale_published_at_echo(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # E1 계획 리뷰 Critical: 전필드 PUT 폼이 직전 published_at(과거 시각)을 에코해도
    # false 전환은 항상 예약 해제여야 한다 - 안 지우면 E1 폴링이 60초 안에 재공개.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await _put(owner_client, work_id, episode_id, is_published=True)
    stale_echo = resp.json()["published_at"]
    resp = await _put(
        owner_client, work_id, episode_id, is_published=False, published_at=stale_echo
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is False
    assert body["published_at"] is None


async def test_schedule_publish_keeps_draft(owner_client: AsyncClient):
    # 예약: published_at만 세팅, is_published 전환은 E1 스케줄러 소관.
    # 이미지 0장 draft에도 예약은 허용(메타 먼저 워크플로) - 공개 전환 시점에 E1이 재검사.
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    resp = await _put(owner_client, work_id, episode["id"], published_at=at)
    assert resp.status_code == 200
    body = resp.json()
    assert body["published_at"] is not None
    assert body["is_published"] is False


async def test_update_naive_published_at_422(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _put(owner_client, work_id, episode["id"], published_at="2026-07-15T10:00:00")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET 목록
# ---------------------------------------------------------------------------


async def test_list_episodes_ordered_by_episode_no(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    await _create_episode(owner_client, work_id, episode_no=2, title="2화")
    await _create_episode(owner_client, work_id, episode_no=1, title="1화")
    resp = await owner_client.get(_episodes_url(work_id))
    assert resp.status_code == 200
    assert [e["episode_no"] for e in resp.json()] == [1, 2]


# ---------------------------------------------------------------------------
# 표지 업로드 (작품 단위 - 에피소드 페이지와 별개 파일)
# ---------------------------------------------------------------------------


async def test_upload_cover_sets_cover_image(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id = await _create_work_id(owner_client)
    resp = await owner_client.post(
        f"{WORKS_URL}/{work_id}/cover",
        files={"image": ("cover.png", _png(1000, 1500), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["cover_image"] == f"works/{work_id}/cover.webp"
    assert uploaded_keys == [f"works/{work_id}/cover.webp"]


async def test_upload_cover_nonimage_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id = await _create_work_id(owner_client)
    resp = await owner_client.post(
        f"{WORKS_URL}/{work_id}/cover",
        files={"image": ("cover.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 422
    assert uploaded_keys == []
