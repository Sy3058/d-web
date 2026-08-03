"""에피소드 관리 API 테스트 (M1.5 D3, ADM-03 + F3 재설계 2026-07-15).

구조 A(장당 업로드 + JSON 메타 분리) 계약 검증. F3부터 본문은 content
문서(TipTap JSON)가 진실이고 image_keys는 업로드 매니페스트, is_free는
paywall 경계에서 서버가 파생한다. R2는 upload_bytes를 가로채 키만
기록한다(hermetic - 실연결은 D1 스모크로 기확인). 인가 픽스처는
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
from sqlmodel import select
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

    async def fake_upload(
        key: str,
        data: bytes,
        content_type: str = "image/webp",
        *,
        bucket: str | None = None,
    ) -> str:
        # bucket은 표지 업로드(M2 D1)만 넘긴다 - 여기선 어느 버킷으로 갔는지는
        # 무시하고 키만 기록한다(버킷 라우팅 자체는 test_upload_cover_uses_public_bucket에서 검증).
        keys.append(key)
        return key

    async def fake_download(key: str, *, bucket: str | None = None) -> bytes:
        # 썸네일 생성(M2 D2)이 원고를 다시 읽는 경로 - 실제 R2엔 아무것도 없으므로
        # (upload_bytes도 fake라 진짜 저장이 안 됨) 유효한 PNG를 대신 돌려줘
        # convert_to_webp가 실제로 동작하게 한다.
        return _png(800, 1200)

    async def fake_delete(key: str, *, bucket: str | None = None) -> None:
        return None

    monkeypatch.setattr(r2_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(r2_service, "download_bytes", fake_download)
    monkeypatch.setattr(r2_service, "delete_object", fake_delete)
    return keys


@pytest_asyncio.fixture
async def r2_calls(monkeypatch) -> dict[str, list[dict]]:
    """uploaded_keys와 달리 bucket 인자까지 기록(M2 D2 리뷰 보강 - 버킷 라우팅 회귀 방지).
    upload/download/delete 세 함수 호출 전부를 별도 리스트에 남긴다."""
    calls: dict[str, list[dict]] = {"upload": [], "download": [], "delete": []}

    async def fake_upload(
        key: str, data: bytes, content_type: str = "image/webp", *, bucket: str | None = None
    ) -> str:
        calls["upload"].append({"key": key, "bucket": bucket})
        return key

    async def fake_download(key: str, *, bucket: str | None = None) -> bytes:
        calls["download"].append({"key": key, "bucket": bucket})
        return _png(800, 1200)

    async def fake_delete(key: str, *, bucket: str | None = None) -> None:
        calls["delete"].append({"key": key, "bucket": bucket})

    monkeypatch.setattr(r2_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(r2_service, "download_bytes", fake_download)
    monkeypatch.setattr(r2_service, "delete_object", fake_delete)
    return calls


async def _create_work_id(client: AsyncClient) -> str:
    resp = await client.post(WORKS_URL, json={"title": "작품"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_episode(client: AsyncClient, work_id: str, **fields) -> dict:
    resp = await client.post(_episodes_url(work_id), json={"title": "1화", **fields})
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


def _doc(*nodes: dict) -> dict:
    return {"type": "doc", "content": list(nodes)}


def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _img(key: str) -> dict:
    return {"type": "image", "attrs": {"key": key}}


_PAYWALL = {"type": "paywall"}
_EMPTY_DOC = {"type": "doc", "content": []}


async def _episode_with_content(
    owner_client: AsyncClient, count: int = 1
) -> tuple[str, str, list[str]]:
    """페이지 업로드 후 본문(content)까지 채운 공개 가능 상태의 에피소드."""
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count)
    resp = await _put(owner_client, work_id, episode_id, content=_doc(*(_img(k) for k in keys)))
    assert resp.status_code == 200
    return work_id, episode_id, keys


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
    body = await _create_episode(owner_client, work_id, price=300)
    assert body["is_published"] is False
    assert body["image_keys"] == []
    assert body["content"] == _EMPTY_DOC
    assert body["subtitle"] is None
    assert body["thumbnail"] is None
    assert body["price"] == 300
    assert body["is_free"] is True  # 빈 문서 = 무료 (파생 정합)


async def test_create_episode_assigns_public_id(owner_client: AsyncClient):
    # public_id는 클라이언트 입력이 아니라 서버가 무작위 발급하고, 매번 다른 값이다.
    work_id = await _create_work_id(owner_client)
    body = await _create_episode(owner_client, work_id, title="1화")
    assert isinstance(body["public_id"], int)
    assert 10_000_000 <= body["public_id"] <= 99_999_999

    other = await _create_episode(owner_client, work_id, title="2화")
    assert other["public_id"] != body["public_id"]


async def test_create_episode_requires_title(owner_client: AsyncClient):
    # 서버 기본값 "무제" 폐지(회차 번호 폐기와 동반) - 번호가 사라져 제목이 유일한
    # 식별자가 됐으므로 빈 제목으로 회차가 생기는 경로 자체를 없앤다. 생략도 빈 문자열도 422.
    work_id = await _create_work_id(owner_client)
    assert (await owner_client.post(_episodes_url(work_id), json={})).status_code == 422
    resp = await owner_client.post(_episodes_url(work_id), json={"title": ""})
    assert resp.status_code == 422


async def test_create_episode_ignores_is_free_injection(owner_client: AsyncClient):
    # is_free는 content 파생 컬럼 - 입력으로 보내도 무시된다(EpisodeCreate에 필드 없음).
    work_id = await _create_work_id(owner_client)
    body = await _create_episode(owner_client, work_id, is_free=False)
    assert body["is_free"] is True


async def test_create_episode_retries_on_public_id_collision(
    owner_client: AsyncClient, monkeypatch
):
    # public_id는 클라이언트가 지정할 수 없으니(요청 필드 아님) 충돌은 서버 내부 재시도로만
    # 관측 가능하다 - _generate_public_id를 몽키패치해 1회 충돌 후 성공을 재현한다.
    work_id = await _create_work_id(owner_client)
    values = iter([10_000_001, 10_000_001, 20_000_002])
    monkeypatch.setattr(episode_service, "_generate_public_id", lambda: next(values))

    first = await owner_client.post(_episodes_url(work_id), json={"title": "1화"})
    assert first.status_code == 201
    assert first.json()["public_id"] == 10_000_001

    second = await owner_client.post(_episodes_url(work_id), json={"title": "2화"})
    assert second.status_code == 201
    assert second.json()["public_id"] == 20_000_002


async def test_create_episode_public_id_exhausted_409(owner_client: AsyncClient, monkeypatch):
    # 재시도 상한(5회)을 모두 충돌로 소진하면 409. 실제로는 9천만 공간에서 극히
    # 희박하지만, 로직 자체(무한 루프 대신 명시적 실패)는 결정적으로 검증돼야 한다.
    work_id = await _create_work_id(owner_client)
    monkeypatch.setattr(episode_service, "_generate_public_id", lambda: 10_000_001)
    await owner_client.post(_episodes_url(work_id), json={"title": "1화"})

    resp = await owner_client.post(_episodes_url(work_id), json={"title": "충돌"})
    assert resp.status_code == 409


async def test_create_episode_work_not_found_404(owner_client: AsyncClient):
    resp = await owner_client.post(_episodes_url(_MISSING), json={"title": "1화"})
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
        json={"title": "1화", "published_at": "2026-07-15T10:00:00"},
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
    assert keys == uploaded_keys  # 매니페스트는 업로드 순서 보존 (표시 순서 진실은 content)
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
    episode = await episode_service.create_episode(work.id, EpisodeCreate(title="1화"), db_session)
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


async def test_update_explicit_null_title_422(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _put(owner_client, work_id, episode["id"], title=None)
    assert resp.status_code == 422


async def test_reorder_reflected(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    reordered = [keys[2], keys[0], keys[1]]
    resp = await _put(owner_client, work_id, episode_id, image_keys=reordered)
    assert resp.status_code == 200
    assert resp.json()["image_keys"] == reordered  # 보낸 배열 그대로 저장(중복 없는 부분집합)


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
    episode = await episode_service.create_episode(work.id, EpisodeCreate(title="1화"), db_session)
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


async def test_thumbnail_select_uploads_to_public_bucket(
    owner_client: AsyncClient, r2_calls: dict[str, list[dict]]
):
    # 리뷰 보강: 썸네일 축소본이 실제로 공개 버킷(dweb-cover)으로 가는지 - 기존
    # uploaded_keys 픽스처는 bucket 인자를 무시해 이 회귀를 못 잡았다.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, thumbnail=keys[1])
    assert resp.status_code == 200
    thumb_uploads = [c for c in r2_calls["upload"] if c["key"].endswith("thumb.webp")]
    assert len(thumb_uploads) == 1
    assert thumb_uploads[0]["bucket"] == r2_service.settings.r2_public_bucket == "dweb-cover"


async def test_thumbnail_resend_same_value_no_r2_calls(
    owner_client: AsyncClient, r2_calls: dict[str, list[dict]]
):
    # 리뷰 보강: 동일 키 재전송은 R2 왕복 0(썸네일 "변경" 아님) - 코드는 맞았으나
    # 이 경로를 직접 단언하는 테스트가 없었다.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    await _put(owner_client, work_id, episode_id, thumbnail=keys[0])
    r2_calls["upload"].clear()
    r2_calls["download"].clear()
    r2_calls["delete"].clear()

    resp = await _put(owner_client, work_id, episode_id, thumbnail=keys[0])

    assert resp.status_code == 200
    assert r2_calls["upload"] == []
    assert r2_calls["download"] == []
    assert r2_calls["delete"] == []


async def test_thumbnail_clear_deletes_from_public_bucket(
    owner_client: AsyncClient, r2_calls: dict[str, list[dict]]
):
    # 리뷰 보강: 해제 시 delete_object가 공개 버킷 인자로 호출되는지.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    await _put(owner_client, work_id, episode_id, thumbnail=keys[0])

    resp = await _put(owner_client, work_id, episode_id, thumbnail=None)

    assert resp.status_code == 200
    assert len(r2_calls["delete"]) == 1
    assert r2_calls["delete"][0]["key"].endswith("thumb.webp")
    assert r2_calls["delete"][0]["bucket"] == r2_service.settings.r2_public_bucket == "dweb-cover"


# ---------------------------------------------------------------------------
# PUT content: 본문 문서 저장 (F3 재설계)
# ---------------------------------------------------------------------------


async def test_save_content_derives_paid(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 글+이미지 혼합 본문 저장 + paywall 뒤 유료 분량 존재 → is_free=false 파생.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    doc = _doc(_para("도입부"), _img(keys[0]), _PAYWALL, _img(keys[1]), _img(keys[2]))
    resp = await _put(owner_client, work_id, episode_id, content=doc)
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == doc
    assert body["is_free"] is False


async def test_content_without_paywall_is_free(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 경계 없음 = 전체 무료 (에디터 기본 - 작가가 상자를 옮겨야 유료).
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await _put(owner_client, work_id, episode_id, content=_doc(_img(keys[0])))
    assert resp.status_code == 200
    assert resp.json()["is_free"] is True


async def test_content_paywall_at_end_is_free(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 경계 뒤에 유의미 콘텐츠가 없으면 전체 무료.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await _put(owner_client, work_id, episode_id, content=_doc(_img(keys[0]), _PAYWALL))
    assert resp.status_code == 200
    assert resp.json()["is_free"] is True


async def test_content_foreign_image_key_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 이 회차 매니페스트에 없는 키 참조 = 임의 키 주입 - 다른 회차·작품 원고 참조 금지.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await _put(
        owner_client,
        work_id,
        episode_id,
        content=_doc(_img("works/other/episodes/other/000.webp")),
    )
    assert resp.status_code == 422


async def test_content_disallowed_node_422(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    doc = _doc({"type": "iframe", "attrs": {"src": "https://evil.example"}})
    resp = await _put(owner_client, work_id, episode["id"], content=doc)
    assert resp.status_code == 422


async def test_content_javascript_link_422(owner_client: AsyncClient):
    # 마크 화이트리스트를 통과한 link도 href 스킴은 http(s)만 - javascript: 주입 차단.
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    node = {
        "type": "paragraph",
        "content": [
            {
                "type": "text",
                "text": "클릭",
                "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}],
            }
        ],
    }
    resp = await _put(owner_client, work_id, episode["id"], content=_doc(node))
    assert resp.status_code == 422


async def test_content_meaningless_normalized_to_empty_doc(owner_client: AsyncClient):
    # 빈 paragraph·구분선만 있으면 EMPTY_DOC으로 접힌다 - E1 SQL 가드의 성립 조건.
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    doc = _doc({"type": "paragraph"}, {"type": "horizontalRule"})
    resp = await _put(owner_client, work_id, episode["id"], content=doc)
    assert resp.status_code == 200
    assert resp.json()["content"] == _EMPTY_DOC


async def test_content_save_stale_manifest_conflict(
    owner: User, uploaded_keys: list[str], db_session: AsyncSession
):
    """F3 리뷰 m1 회귀: content 저장도 길이-가드 - 검증에 쓴 매니페스트 스냅샷이
    stale이면(인플라이트 업로드·재배열이 먼저 커밋) 409. 무가드 ORM 경로였다면
    "content 이미지 키 ⊆ image_keys" 불변식이 동시 요청에서 깨졌다."""
    work = await work_service.create_work(WorkCreate(title="본문경합"), owner.id, db_session)
    episode = await episode_service.create_episode(work.id, EpisodeCreate(title="1화"), db_session)
    appended = f"works/{work.id}/episodes/{episode.id}/{uuid.uuid4().hex}.webp"
    await db_session.exec(
        update(Episode)
        .where(Episode.id == episode.id)
        .values(image_keys=[appended])
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()

    # episode 인메모리 스냅샷은 여전히 0장 - 그 기준으로 검증된 content 저장 시도
    with pytest.raises(EpisodeConflictError):
        await episode_service.update_episode(
            episode, EpisodeUpdate(content=_doc(_para("글"))), db_session
        )


async def test_manifest_delete_breaking_content_reference_422(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 본문이 참조 중인 키를 매니페스트에서 지우면 깨진 참조 - 최종 상태 기준 재검증.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, content=_doc(_img(keys[0])))
    assert resp.status_code == 200
    resp = await _put(owner_client, work_id, episode_id, image_keys=[keys[1], keys[2]])
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 공개 (즉시/예약) - 리뷰 ③·④ 시맨틱 (F3: 요건이 "본문 유의미 콘텐츠"로 이동)
# ---------------------------------------------------------------------------


async def test_publish_immediately_stamps_published_at(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, keys = await _episode_with_content(owner_client, count=1)
    resp = await _put(owner_client, work_id, episode_id, is_published=True)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_published"] is True
    assert body["published_at"] is not None  # 공개 회차는 항상 유효한 공개 시각 보유


async def test_publish_text_only_episode(owner_client: AsyncClient):
    # 재설계 핵심 시나리오: 이미지 0장이어도 글이 있으면 공개 가능(공지·연재글).
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    await _put(owner_client, work_id, episode["id"], content=_doc(_para("공지: 다음 주 휴재")))
    resp = await _put(owner_client, work_id, episode["id"], is_published=True)
    assert resp.status_code == 200
    assert resp.json()["is_published"] is True


async def test_publish_empty_episode_422(owner_client: AsyncClient):
    # 리뷰 ④ 계승: 본문 없는 draft는 공개 불가 (이미지가 있어도 본문에 안 실렸으면 동일).
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await _put(owner_client, work_id, episode["id"], is_published=True)
    assert resp.status_code == 422


async def test_publish_pages_without_content_422(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 매니페스트에만 있고 본문에 안 실린 이미지는 독자에게 안 보인다 - 공개 요건 미달.
    work_id, episode_id, keys = await _episode_with_pages(owner_client, count=1)
    resp = await _put(owner_client, work_id, episode_id, is_published=True)
    assert resp.status_code == 422


async def test_published_episode_cannot_clear_content(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 리뷰 ④ 계승: 공개 상태에서 본문 전삭제 불가. #86부터 is_published 없는 content
    # 쓰기는 그보다 앞선 발행 액션 가드(409)에 걸리고, 발행 액션으로 와도 전삭제는 422.
    work_id, episode_id, keys = await _episode_with_content(owner_client, count=1)
    await _put(owner_client, work_id, episode_id, is_published=True)
    resp = await _put(owner_client, work_id, episode_id, content=_doc())
    assert resp.status_code == 409
    resp = await _put(owner_client, work_id, episode_id, content=_doc(), is_published=True)
    assert resp.status_code == 422


async def test_unpublish_clears_published_at(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 리뷰 ③: 비공개 전환 시 published_at을 안 지우면 E1 폴링이 다음 틱에 되살린다.
    work_id, episode_id, keys = await _episode_with_content(owner_client, count=1)
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
    work_id, episode_id, keys = await _episode_with_content(owner_client, count=1)
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
# 편집본(draft) 분리 (#86) - 공개 회차의 임시저장이 라이브를 못 덮는다
# ---------------------------------------------------------------------------


def _draft(*nodes: dict, title: str = "고친 제목") -> dict:
    return {"title": title, "subtitle": None, "content": _doc(*nodes)}


async def _published_episode(
    owner_client: AsyncClient, count: int = 1
) -> tuple[str, str, list[str], dict]:
    work_id, episode_id, keys = await _episode_with_content(owner_client, count)
    resp = await _put(owner_client, work_id, episode_id, is_published=True)
    assert resp.status_code == 200
    return work_id, episode_id, keys, resp.json()


async def test_draft_save_leaves_live_untouched(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # #86 본체: 공개 회차의 임시저장(draft)은 발행본·공개 상태·is_free를 건드리지 않는다.
    work_id, episode_id, _keys, published = await _published_episode(owner_client)
    resp = await _put(owner_client, work_id, episode_id, draft=_draft(_para("수정 중 원고")))
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] == _draft(_para("수정 중 원고"))
    assert body["content"] == published["content"]
    assert body["is_published"] is True
    assert body["published_at"] == published["published_at"]
    assert body["is_free"] == published["is_free"]


async def test_draft_with_content_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    resp = await _put(
        owner_client,
        work_id,
        episode_id,
        content=_doc(_para("발행본")),
        draft=_draft(_para("편집본")),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 회차 soft delete (#85)
# ---------------------------------------------------------------------------


def _episode_url(work_id: str, episode_id: str) -> str:
    return f"{_episodes_url(work_id)}/{episode_id}"


async def _deleted_state(db_session: AsyncSession, episode_id: str) -> tuple:
    """삭제된 행의 (deleted_at, is_published, published_at). API로는 안 보이니 직접 읽는다.

    엔티티가 아니라 컬럼을 select한다 - conftest 세션은 expire_on_commit=False라
    identity map에 남은 Episode 인스턴스가 bulk UPDATE(synchronize_session=False)
    결과를 모른 채 그대로 돌아온다. 컬럼 select는 항상 DB를 친다.
    """
    result = await db_session.exec(
        select(Episode.deleted_at, Episode.is_published, Episode.published_at).where(
            Episode.id == uuid.UUID(episode_id)
        )
    )
    return result.one()


async def test_delete_episode_204_and_hidden_from_list(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    resp = await owner_client.delete(_episode_url(work_id, episode_id))
    assert resp.status_code == 204
    listed = await owner_client.get(_episodes_url(work_id))
    assert listed.status_code == 200
    assert listed.json() == []


async def test_delete_published_episode_unpublishes(
    owner_client: AsyncClient, uploaded_keys: list[str], db_session: AsyncSession
):
    # #85 본체: 공개 중인 회차도 지울 수 있고, 삭제와 공개 해제가 같은 UPDATE로 일어난다.
    work_id, episode_id, _keys, published = await _published_episode(owner_client)
    assert published["is_published"] is True
    assert published["published_at"] is not None

    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204

    deleted_at, is_published, published_at = await _deleted_state(db_session, episode_id)
    # "삭제 ⟹ 비공개" 불변식. 셋 중 하나라도 빠지면 독자 경로(is_published 기준)나
    # 스케줄러 재공개(published_at 기준) 중 한쪽이 뚫린다.
    assert deleted_at is not None
    assert is_published is False
    assert published_at is None


async def test_delete_twice_404(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204
    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 404


async def test_delete_missing_episode_404(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    assert (await owner_client.delete(_episode_url(work_id, _MISSING))).status_code == 404


async def test_deleted_episode_put_404(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 재공개 경로가 막혀야 "삭제 ⟹ 비공개"가 불변식으로 성립한다. 여기가 뚫리면
    # 독자 경로의 deleted_at 가드는 방어선이 아니라 유일한 방어선이 된다.
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204
    assert (await _put(owner_client, work_id, episode_id, is_published=True)).status_code == 404


async def test_deleted_episode_image_upload_404(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204
    assert (await _upload_image(owner_client, work_id, episode_id)).status_code == 404


async def test_delete_removes_public_thumbnail(
    owner_client: AsyncClient, r2_calls: dict[str, list[dict]]
):
    # 공개 버킷 축소본은 서명 없이 열린다 - 회차를 내렸는데 남으면 URL을 아는 사람에게
    # 계속 서빙된다. 원고(image_keys)는 soft delete라 그대로 둔다.
    work_id, episode_id, keys = await _episode_with_content(owner_client)
    assert (await _put(owner_client, work_id, episode_id, thumbnail=keys[0])).status_code == 200
    r2_calls["delete"].clear()

    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204

    assert len(r2_calls["delete"]) == 1
    call = r2_calls["delete"][0]
    assert call["bucket"] == r2_service.settings.r2_public_bucket == "dweb-cover"
    assert call["key"] == r2_service.episode_thumb_key(uuid.UUID(work_id), uuid.UUID(episode_id))


async def test_delete_without_thumbnail_touches_no_object(
    owner_client: AsyncClient, r2_calls: dict[str, list[dict]]
):
    # 위 테스트의 짝. 이것만 없으면 "삭제 시 무조건 thumb 키를 지운다"로 바뀌어도
    # (썸네일 없는 회차에 없는 키 삭제 요청을 날려도) 아무도 못 잡는다.
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    r2_calls["delete"].clear()
    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204
    assert r2_calls["delete"] == []


async def test_delete_excluded_from_work_episode_count(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 작품 목록의 "총 N화"(Work.episode_count 상관 서브쿼리)도 삭제분을 빼야 한다 -
    # 지웠는데 숫자가 그대로면 관리자는 삭제가 안 된 줄 안다.
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    before = (await owner_client.get(f"{WORKS_URL}/{work_id}")).json()["episode_count"]
    assert before == 1
    assert (await owner_client.delete(_episode_url(work_id, episode_id))).status_code == 204
    after = (await owner_client.get(f"{WORKS_URL}/{work_id}")).json()["episode_count"]
    assert after == 0


async def test_content_write_consumes_draft(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 수정 발행 = 에디터가 든 최신 문서를 content로 승격 - 남은 편집본은 소진된다.
    work_id, episode_id, _keys, _published = await _published_episode(owner_client)
    await _put(owner_client, work_id, episode_id, draft=_draft(_para("고친 원고")))
    resp = await _put(
        owner_client, work_id, episode_id, content=_doc(_para("고친 원고")), is_published=True
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is None
    assert body["content"] == _doc(_para("고친 원고"))


async def test_draft_discard_with_explicit_null(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    work_id, episode_id, _keys, published = await _published_episode(owner_client)
    await _put(owner_client, work_id, episode_id, draft=_draft(_para("버릴 원고")))
    resp = await _put(owner_client, work_id, episode_id, draft=None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"] is None
    assert body["content"] == published["content"]


async def test_draft_foreign_image_key_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    # 임시저장이어도 검증은 발행본과 동일 - 임의 키 주입 문서가 DB에 살면 안 된다.
    work_id, episode_id, _keys = await _episode_with_content(owner_client)
    resp = await _put(
        owner_client, work_id, episode_id, draft=_draft(_img("works/x/episodes/y/z.webp"))
    )
    assert resp.status_code == 422


async def test_published_content_without_publish_action_409(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # #86 사고 경로 봉쇄: 공개 회차에 is_published 없는 content 쓰기는 거부 + 라이브 무접촉.
    work_id, episode_id, _keys, published = await _published_episode(owner_client)
    resp = await _put(owner_client, work_id, episode_id, content=_doc(_para("작성 중 원고")))
    assert resp.status_code == 409
    listed = await owner_client.get(_episodes_url(work_id))
    assert listed.json()[0]["content"] == published["content"]


async def test_republish_content_keeps_published_at(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 수정 발행(is_published 동반)은 허용되고 원 공개 시각은 재스탬프되지 않는다.
    work_id, episode_id, _keys, published = await _published_episode(owner_client)
    resp = await _put(
        owner_client, work_id, episode_id, content=_doc(_para("고침")), is_published=True
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == _doc(_para("고침"))
    assert body["published_at"] == published["published_at"]


async def test_publish_flip_race_guarded(
    owner: User, uploaded_keys: list[str], db_session: AsyncSession
):
    """로드 시점 비공개(예약 등) -> 커밋 전 스케줄러가 공개 전환한 race: 조건부 UPDATE의
    is_published=false 가드가 rowcount 0으로 잡는다. 인메모리 409 검사만으로는 이 창이
    안 닫힌다(#86 사고의 race 재발 경로)."""
    work = await work_service.create_work(WorkCreate(title="race"), owner.id, db_session)
    episode = await episode_service.create_episode(work.id, EpisodeCreate(title="1화"), db_session)
    await episode_service.update_episode(
        episode, EpisodeUpdate(content=_doc(_para("본문"))), db_session
    )
    # 스케줄러 전환을 직접 UPDATE로 재현 - 인메모리 episode는 여전히 is_published=False
    await db_session.exec(
        update(Episode)
        .where(Episode.id == episode.id)
        .values(is_published=True)
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    with pytest.raises(EpisodeConflictError):
        await episode_service.update_episode(
            episode, EpisodeUpdate(content=_doc(_para("작성 중"))), db_session
        )


async def test_manifest_delete_breaking_draft_reference_422(
    owner_client: AsyncClient, uploaded_keys: list[str]
):
    # 축소된 매니페스트가 편집본 참조 키를 지우면 승격 시점 깨진 참조 - 즉시 거부.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)
    resp = await _put(owner_client, work_id, episode_id, draft=_draft(_img(keys[0])))
    assert resp.status_code == 200
    resp = await _put(owner_client, work_id, episode_id, image_keys=[keys[1], keys[2]])
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET 목록
# ---------------------------------------------------------------------------


async def _set_columns(db_session: AsyncSession, episode_id: str, **values) -> None:
    await db_session.exec(
        update(Episode).where(Episode.id == uuid.UUID(episode_id)).values(**values)
    )
    await db_session.commit()


async def test_create_episode_assigns_incrementing_sort_order(owner_client: AsyncClient):
    # 기본 표시 순서 = 올린 순서(작품 안에서 max+1). 다른 작품과 번호를 공유하지 않는다.
    work_id = await _create_work_id(owner_client)
    other_work_id = await _create_work_id(owner_client)
    first = await _create_episode(owner_client, work_id, title="첫 화")
    second = await _create_episode(owner_client, work_id, title="다음 화")
    elsewhere = await _create_episode(owner_client, other_work_id, title="남의 작품 1화")

    assert first["sort_order"] == 1
    assert second["sort_order"] == 2
    assert elsewhere["sort_order"] == 1  # work_id 스코프라 1부터 다시 시작


async def test_list_episodes_sort_order_beats_created_at(
    owner_client: AsyncClient, db_session: AsyncSession
):
    # 정렬 1순위는 sort_order(작가 지정)고 created_at은 tie-breaker다.
    # ⚠️ created_at을 sort_order와 **반대 방향**으로 깔아 둔다 - 둘이 같은 방향이면
    # ORDER BY에서 sort_order를 지워도 테스트가 통과해 판별력이 0이 된다.
    work_id = await _create_work_id(owner_client)
    first = await _create_episode(owner_client, work_id, title="첫 화")  # sort_order 1
    second = await _create_episode(owner_client, work_id, title="다음 화")  # sort_order 2

    await _set_columns(db_session, first["id"], created_at=datetime(2026, 1, 2, tzinfo=UTC))
    await _set_columns(db_session, second["id"], created_at=datetime(2026, 1, 1, tzinfo=UTC))

    resp = await owner_client.get(_episodes_url(work_id))
    assert resp.status_code == 200
    assert [e["id"] for e in resp.json()] == [first["id"], second["id"]]


async def test_list_episodes_created_at_breaks_sort_order_tie(
    owner_client: AsyncClient, db_session: AsyncSession
):
    # sort_order엔 UNIQUE가 없어 동점이 정상적으로 발생한다(동시 생성이 같은 max+1을
    # 계산하는 경우). 그때 순서를 확정하는 건 created_at이다 - tie-breaker가 빠지면
    # 순서가 무정의(DB 임의 순서)가 되므로 이 계약도 고정해 둔다.
    work_id = await _create_work_id(owner_client)
    early = await _create_episode(owner_client, work_id, title="먼저 올린 화")
    late = await _create_episode(owner_client, work_id, title="나중 올린 화")

    await _set_columns(
        db_session, early["id"], sort_order=7, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    await _set_columns(
        db_session, late["id"], sort_order=7, created_at=datetime(2026, 1, 2, tzinfo=UTC)
    )

    resp = await owner_client.get(_episodes_url(work_id))
    assert resp.status_code == 200
    assert [e["id"] for e in resp.json()] == [early["id"], late["id"]]


async def test_reorder_episodes_rewrites_sort_order(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    a = await _create_episode(owner_client, work_id, title="A")
    b = await _create_episode(owner_client, work_id, title="B")
    c = await _create_episode(owner_client, work_id, title="C")

    resp = await owner_client.put(
        _episodes_url(work_id), json={"episode_ids": [c["id"], a["id"], b["id"]]}
    )
    assert resp.status_code == 200
    assert [e["id"] for e in resp.json()] == [c["id"], a["id"], b["id"]]
    assert [e["sort_order"] for e in resp.json()] == [1, 2, 3]

    # 응답만 정렬된 게 아니라 실제로 저장됐는지 재조회로 확인한다.
    again = await owner_client.get(_episodes_url(work_id))
    assert [e["id"] for e in again.json()] == [c["id"], a["id"], b["id"]]


async def test_reorder_episodes_rejects_partial_set_409(owner_client: AsyncClient):
    # stale한 목록(다른 탭에서 회차가 추가된 뒤)으로 보낸 재배열은 빠진 회차를 조용히
    # 엉뚱한 자리로 밀어버린다 - 집합 불일치를 낙관적 동시성 검사로 삼아 409로 막는다.
    work_id = await _create_work_id(owner_client)
    a = await _create_episode(owner_client, work_id, title="A")
    await _create_episode(owner_client, work_id, title="B")

    resp = await owner_client.put(_episodes_url(work_id), json={"episode_ids": [a["id"]]})
    assert resp.status_code == 409


async def test_reorder_episodes_rejects_duplicate_and_foreign_ids_409(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    other_work_id = await _create_work_id(owner_client)
    a = await _create_episode(owner_client, work_id, title="A")
    b = await _create_episode(owner_client, work_id, title="B")
    outsider = await _create_episode(owner_client, other_work_id, title="남의 작품")

    dup = await owner_client.put(_episodes_url(work_id), json={"episode_ids": [a["id"], a["id"]]})
    assert dup.status_code == 409

    foreign = await owner_client.put(
        _episodes_url(work_id), json={"episode_ids": [a["id"], b["id"], outsider["id"]]}
    )
    assert foreign.status_code == 409


async def test_reorder_episodes_excludes_deleted(owner_client: AsyncClient):
    # 삭제된 회차는 목록에서 빠지므로 재배열 대상 집합에도 없어야 한다 - 포함시키면 409.
    work_id = await _create_work_id(owner_client)
    a = await _create_episode(owner_client, work_id, title="A")
    b = await _create_episode(owner_client, work_id, title="B")
    assert (await owner_client.delete(f"{_episodes_url(work_id)}/{b['id']}")).status_code == 204

    stale = await owner_client.put(_episodes_url(work_id), json={"episode_ids": [a["id"], b["id"]]})
    assert stale.status_code == 409

    ok = await owner_client.put(_episodes_url(work_id), json={"episode_ids": [a["id"]]})
    assert ok.status_code == 200
    assert [e["id"] for e in ok.json()] == [a["id"]]


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


async def test_upload_cover_uses_public_bucket(owner_client: AsyncClient, monkeypatch):
    # 표지는 원고 버킷(dweb)이 아니라 공개 버킷(dweb-cover)으로 가야 한다(M2 D1) -
    # 실제 버킷 인자를 검증(uploaded_keys 픽스처는 버킷을 무시하므로 여기선 직접 mock).
    calls: list[dict] = []

    async def fake_upload(key, data, content_type="image/webp", *, bucket=None):
        calls.append({"key": key, "bucket": bucket})
        return key

    monkeypatch.setattr(r2_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "https://cover.example.com")

    work_id = await _create_work_id(owner_client)
    resp = await owner_client.post(
        f"{WORKS_URL}/{work_id}/cover",
        files={"image": ("cover.png", _png(1000, 1500), "image/png")},
    )

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["bucket"] == r2_service.settings.r2_public_bucket == "dweb-cover"
    assert resp.json()["cover_url"].startswith(
        f"https://cover.example.com/works/{work_id}/cover.webp?v="
    )


async def test_upload_cover_nonimage_422(owner_client: AsyncClient, uploaded_keys: list[str]):
    work_id = await _create_work_id(owner_client)
    resp = await owner_client.post(
        f"{WORKS_URL}/{work_id}/cover",
        files={"image": ("cover.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 422
    assert uploaded_keys == []


# ---------------------------------------------------------------------------
# presigned 미리보기 URL (GET image-urls - F3에서 M3 GET 발급 앞당김)
# ---------------------------------------------------------------------------


def _image_urls_url(work_id: str, episode_id: str) -> str:
    return f"{_episodes_url(work_id)}/{episode_id}/image-urls"


async def test_image_urls_pairs_in_key_order(
    owner_client: AsyncClient, uploaded_keys: list[str], monkeypatch
):
    # 응답은 image_keys 순서의 {key, url} 쌍 - 프론트 재배열·썸네일 UI의 매핑 계약.
    work_id, episode_id, keys = await _episode_with_pages(owner_client)

    async def fake_presign(ks):
        return [f"https://signed.example/{k}" for k in ks]

    monkeypatch.setattr(r2_service, "presign_get_urls", fake_presign)
    resp = await owner_client.get(_image_urls_url(work_id, episode_id))
    assert resp.status_code == 200
    body = resp.json()
    assert [item["key"] for item in body] == keys
    assert [item["url"] for item in body] == [f"https://signed.example/{k}" for k in keys]


async def test_image_urls_empty_draft(owner_client: AsyncClient):
    # 이미지 0장 draft는 presign 경로 자체를 안 타므로 R2 미설정 환경에서도 200 [].
    work_id = await _create_work_id(owner_client)
    episode = await _create_episode(owner_client, work_id)
    resp = await owner_client.get(_image_urls_url(work_id, episode["id"]))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_image_urls_reader_forbidden_403(async_client: AsyncClient, existing_user: User):
    await _authed(async_client, existing_user)
    resp = await async_client.get(_image_urls_url(_MISSING, _MISSING))
    assert resp.status_code == 403


async def test_image_urls_episode_not_found_404(owner_client: AsyncClient):
    work_id = await _create_work_id(owner_client)
    resp = await owner_client.get(_image_urls_url(work_id, _MISSING))
    assert resp.status_code == 404


async def test_image_urls_r2_unconfigured_503(
    owner_client: AsyncClient, uploaded_keys: list[str], monkeypatch
):
    # 페이지가 있는데 R2 미설정이면 운영자 설정 문제(503)지 클라이언트 귀책이 아니다.
    work_id, episode_id, _keys = await _episode_with_pages(owner_client)
    monkeypatch.setattr(r2_service.settings, "r2_access_key_id", "")
    r2_service._get_client.cache_clear()
    resp = await owner_client.get(_image_urls_url(work_id, episode_id))
    assert resp.status_code == 503
