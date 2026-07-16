import { Node, mergeAttributes } from '@tiptap/core';
import { ReactNodeViewRenderer } from '@tiptap/react';
import type { ImageUrlStore } from '../imageUrlStore';
import { ImageNodeView } from './ImageNodeView';

export interface EpisodeImageOptions {
  store: ImageUrlStore | null;
}

/** 본문 이미지 노드. attrs는 key 하나뿐 - 서버 화이트리스트(_ALLOWED_NODE_ATTRS image={key})와
 * 일치한다. 표시용 URL은 문서에 저장하지 않고 store에서 해석한다(만료값 캐시 금지). */
export const EpisodeImage = Node.create<EpisodeImageOptions>({
  name: 'image',
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,
  addOptions() {
    return { store: null };
  },
  addAttributes() {
    return { key: { default: null } };
  },
  parseHTML() {
    return [
      {
        tag: 'img[data-key]',
        getAttrs: (el) => ({ key: (el as HTMLElement).getAttribute('data-key') }),
      },
    ];
  },
  renderHTML({ HTMLAttributes }) {
    return ['img', mergeAttributes({ 'data-key': HTMLAttributes.key })];
  },
  addNodeView() {
    return ReactNodeViewRenderer(ImageNodeView);
  },
});
