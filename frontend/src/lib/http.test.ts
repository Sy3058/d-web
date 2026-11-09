import { expect, it } from 'vitest';
import { applyCatalogCache } from './http';

it('조회 장애와 빈 결과가 겹치면 404 대신 재시도 가능한 503/no-store다', () => {
  const response = { status: 200, headers: new Headers() };
  applyCatalogCache(response, { error: true, notFound: true });
  expect(response.status).toBe(503);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
});

it('확정된 리소스 누락은 404/no-store다', () => {
  const response = { status: 200, headers: new Headers() };
  applyCatalogCache(response, { notFound: true });
  expect(response.status).toBe(404);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
});

it('정상 공개 메타는 기존 60초 공유 캐시를 유지한다', () => {
  const response = { status: 200, headers: new Headers() };
  applyCatalogCache(response, {});
  expect(response.status).toBe(200);
  expect(response.headers.get('Cache-Control')).toBe('public, max-age=60');
});
