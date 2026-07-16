/** 이미지 key -> presigned URL 해석 저장소. 이미지 노드뷰가 useSyncExternalStore로 구독한다.
 *
 * React context가 ReactNodeViewRenderer 노드뷰까지 전파된다는 보장이 공식 문서에 없어(v3),
 * 에디터 생성 시 확장 옵션으로 주입되는 안정적 인스턴스 + 구독 모델을 쓴다. 인스턴스는 고정이고
 * 내용(map)만 바뀌므로, URL이 지연 로딩(presigned refetch)돼도 구독자가 리렌더된다.
 * URL은 만료되는 일회성 값이라 문서(content)에는 절대 넣지 않고 여기서만 들고 있는다. */
export interface ImageUrlStore {
  get(key: string): string | undefined;
  set(entries: Iterable<readonly [string, string]>): void;
  subscribe(listener: () => void): () => void;
}

export function createImageUrlStore(): ImageUrlStore {
  const map = new Map<string, string>();
  const listeners = new Set<() => void>();
  return {
    get: (key) => map.get(key),
    set(entries) {
      for (const [key, url] of entries) map.set(key, url);
      for (const listener of listeners) listener();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
