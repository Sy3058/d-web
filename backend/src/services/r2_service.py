"""Cloudflare R2 업로드 서비스 (M1.5 D1).

boto3(S3 호환) 동기 SDK를 anyio.to_thread로 오프로드한다(M1 bcrypt와 같은
루프 비블로킹 패턴). presigned PUT 직업로드는 미채택 - 클라가 R2로 직접 올리면
서버가 바이트를 못 봐 변환(ADM-03 서버 변환)이 불가능하다(M1.5 결정 1).
aioboto3는 대량 동시 업로드가 필요해질 때 재검토(1인 작가 저빈도 업로드).

여기는 업로드(PUT)만 담당한다 - Signed URL(GET) 발급은 M3(결제·잠금) 소관.
키는 공개 URL이 아니며 비관리자에게 직접 반환하지 않는다(episodes.image_keys에
키만 저장).

키 스킴 (M1.5 D1 확정):
- 에피소드 페이지: works/{work_id}/episodes/{episode_id}/{page:03d}.webp
  (episode_id=UUID 기준이라 episode_no를 나중에 바꿔도 키가 안정)
- 표지: works/{work_id}/cover.webp
"""

import uuid
from functools import lru_cache, partial
from urllib.parse import urlparse

import boto3
from anyio import to_thread
from botocore.config import Config as BotoConfig

from src.config import settings

WEBP_CONTENT_TYPE = "image/webp"


class R2NotConfiguredError(RuntimeError):
    """R2 자격증명 미설정 상태에서 업로드를 시도했을 때.

    부팅은 무자격 환경(CI·로컬)에서도 허용하고, 실제 사용 시점에만 실패시킨다.
    운영자 설정 문제(5xx)이지 클라이언트 귀책(4xx)이 아니다.
    """


def episode_page_key(work_id: uuid.UUID, episode_id: uuid.UUID, page: int) -> str:
    """에피소드 페이지 키. page는 0부터 시작(image_keys 배열 인덱스와 동일).

    범위 가드는 3자리 zero-pad 계약 보호: 1000은 4자리("1000.webp")로 패딩이
    조용히 깨지고 음수는 "-01.webp"가 된다. 회차당 상한(50)보다 훨씬 넉넉하므로
    정상 경로에선 닿지 않는다(리뷰 하드닝).
    """
    if not 0 <= page <= 999:
        raise ValueError(f"page는 0~999 범위여야 한다: {page}")
    return f"works/{work_id}/episodes/{episode_id}/{page:03d}.webp"


def cover_key(work_id: uuid.UUID) -> str:
    """작품 표지 키. 작품당 1개 - 재업로드는 같은 키를 덮어쓴다."""
    return f"works/{work_id}/cover.webp"


def is_configured() -> bool:
    """R2 자격증명·endpoint가 채워졌는가. main.py production 부팅 경고와 공유."""
    return bool(
        settings.r2_access_key_id
        and settings.r2_secret_access_key.get_secret_value()
        and settings.r2_endpoint
    )


@lru_cache(maxsize=1)
def _get_client():
    """S3 호환 클라이언트 싱글턴(프로세스당 1회 생성, boto3 클라이언트는 스레드 안전).

    eager(모듈 로드 시) 생성이 아닌 이유: 무자격 환경(CI·R2 없는 로컬)에서
    import만으로 죽으면 안 되기 때문. 대신 첫 생성은 콜드 ~60ms(botocore 서비스
    정의 파싱)라 반드시 to_thread 안에서 호출한다(upload_bytes - 루프 블로킹 금지).
    """
    if not is_configured():
        raise R2NotConfiguredError(
            "R2 미설정: R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT를 .env에 채울 것"
        )
    if urlparse(settings.r2_endpoint).path not in ("", "/"):
        # 대시보드 '버킷 Settings > S3 API' 주소는 끝에 /<버킷명>이 붙어 있다. 그대로
        # 넣으면 boto3가 버킷을 한 번 더 덧붙여(PUT /dweb/dweb/works/...) R2가 첫
        # 세그먼트를 버킷으로 해석 - 에러 없이 성공하면서 모든 키가 어긋나게 저장되는
        # 조용한 오염이라(리뷰 실측) 첫 사용 시점에 명시적으로 거부한다.
        raise R2NotConfiguredError(
            "R2_ENDPOINT에 경로가 붙어 있음 - 버킷명을 뺀 "
            "https://<account-id>.r2.cloudflarestorage.com 형태여야 함"
        )
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
        # R2는 리전 개념이 없어 "auto" 고정(Cloudflare 문서).
        region_name="auto",
        config=BotoConfig(
            connect_timeout=10,
            read_timeout=60,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _put_object_sync(key: str, data: bytes, content_type: str) -> None:
    # _get_client()도 이 안에서: 첫 클라이언트 생성(콜드 ~60ms)이 이벤트 루프를
    # 블로킹하지 않도록 획득과 호출을 함께 스레드로 보낸다(리뷰 실측 62.7ms).
    _get_client().put_object(
        Bucket=settings.r2_bucket, Key=key, Body=data, ContentType=content_type
    )


async def upload_bytes(key: str, data: bytes, content_type: str = WEBP_CONTENT_TYPE) -> str:
    """바이트를 R2에 업로드하고 저장된 키를 그대로 반환한다.

    같은 키 재업로드는 덮어쓰기(S3 PUT 시맨틱). 다건 업로드의 부분 실패
    처리(완료분 키 수집 → DB 1회 커밋)는 호출자(D3 episode_service) 책임.
    """
    await to_thread.run_sync(partial(_put_object_sync, key, data, content_type))
    return key
