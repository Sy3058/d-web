import { describe, expect, it } from 'vitest';
import {
  parseGuestProgress,
  readGuestProgress,
  selectGuestWorkProgress,
  writeGuestProgress,
} from './guestProgress';

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

const key = (episodeId: string) => `dweb:viewer-progress:v1:${episodeId}`;

describe('guest progress storage', () => {
  it('유효한 레코드를 저장하고 읽는다', () => {
    const storage = new MemoryStorage();

    writeGuestProgress(storage, 'episode-a', 4, 6_000, 123_456);

    expect(readGuestProgress(storage, 'episode-a')).toEqual({
      pageNo: 4,
      blockOffsetBp: 6_000,
      updatedAt: 123_456,
    });
  });

  it.each([
    ['손상 JSON', '{'],
    ['배열', '[]'],
    ['음수 pageNo', '{"pageNo":-1,"blockOffsetBp":0,"updatedAt":1}'],
    ['과대 pageNo', '{"pageNo":2147483648,"blockOffsetBp":0,"updatedAt":1}'],
    ['소수 pageNo', '{"pageNo":1.5,"blockOffsetBp":0,"updatedAt":1}'],
    ['음수 offset', '{"pageNo":0,"blockOffsetBp":-1,"updatedAt":1}'],
    ['과대 offset', '{"pageNo":0,"blockOffsetBp":10001,"updatedAt":1}'],
    ['잘못된 updatedAt', '{"pageNo":0,"blockOffsetBp":0,"updatedAt":"1"}'],
  ])('%s 레코드는 무시한다', (_label, raw) => {
    expect(parseGuestProgress(raw)).toBeNull();
  });

  it('getItem SecurityError를 복원값 없음으로 처리한다', () => {
    const storage = {
      getItem() {
        throw new DOMException('blocked', 'SecurityError');
      },
    };

    expect(readGuestProgress(storage, 'episode-a')).toBeNull();
  });

  it('quota 초과로 저장하지 못해도 예외를 전파하지 않는다', () => {
    const storage = new MemoryStorage();
    storage.setItem = () => {
      throw new DOMException('full', 'QuotaExceededError');
    };

    expect(() => writeGuestProgress(storage, 'episode-a', 1, 2_000, 1)).not.toThrow();
    expect(storage.length).toBe(0);
  });

  it('101번째 유효 레코드 저장 후 updatedAt이 가장 오래된 항목을 제거한다', () => {
    const storage = new MemoryStorage();
    for (let index = 0; index < 101; index += 1) {
      writeGuestProgress(storage, `episode-${index}`, index, 0, index);
    }

    expect(storage.length).toBe(100);
    expect(storage.getItem(key('episode-0'))).toBeNull();
    expect(storage.getItem(key('episode-1'))).not.toBeNull();
    expect(storage.getItem(key('episode-100'))).not.toBeNull();
  });

  it('정리할 때 손상된 현재 버전 레코드도 제거한다', () => {
    const storage = new MemoryStorage();
    storage.setItem(key('broken'), '{');

    writeGuestProgress(storage, 'episode-a', 1, 0, 1);

    expect(storage.getItem(key('broken'))).toBeNull();
    expect(storage.getItem(key('episode-a'))).not.toBeNull();
  });

  it('동률 updatedAt은 episode 목록의 뒤쪽 회차를 최근 회차로 고른다', () => {
    const storage = new MemoryStorage();
    writeGuestProgress(storage, 'public-a', 1, 0, 100);
    writeGuestProgress(storage, 'hidden', 2, 0, 999);
    writeGuestProgress(storage, 'public-b', 3, 0, 100);
    storage.setItem(
      'dweb:viewer-progress:v0:legacy',
      JSON.stringify({ pageNo: 9, blockOffsetBp: 0, updatedAt: 1_000 }),
    );

    expect(selectGuestWorkProgress(storage, ['public-a', 'public-b', 'public-c'])).toEqual({
      readEpisodeIds: ['public-a', 'public-b'],
      lastEpisodeId: 'public-b',
    });
  });

  it('손상된 현재 버전 레코드는 작품 진행도에서도 제외한다', () => {
    const storage = new MemoryStorage();
    storage.setItem(key('episode-a'), '{broken');

    expect(selectGuestWorkProgress(storage, ['episode-a'])).toEqual({
      readEpisodeIds: [],
      lastEpisodeId: null,
    });
  });
});
