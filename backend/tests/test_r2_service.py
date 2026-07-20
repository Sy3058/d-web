"""r2_service 단위 테스트 (M1.5 D1).

R2 호출은 전부 mock - 어떤 테스트도 실제 네트워크에 나가지 않는다(hermetic,
CI엔 R2 자격증명이 없다). 실버킷 연결은 2026-07-10 스모크(put/get/delete)로 기확인.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from src.services import r2_service


@pytest.fixture(autouse=True)
def _clear_client_cache():
    # _get_client는 lru_cache 싱글턴 - 매 테스트 시작 전에 비워 이전 테스트의
    # 설정으로 만든 캐시가 새 테스트에 새어들지 않게 한다(setup만으로 격리 충분).
    r2_service._get_client.cache_clear()


def test_episode_page_key_format_and_uniqueness():
    # 파일명은 uuid - 같은 인자로 불러도 호출마다 새 키(D3 리뷰: 순번 파일명은
    # 동시 업로드가 같은 키를 계산해 살아있는 객체를 덮어쓰는 구멍이라 폐기).
    work_id, episode_id = uuid.uuid4(), uuid.uuid4()
    key1 = r2_service.episode_page_key(work_id, episode_id)
    key2 = r2_service.episode_page_key(work_id, episode_id)
    prefix = f"works/{work_id}/episodes/{episode_id}/"
    assert key1.startswith(prefix)
    assert key1.endswith(".webp")
    assert key1 != key2


def test_cover_key_format():
    work_id = uuid.uuid4()
    assert r2_service.cover_key(work_id) == f"works/{work_id}/cover.webp"


async def test_upload_bytes_calls_put_object_and_returns_key(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(r2_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(r2_service.settings, "r2_bucket", "test-bucket")

    key = await r2_service.upload_bytes("works/w/cover.webp", b"payload")

    assert key == "works/w/cover.webp"
    fake_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="works/w/cover.webp",
        Body=b"payload",
        ContentType="image/webp",
    )


async def test_upload_bytes_custom_content_type(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(r2_service, "_get_client", lambda: fake_client)

    await r2_service.upload_bytes("k", b"d", content_type="image/png")

    assert fake_client.put_object.call_args.kwargs["ContentType"] == "image/png"


async def test_upload_bytes_explicit_bucket_overrides_default(monkeypatch):
    # 표지·썸네일 등 공개 자산은 호출자가 bucket=을 명시해 원고 버킷과 분리한다(M2 D1).
    fake_client = MagicMock()
    monkeypatch.setattr(r2_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(r2_service.settings, "r2_bucket", "dweb")

    await r2_service.upload_bytes("works/w/cover.webp", b"payload", bucket="dweb-cover")

    assert fake_client.put_object.call_args.kwargs["Bucket"] == "dweb-cover"


async def test_upload_bytes_bucket_omitted_keeps_default(monkeypatch):
    # bucket 생략 시 원고 버킷(r2_bucket) 유지 - D1 도입이 기존 원고 업로드 경로를
    # 회귀시키지 않아야 한다.
    fake_client = MagicMock()
    monkeypatch.setattr(r2_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(r2_service.settings, "r2_bucket", "dweb")

    await r2_service.upload_bytes("works/w/episodes/e/p.webp", b"payload")

    assert fake_client.put_object.call_args.kwargs["Bucket"] == "dweb"


def test_public_url_none_when_key_missing(monkeypatch):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "https://cover.example.com")
    assert r2_service.public_url(None) is None


def test_public_url_none_when_base_unset(monkeypatch):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "")
    assert r2_service.public_url("works/x/cover.webp") is None


def test_public_url_trailing_slash_normalized(monkeypatch):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "https://cover.example.com/")
    assert (
        r2_service.public_url("works/x/cover.webp")
        == "https://cover.example.com/works/x/cover.webp"
    )


def test_public_url_without_version_has_no_query(monkeypatch):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "https://cover.example.com")
    assert (
        r2_service.public_url("works/x/cover.webp")
        == "https://cover.example.com/works/x/cover.webp"
    )


def test_public_url_with_version_appends_cache_buster(monkeypatch):
    monkeypatch.setattr(r2_service.settings, "public_asset_base_url", "https://cover.example.com")
    version = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
    url = r2_service.public_url("works/x/cover.webp", version=version)
    assert url == f"https://cover.example.com/works/x/cover.webp?v={int(version.timestamp())}"


def test_get_client_unconfigured_raises(monkeypatch):
    # 자격증명 셋 중 하나만 비어도 미설정으로 취급(전부 AND 조건).
    monkeypatch.setattr(r2_service.settings, "r2_access_key_id", "")
    with pytest.raises(r2_service.R2NotConfiguredError):
        r2_service._get_client()


async def test_upload_bytes_unconfigured_raises(monkeypatch):
    # 업로드 경로도 미설정이면 put 시도 전에 명확히 실패한다.
    monkeypatch.setattr(r2_service.settings, "r2_endpoint", "")
    with pytest.raises(r2_service.R2NotConfiguredError):
        await r2_service.upload_bytes("k", b"d")


def test_get_client_rejects_endpoint_with_bucket_path(monkeypatch):
    # 대시보드 'S3 API' 주소(끝에 /버킷명)를 그대로 넣는 오설정은 에러 없이
    # 모든 키가 어긋나게 저장되는 조용한 오염이므로 첫 사용 시 거부해야 한다.
    monkeypatch.setattr(r2_service.settings, "r2_access_key_id", "a" * 32)
    monkeypatch.setattr(r2_service.settings, "r2_secret_access_key", SecretStr("b" * 64))
    monkeypatch.setattr(
        r2_service.settings,
        "r2_endpoint",
        "https://acct.r2.cloudflarestorage.com/dweb",
    )
    with pytest.raises(r2_service.R2NotConfiguredError, match="경로"):
        r2_service._get_client()


async def test_presign_get_urls_order_and_params(monkeypatch):
    # 입력 키 순서 = 출력 URL 순서(image_keys 배열이 순서 진실 - 라우터가 zip으로 짝지음).
    fake_client = MagicMock()
    fake_client.generate_presigned_url.side_effect = lambda *a, **kw: (
        f"https://signed.example/{kw['Params']['Key']}"
    )
    monkeypatch.setattr(r2_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(r2_service.settings, "r2_bucket", "test-bucket")

    urls = await r2_service.presign_get_urls(["k1", "k2"])

    assert urls == ["https://signed.example/k1", "https://signed.example/k2"]
    first = fake_client.generate_presigned_url.call_args_list[0]
    assert first.args[0] == "get_object"
    assert first.kwargs["Params"] == {"Bucket": "test-bucket", "Key": "k1"}
    assert first.kwargs["ExpiresIn"] == r2_service.PRESIGN_GET_EXPIRES


async def test_presign_get_urls_empty_short_circuit(monkeypatch):
    # 빈 목록은 클라이언트 획득 전에 [] - 이미지 0장 draft 조회가 R2 미설정 환경(CI)에서도 안전.
    monkeypatch.setattr(r2_service.settings, "r2_access_key_id", "")
    assert await r2_service.presign_get_urls([]) == []


async def test_presign_get_urls_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(r2_service.settings, "r2_endpoint", "")
    with pytest.raises(r2_service.R2NotConfiguredError):
        await r2_service.presign_get_urls(["k"])
