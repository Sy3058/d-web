"""관리자 이미지 업로드 공용 배관 (M1.5 D3).

admin_works(표지)·admin_episodes(페이지)가 공유한다. 도메인 라우터 안에 두면
형제 라우터가 사설 이름을 cross-import하게 되고(역방향 import가 생기는 순간
순환 import로 부팅 실패), 크기 상한 검사가 image_service와 중복돼 경로별로
다른 상한·문구로 갈라질 수 있어 lib로 승격했다(2026-07-10 리뷰 ⑩).
"""

from fastapi import HTTPException, UploadFile, status

from src.services import image_service

R2_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="이미지 저장소가 설정되지 않았습니다 - 운영자에게 문의하세요",
)


async def read_image_upload(upload: UploadFile) -> bytes:
    """업로드 파일을 장당 상한+1바이트까지만 메모리에 읽는다(바운디드 read).

    자체 크기 검사·에러는 없다 - 상한+1바이트로 잘린 데이터는 image_service의
    len 검사(단일 출처, 같은 상수)가 거부한다. Starlette은 핸들러 진입 전에
    바디를 (대용량은 디스크 스풀로) 이미 수신해 두므로, 여기서 막는 것은
    수신이 아니라 **메모리 통짜 로드**다.
    """
    return await upload.read(image_service.MAX_IMAGE_BYTES + 1)
