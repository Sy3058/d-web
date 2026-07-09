"""이미지 변환 서비스 (M1.5 D2).

원본 이미지를 가로 800px WebP로 변환한다(ADM-03 서버 변환 - M1.5 결정 1·2).
Pillow는 CPU 바운드라 anyio.to_thread로 오프로드한다 - 이벤트 루프 비블로킹일 뿐
병렬 가속이 아니므로(GIL) 요청 응답은 장수만큼 합산 시간을 기다린다(50장 ≈ 수 초,
F3 진행바로 커버). 변환이 일관되게 길어지면 Arq 워커 분리(결정 2 escalation).
"""

from io import BytesIO

from anyio import to_thread
from PIL import Image, ImageOps, UnidentifiedImageError

from src.lib.exceptions import ImageValidationError

# ── 검증 상한 (개수/크기 상수 - 금액 아님, 하드코딩 금지 규칙 비저촉) ──────────
# 장당 원본 바이트 상한. 웹툰 원고 1장(JPEG/PNG)은 보통 수 MB - 20MB면 넉넉하고,
# 그 이상은 원고가 아니라 실수(무압축 TIFF 등)이거나 악의적 입력이다.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
# 원본 해상도(픽셀 수) 상한 - decompression bomb 방어. 헤더의 크기 선언만으로
# 본 디코드 전에 거부한다. 세로 원고 2000x30000=60MP도 통과하는 여유값.
# (이 값의 2.2배쯤인 ~179MP부터는 Pillow 자체 가드가 open 단계에서 먼저 터진다 -
#  그쪽도 같은 "해상도 초과" 메시지로 매핑해 사용자 안내를 일관되게 유지)
MAX_IMAGE_PIXELS = 80_000_000
# 회차당 장수 상한(ADM-03). 실제 개수 검증은 D3 엔드포인트에서 이 상수를 쓴다.
MAX_IMAGES_PER_EPISODE = 50

# ── 변환 규격 ──────────────────────────────────────────────────────────────
TARGET_WIDTH = 800  # 가로 고정, 세로는 비율 유지(ADM-03)
WEBP_QUALITY = 80  # 용량/화질 균형 기본값(실측 후 조정 여지)
# WebP 포맷 자체의 변 길이 한계(스펙 14bit = 16383px). 800px로 줄인 뒤에도
# 세로가 이걸 넘는 초장축 원고는 인코딩 자체가 불가능하므로 분할 업로드를 요구한다.
WEBP_MAX_DIMENSION = 16383

# EXIF Orientation 태그 ID와, 가로세로가 서로 바뀌는(transpose 시 축 교환) 값들.
_ORIENTATION_TAG = 0x0112
_AXIS_SWAP_ORIENTATIONS = (5, 6, 7, 8)


def _maybe_draft_jpeg(img: Image.Image) -> None:
    """대형 JPEG을 DCT 도메인 축소 디코드로 열도록 설정한다(실측 2.8배 가속).

    draft는 JPEG 전용이고 그 외 포맷엔 no-op. 최종 목표(800px)의 2배 여유를
    요청하는 것은 thumbnail()과 같은 품질 관행 - 중간 이미지에서 LANCZOS로
    최종 축소하므로 화질 손실이 없다. EXIF 회전(5~8)은 transpose 후 축이
    바뀌므로 '유효 가로'를 회전 후 기준으로 계산한다(안 하면 회전 원고가
    목표보다 작게 디코드돼 결과 폭이 800 미만으로 어긋난다 - 리뷰 검증).
    """
    if img.format != "JPEG":
        return
    orientation = img.getexif().get(_ORIENTATION_TAG, 1)
    swapped = orientation in _AXIS_SWAP_ORIENTATIONS
    effective_width = img.height if swapped else img.width
    if effective_width <= TARGET_WIDTH * 2:
        return  # 여유 포함 목표 이하 - 축소 디코드 이득 없음
    ratio = (TARGET_WIDTH * 2) / effective_width
    img.draft(
        None,  # 모드는 유지(크기만) - CMYK JPEG 등은 아래 정규화 단계가 처리
        (max(1, round(img.width * ratio)), max(1, round(img.height * ratio))),
    )


