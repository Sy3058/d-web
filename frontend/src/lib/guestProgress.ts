const STORAGE_KEY_PREFIX = 'dweb:viewer-progress:v1:';
const MAX_RECORDS = 100;
const PAGE_NO_MAX = 2_147_483_647;
const BLOCK_OFFSET_BP_MAX = 10_000;

export interface GuestProgressRecord {
  pageNo: number;
  blockOffsetBp: number;
  updatedAt: number;
}

export interface GuestWorkProgress {
  readEpisodeIds: string[];
  lastEpisodeId: string | null;
}

function storageKey(episodeId: string): string {
  return `${STORAGE_KEY_PREFIX}${episodeId}`;
}

function isValidRecord(value: unknown): value is GuestProgressRecord {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    Number.isInteger(record.pageNo) &&
    Number(record.pageNo) >= 0 &&
    Number(record.pageNo) <= PAGE_NO_MAX &&
    Number.isInteger(record.blockOffsetBp) &&
    Number(record.blockOffsetBp) >= 0 &&
    Number(record.blockOffsetBp) <= BLOCK_OFFSET_BP_MAX &&
    Number.isSafeInteger(record.updatedAt) &&
    Number(record.updatedAt) >= 0
  );
}

export function parseGuestProgress(raw: string | null): GuestProgressRecord | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return isValidRecord(value) ? value : null;
  } catch {
    return null;
  }
}

export function readGuestProgress(
  storage: Pick<Storage, 'getItem'>,
  episodeId: string,
): GuestProgressRecord | null {
  try {
    return parseGuestProgress(storage.getItem(storageKey(episodeId)));
  } catch {
    return null;
  }
}

function pruneGuestProgress(storage: Storage): void {
  try {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(STORAGE_KEY_PREFIX)) keys.push(key);
    }

    const records = keys.flatMap((key) => {
      const record = parseGuestProgress(storage.getItem(key));
      if (record) return [{ key, updatedAt: record.updatedAt }];
      storage.removeItem(key);
      return [];
    });
    records.sort((a, b) => a.updatedAt - b.updatedAt || a.key.localeCompare(b.key));

    for (const record of records.slice(0, Math.max(0, records.length - MAX_RECORDS))) {
      storage.removeItem(record.key);
    }
  } catch {
    // 읽기 위치는 부가 UX다. storage 접근 실패가 열람을 막아서는 안 된다.
  }
}

export function writeGuestProgress(
  storage: Storage,
  episodeId: string,
  pageNo: number,
  blockOffsetBp: number,
  updatedAt = Date.now(),
): void {
  const record = { pageNo, blockOffsetBp, updatedAt };
  if (!episodeId || !isValidRecord(record)) return;

  try {
    storage.setItem(storageKey(episodeId), JSON.stringify(record));
  } catch {
    return;
  }
  pruneGuestProgress(storage);
}

export function selectGuestWorkProgress(
  storage: Pick<Storage, 'getItem'>,
  episodeIds: readonly string[],
): GuestWorkProgress {
  const readEpisodeIds: string[] = [];
  let lastEpisodeId: string | null = null;
  let lastUpdatedAt = -1;

  for (const episodeId of episodeIds) {
    const record = readGuestProgress(storage, episodeId);
    if (!record) continue;
    readEpisodeIds.push(episodeId);
    // 같은 millisecond면 작가 지정 순서에서 뒤쪽 회차를 결정적인 tie-breaker로 사용한다.
    if (record.updatedAt >= lastUpdatedAt) {
      lastEpisodeId = episodeId;
      lastUpdatedAt = record.updatedAt;
    }
  }

  return { readEpisodeIds, lastEpisodeId };
}

function withBrowserStorage<T>(fallback: T, action: (storage: Storage) => T): T {
  try {
    return action(window.localStorage);
  } catch {
    return fallback;
  }
}

export function getBrowserGuestProgress(episodeId: string): GuestProgressRecord | null {
  return withBrowserStorage(null, (storage) => readGuestProgress(storage, episodeId));
}

export function putBrowserGuestProgress(
  episodeId: string,
  pageNo: number,
  blockOffsetBp: number,
): void {
  withBrowserStorage(undefined, (storage) =>
    writeGuestProgress(storage, episodeId, pageNo, blockOffsetBp),
  );
}

export function getBrowserGuestWorkProgress(
  episodeIds: readonly string[],
): GuestWorkProgress {
  return withBrowserStorage(
    { readEpisodeIds: [], lastEpisodeId: null },
    (storage) => selectGuestWorkProgress(storage, episodeIds),
  );
}
