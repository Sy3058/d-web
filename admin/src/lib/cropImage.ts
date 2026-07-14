import type { Area } from 'react-easy-crop';

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener('load', () => resolve(image));
    image.addEventListener('error', reject);
    image.src = src;
  });
}

// 서버가 표지를 800px WebP로 변환하므로(backend image_service) 그보다 큰 원본을 올리는 건
// 낭비다. 여유를 두고 1600px로 캡하면 업로드가 가벼워지고, 잘라낸 JPEG이 서버의 장당 용량
// 상한을 넘겨 422로 거부되는 경우도 애초에 안 생긴다.
const MAX_OUTPUT_WIDTH = 1600;

/** react-easy-crop이 계산한 픽셀 영역(croppedAreaPixels)을 실제로 canvas에 그려
 * 잘라낸 이미지 File로 만든다. 표지 업로드는 이 결과 파일을 그대로 서버에 보낸다. */
export async function getCroppedImageFile(
  imageSrc: string,
  area: Area,
  fileName = 'cover.jpg',
): Promise<File> {
  const image = await loadImage(imageSrc);
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, MAX_OUTPUT_WIDTH / area.width);
  // canvas 크기는 정수여야 한다(소수는 잘려 나가 그린 결과와 어긋난다).
  canvas.width = Math.round(area.width * scale);
  canvas.height = Math.round(area.height * scale);

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('canvas context를 가져올 수 없습니다');
  }
  ctx.drawImage(
    image,
    area.x,
    area.y,
    area.width,
    area.height,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, 'image/jpeg', 0.92);
  });
  if (!blob) {
    throw new Error('이미지 crop에 실패했습니다');
  }
  return new File([blob], fileName, { type: 'image/jpeg' });
}
