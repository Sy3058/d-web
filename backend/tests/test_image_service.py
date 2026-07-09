"""image_service 단위 테스트 (M1.5 D2).

Pillow로 테스트 이미지를 메모리에서 생성해 변환 결과(크기·포맷·모드·메타데이터)와
거부 케이스(비이미지·바이트/해상도 초과·초장축)를 검증한다.
"""

from io import BytesIO

import pytest
from PIL import Image

from src.lib.exceptions import ImageValidationError
from src.services import image_service
from src.services.image_service import convert_to_webp


def _img_bytes(
    width: int, height: int, fmt: str = "PNG", mode: str = "RGB", **save_kwargs
) -> bytes:
    buf = BytesIO()
    Image.new(mode, (width, height)).save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def _open(webp: bytes) -> Image.Image:
    return Image.open(BytesIO(webp))


# ── 변환 규격 ──────────────────────────────────────────────────────────────


async def test_wide_image_resized_to_800_keeping_ratio():
    out = _open(await convert_to_webp(_img_bytes(1600, 2400)))
    assert out.format == "WEBP"
    assert out.size == (800, 1200)


async def test_narrow_image_not_upscaled():
    out = _open(await convert_to_webp(_img_bytes(400, 600)))
    assert out.size == (400, 600)


async def test_exact_800_kept():
    out = _open(await convert_to_webp(_img_bytes(800, 100)))
    assert out.size == (800, 100)


async def test_jpeg_input_accepted():
    out = _open(await convert_to_webp(_img_bytes(1000, 500, fmt="JPEG")))
    assert out.format == "WEBP"
    assert out.size == (800, 400)


async def test_exif_orientation_applied_and_metadata_stripped():
    # orientation=6(시계 90도 회전 지시)이 픽셀에 적용돼 가로세로가 뒤집히고,
    # 출력 WebP에는 EXIF가 남지 않아야 한다(개인정보 제거).
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    src = _img_bytes(200, 100, fmt="JPEG", exif=exif)

    out = _open(await convert_to_webp(src))

    assert out.size == (100, 200)
    assert len(out.getexif()) == 0


async def test_alpha_preserved():
    out = _open(await convert_to_webp(_img_bytes(100, 100, mode="RGBA")))
    assert out.mode == "RGBA"


async def test_palette_converted():
    buf = BytesIO()
    Image.new("RGB", (100, 100)).convert("P").save(buf, format="PNG")
    out = _open(await convert_to_webp(buf.getvalue()))
    assert out.mode in ("RGB", "RGBA")


async def test_cmyk_converted_to_rgb():
    out = _open(await convert_to_webp(_img_bytes(100, 100, fmt="JPEG", mode="CMYK")))
    assert out.mode == "RGB"


async def test_16bit_grayscale_scaled_not_clipped():
    # 16비트 스캔 원고: convert("RGB") 직행이면 중간 회색(32768)이 255로 클리핑돼
    # 백지가 된다(리뷰 실측) - 선형 스케일로 ~127 회색이 보존돼야 한다.
    buf = BytesIO()
    Image.new("I;16", (50, 50), color=32768).save(buf, format="PNG")
    out = _open(await convert_to_webp(buf.getvalue()))
    r, g, b = out.convert("RGB").getpixel((25, 25))
    assert 110 <= r <= 145, f"클리핑 의심: {r} (기대 ~127)"


async def test_palette_downscale_uses_smooth_resampling():
    # P 모드는 resize가 LANCZOS를 조용히 NEAREST로 강제한다(Pillow 소스) -
    # 정규화를 리사이즈 앞으로 옮긴 뒤엔 1px 체커보드 2배 축소가 평균(~127)이
    # 나와야 한다. NEAREST면 0 또는 255(위상 선택)가 나온다.
    board = Image.new("RGB", (1600, 100))
    board.putdata(
        [(255, 255, 255) if (x + y) % 2 else (0, 0, 0) for y in range(100) for x in range(1600)]
    )
    buf = BytesIO()
    board.convert("P", palette=Image.Palette.ADAPTIVE).save(buf, format="PNG")
    out = _open(await convert_to_webp(buf.getvalue()))
    assert out.size == (800, 50)
    r, g, b = out.convert("RGB").getpixel((400, 25))
    assert 90 <= r <= 165, f"NEAREST 의심: {r} (기대 ~127 평균)"


