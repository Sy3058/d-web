export function safeProfileImageUrl(value: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if ((url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password) return value;
  } catch { /* 잘못된 이전 이미지는 기본 프로필로 표시한다. */ }
  return undefined;
}
