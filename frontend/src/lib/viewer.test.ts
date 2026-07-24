import { describe, expect, it } from 'vitest';
import { clampBlockIndex, imageFetchPriority, isLoggedIn } from './viewer';

describe('imageFetchPriority', () => {
  it('앞 3장(0,1,2번째 이미지)은 high', () => {
    expect(imageFetchPriority(0)).toBe('high');
    expect(imageFetchPriority(1)).toBe('high');
    expect(imageFetchPriority(2)).toBe('high');
  });

  it('4번째 이미지부터는 low', () => {
    expect(imageFetchPriority(3)).toBe('low');
    expect(imageFetchPriority(10)).toBe('low');
  });
});

describe('clampBlockIndex', () => {
  it('범위 안이면 그대로 반환한다', () => {
    expect(clampBlockIndex(3, 10)).toBe(3);
  });

  it('음수는 0으로 자른다', () => {
    expect(clampBlockIndex(-5, 10)).toBe(0);
  });

  it('블록 수를 넘으면 마지막 인덱스로 자른다(본문 축소 후 stale page_no)', () => {
    expect(clampBlockIndex(99, 10)).toBe(9);
  });

  it('블록이 0개면 0을 반환한다(빈 문서 방어)', () => {
    expect(clampBlockIndex(5, 0)).toBe(0);
  });
});

describe('isLoggedIn', () => {
  it('login_hint 쿠키가 있으면 true', () => {
    expect(isLoggedIn('login_hint=%EB%8F%84%EA%B5%B0')).toBe(true);
  });

  it('다른 쿠키들 사이에 섞여 있어도 찾는다', () => {
    expect(isLoggedIn('theme=dark; login_hint=abc; foo=bar')).toBe(true);
  });

  it('없으면 false', () => {
    expect(isLoggedIn('theme=dark; foo=bar')).toBe(false);
  });

  it('빈 문자열이면 false', () => {
    expect(isLoggedIn('')).toBe(false);
  });
});
