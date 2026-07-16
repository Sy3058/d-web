// 서버(image_service.MAX_IMAGES_PER_EPISODE / lib/uploads 20MB)와 같은 값.
// 클라 검증은 UX 보조이고 최종 강제는 서버(409/422)다.
export const MAX_IMAGES_PER_EPISODE = 50;
export const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** 삽입 전 클라 측 사전검증. 문제가 있으면 사용자용 메시지, 없으면 null. */
export function validateImageFile(file: File): string | null {
  if (!file.type.startsWith('image/')) return `${file.name}: 이미지 파일이 아닙니다.`;
  if (file.size > MAX_IMAGE_BYTES) return `${file.name}: 장당 20MB를 넘습니다.`;
  return null;
}
