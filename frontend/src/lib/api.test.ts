import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApi } from '@d-web/shared';
import { resolveApiBaseUrl } from './api';

afterEach(() => vi.unstubAllGlobals());

it('프로필 PUT는 인증 갱신 뒤 같은 multipart 본문으로 한 번만 재시도한다', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response('', { status: 401 }))
    .mockResolvedValueOnce(new Response('{}'))
    .mockResolvedValueOnce(new Response('{"nickname":"새 닉네임"}'));
  vi.stubGlobal('fetch', fetchMock);
  const body = new FormData();
  body.append('nickname', '새 닉네임');
  body.append('file', new Blob(['image'], { type: 'image/png' }), 'profile.png');
  const client = createApi('https://api.example.com');
  await expect(client.put('/auth/me/profile', undefined, { body })).resolves
    .toEqual({ nickname: '새 닉네임' });
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    'https://api.example.com/auth/me/profile', 'https://api.example.com/auth/refresh',
    'https://api.example.com/auth/me/profile',
  ]);
  for (const index of [0, 2]) {
    expect(fetchMock.mock.calls[index][1]).toMatchObject({ method: 'PUT', credentials: 'include', body });
    expect(new Headers(fetchMock.mock.calls[index][1].headers).has('Content-Type')).toBe(false);
  }
});

it('이미지 업로드는 FormData를 유지하고 multipart 경계를 직접 지정하지 않는다', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'));
  vi.stubGlobal('fetch', fetchMock);
  const body = new FormData();
  body.append('file', new Blob(['image'], { type: 'image/png' }), 'profile.png');
  await createApi('https://api.example.com').put('/auth/me/profile', undefined, { body });
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT', body, credentials: 'include' });
  expect(new Headers(fetchMock.mock.calls[0][1].headers).has('Content-Type')).toBe(false);
});

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