async def test_large_jpeg_draft_path_same_output_size():
    # draft(DCT 축소 디코드) 경로가 최종 크기를 바꾸지 않아야 한다(2배 여유 후 LANCZOS).
    out = _open(await convert_to_webp(_img_bytes(4000, 6000, fmt="JPEG")))
    assert out.size == (800, 1200)


async def test_large_rotated_jpeg_draft_respects_orientation():
    # EXIF 회전(6=90도)은 transpose 후 축이 바뀐다 - draft 유효 가로를 회전 후
    # 기준으로 계산하지 않으면 결과 폭이 800 미만으로 어긋난다(리뷰 검증 caveat).
    exif = Image.Exif()
    exif[0x0112] = 6
    out = _open(await convert_to_webp(_img_bytes(4000, 2000, fmt="JPEG", exif=exif)))
    assert out.size == (800, 1600)


# ── 거부 케이스 ────────────────────────────────────────────────────────────


async def test_non_image_rejected():
    with pytest.raises(ImageValidationError):
        await convert_to_webp(b"this is not an image at all")


async def test_empty_bytes_rejected():
    with pytest.raises(ImageValidationError):
        await convert_to_webp(b"")


async def test_oversize_bytes_rejected(monkeypatch):
    # 실제 20MB 이미지를 만들면 느리므로 상한을 낮춰 경로만 검증한다.
    monkeypatch.setattr(image_service, "MAX_IMAGE_BYTES", 10)
    with pytest.raises(ImageValidationError, match="너무 큽니다"):
        await convert_to_webp(_img_bytes(100, 100))


async def test_pixel_bomb_rejected_before_decode(monkeypatch):
    # 헤더 선언 크기 기준 거부 - 실제 80MP 원본 생성 없이 상한만 낮춰 검증.
    monkeypatch.setattr(image_service, "MAX_IMAGE_PIXELS", 100_000)
    with pytest.raises(ImageValidationError, match="해상도"):
        await convert_to_webp(_img_bytes(400, 400))  # 160,000픽셀 > 100,000


async def test_pillow_bomb_error_gets_resolution_message(monkeypatch):
    # 우리 상한(80MP)보다 큰 ~179MP+ 헤더는 Pillow 자체 가드가 open에서 먼저
    # 터진다 - generic "해석 불가"가 아니라 같은 "해상도" 메시지여야 한다(리뷰).
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)  # 2배=2,000픽셀에서 에러
    with pytest.raises(ImageValidationError, match="해상도"):
        await convert_to_webp(_img_bytes(400, 400))  # 160,000 > 2x1,000


async def test_animated_gif_rejected():
    # 애니메이션은 첫 프레임만 남는 조용한 손실이므로 명시 거부(리뷰 실측).
    frames = [Image.new("RGB", (100, 100), c) for c in ((255, 0, 0), (0, 0, 255))]
    buf = BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(ImageValidationError, match="애니메이션"):
        await convert_to_webp(buf.getvalue())


async def test_too_tall_for_webp_rejected():
    # 폭 800 이하(리사이즈 없음) + 세로 16383 초과 → WebP 인코딩 불가 사전 거부.
    with pytest.raises(ImageValidationError, match="세로"):
        await convert_to_webp(_img_bytes(100, 17000))


def test_max_images_constant_for_d3():
    # D3 엔드포인트가 참조할 계약 상수(ADM-03 회차당 50장).
    assert image_service.MAX_IMAGES_PER_EPISODE == 50