def _convert_sync(data: bytes) -> bytes:
    """검증 + 변환 본체(동기). 반드시 to_thread 경유로 호출할 것(convert_to_webp)."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"이미지가 너무 큽니다 (장당 최대 {MAX_IMAGE_BYTES // (1024 * 1024)}MB)"
        )

    try:
        img = Image.open(BytesIO(data))
        # 애니메이션(GIF/APNG/animated WebP)은 변환 시 첫 프레임만 남아
        # 콘텐츠가 조용히 손실되므로 명시 거부한다(리뷰 실측 확인).
        if getattr(img, "is_animated", False):
            raise ImageValidationError("애니메이션 이미지는 지원하지 않습니다 (정적 이미지만)")
        # 헤더의 크기 선언만으로 본 디코드 전에 폭탄 거부(메모리 할당 전).
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise ImageValidationError("이미지 해상도가 허용 범위를 초과합니다")
        _maybe_draft_jpeg(img)
        # 실제 픽셀 디코드 - 비이미지/손상 파일은 여기서 걸린다.
        img.load()
    except ImageValidationError:
        raise
    except Image.DecompressionBombError as exc:
        # Pillow 자체 가드(~179MP)가 우리 검사보다 먼저 터지는 초대형 헤더도
        # 같은 "해상도 초과"로 안내한다(80~179MP 구간과 메시지 일관 - 리뷰).
        raise ImageValidationError("이미지 해상도가 허용 범위를 초과합니다") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("이미지 파일을 해석할 수 없습니다") from exc

    # EXIF 방향을 픽셀에 적용한 뒤(회전 원고 정규화), 메타데이터는 저장 시
    # 전달하지 않아 제거된다(위치정보 등 개인정보 + 뷰어 방향 오동작 방지).
    img = ImageOps.exif_transpose(img)

    # 16비트 그레이스케일(스캔 원고 PNG/TIFF, mode I/I;16*)은 convert("RGB")가
    # 0~65535를 스케일링 없이 255로 클리핑해 백지가 된다(리뷰 실측) - 선형
    # 스케일로 8비트에 내린 뒤 진행한다.
    if img.mode.startswith("I"):
        img = img.convert("I").point(lambda v: v * (255 / 65535)).convert("L")

    # 모드 정규화는 반드시 리사이즈 '전': Pillow는 P(팔레트) 모드 resize에서
    # LANCZOS 지정을 조용히 NEAREST로 강제해 계단 현상이 생긴다(리뷰 실측).
    # 팔레트/그레이스케일+알파는 RGBA로(투명도 보존 - WebP 지원), 그 외
    # 비표준 모드(CMYK·L 등)는 RGB로.
    if img.mode in ("P", "LA", "PA"):
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    if img.width > TARGET_WIDTH:
        ratio = TARGET_WIDTH / img.width
        img = img.resize(
            (TARGET_WIDTH, max(1, round(img.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    # 원본이 800px 이하면 업스케일하지 않는다 - 없는 정보를 만들어내지 못해
    # 화질은 그대로인데 용량만 커진다(구현 결정, 2026-07-10).

    if img.height > WEBP_MAX_DIMENSION:
        raise ImageValidationError(
            f"세로가 너무 깁니다 (변환 후 최대 {WEBP_MAX_DIMENSION}px - 페이지 분할 필요)"
        )

    buf = BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY)  # exif 미전달 = 메타데이터 제거
    return buf.getvalue()


async def convert_to_webp(data: bytes) -> bytes:
    """원본 이미지 바이트 → 가로 최대 800px WebP 바이트.

    검증 실패는 ImageValidationError(클라 귀책). CPU 바운드라 to_thread로
    오프로드 - async def에서 _convert_sync를 직접 호출하지 말 것(MISTAKES 결정 2).
    """
    return await to_thread.run_sync(_convert_sync, data)
