"""r2_service 단위 테스트 (M1.5 D1).

R2 호출은 전부 mock - 어떤 테스트도 실제 네트워크에 나가지 않는다(hermetic,
CI엔 R2 자격증명이 없다). 실버킷 연결은 2026-07-10 스모크(put/get/delete)로 기확인.
"""

import uuid
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
