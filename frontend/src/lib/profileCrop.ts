import type { Area } from 'react-easy-crop';

const OUTPUT_SIZE = 256;
const MAX_IMAGE_PIXELS = 16_000_000;

/** Only the selected square is re-encoded; source metadata is not copied. */
export async function getProfileCroppedFile(imageSrc: string, area: Area): Promise<File> {
  if (![area.x, area.y, area.width, area.height].every(Number.isFinite)
    || area.x < 0 || area.y < 0 || area.width <= 0 || area.height <= 0
    || Math.abs(area.width - area.height) > 1) {
    throw new Error('Invalid crop area');
  }
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const source = new Image();
    source.onload = () => resolve(source);
    source.onerror = () => reject(new Error('Image could not be loaded'));
    source.src = imageSrc;
  });
  const { naturalWidth: width, naturalHeight: height } = image;
  if (!width || !height || width * height > MAX_IMAGE_PIXELS
    || area.x + area.width > width || area.y + area.height > height) {
    throw new Error('Image or crop dimensions are invalid');
  }
  // Pixel rounding may differ by one pixel. Keep the output square without stretching.
  const size = Math.min(area.width, area.height);
  const x = area.x + (area.width - size) / 2;
  const y = area.y + (area.height - size) / 2;
  const canvas = document.createElement('canvas');
  canvas.width = OUTPUT_SIZE;
  canvas.height = OUTPUT_SIZE;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas is unavailable');
  context.drawImage(image, x, y, size, size, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('Image encoding failed');
  return new File([blob], 'profile.png', { type: 'image/png' });
}
