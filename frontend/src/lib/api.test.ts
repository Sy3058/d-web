import { describe, expect, it } from 'vitest';
import { resolveApiBaseUrl } from './api';

describe('API base URL 선택', () => {
  it('SSR은 compose 내부 API 주소를 우선한다', () => {
    expect(
      resolveApiBaseUrl({
        isServer: true,
        publicUrl: 'http://localhost:8000',
        internalUrl: 'http://api:8000',
      }),
    ).toBe('http://api:8000');
  });

  it('브라우저는 내부 호스트를 노출하지 않고 공개 주소를 쓴다', () => {
    expect(
      resolveApiBaseUrl({
        isServer: false,
        publicUrl: 'https://api.example.com',
        internalUrl: 'http://api:8000',
      }),
    ).toBe('https://api.example.com');
  });

  it('로컬 개발에서 내부 주소가 없으면 공개 주소로 폴백한다', () => {
    expect(
      resolveApiBaseUrl({
        isServer: true,
        publicUrl: 'http://localhost:8000',
      }),
    ).toBe('http://localhost:8000');
  });
});
