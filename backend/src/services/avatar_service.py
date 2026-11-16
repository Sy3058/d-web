"""독자 아바타 전용 제한 디코더. 원고의 unrestricted/draft 경로와 분리한다."""

from io import BytesIO

from anyio import to_thread
from PIL import Image, ImageOps, UnidentifiedImageError

from src.lib.exceptions import ImageValidationError

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000
AVATAR_SIZE = 256


def _convert_sync(data: bytes) -> bytes:
    if len(data) > MAX_AVATAR_BYTES:
        raise ImageValidationError("프로필 이미지는 최대 5MB까지 업로드할 수 있습니다")
    try:
        # formats 제한은 JPEG2000/OpenJPEG 등 불필요한 디코더 진입도 막는다.
        with Image.open(BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as source:
            if source.width * source.height > MAX_AVATAR_PIXELS:
                raise ImageValidationError("프로필 이미지 해상도는 최대 1600만 픽셀입니다")
            if getattr(source, "is_animated", False):
                raise ImageValidationError("정적 이미지만 사용할 수 있습니다")
            # JPEG draft 축소 디코드는 사용하지 않는다. 제한 확인 후 전체 디코드한다.
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image = ImageOps.fit(
                image,
                (AVATAR_SIZE, AVATAR_SIZE),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            image.info.clear()
            output = BytesIO()
            image.save(output, format="WEBP", quality=85)
            return output.getvalue()
    except ImageValidationError:
        raise
    except Image.DecompressionBombError as exc:
        raise ImageValidationError("프로필 이미지 해상도가 허용 범위를 초과합니다") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ImageValidationError("JPEG, PNG 또는 정적 WebP 이미지를 선택해 주세요") from exc


async def convert_avatar(data: bytes) -> bytes:
    return await to_thread.run_sync(_convert_sync, data)
