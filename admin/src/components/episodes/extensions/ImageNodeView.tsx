import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { useSyncExternalStore } from 'react';
import type { ImageUrlStore } from '../imageUrlStore';

const NOOP_SUBSCRIBE = () => () => {};

export function ImageNodeView({ node, extension, selected }: NodeViewProps) {
  const store = (extension.options as { store: ImageUrlStore | null }).store;
  const key = node.attrs.key as string | null;
  // presigned URL은 지연 로딩(업로드 직후엔 로컬 blob, 이후 refetch로 교체)이라 store 구독으로 반영.
  const url = useSyncExternalStore(
    store ? store.subscribe : NOOP_SUBSCRIBE,
    () => (store && key ? store.get(key) : undefined),
    () => undefined,
  );
  return (
    <NodeViewWrapper
      data-drag-handle
      className={`my-2 overflow-hidden rounded border ${selected ? 'border-gray-900' : 'border-transparent'}`}
    >
      {url ? (
        <img src={url} alt="" draggable={false} className="mx-auto max-h-[70vh] w-auto" />
      ) : (
        <div className="flex h-40 items-center justify-center bg-gray-100 text-sm text-gray-500">
          이미지 불러오는 중...
        </div>
      )}
    </NodeViewWrapper>
  );
}
