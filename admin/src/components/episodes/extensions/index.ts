import StarterKit from '@tiptap/starter-kit';
import type { Extensions } from '@tiptap/core';
import type { ImageUrlStore } from '../imageUrlStore';
import { EpisodeImage } from './image';
import { Paywall } from './paywall';
import { WhitelistLink } from './link';

// 서버 화이트리스트(backend lib/content_doc)와 1:1로 맞춘 확장 집합.
// StarterKit이 v3부터 포함하는 노드/마크 중 화이트리스트 밖(heading·목록·codeBlock·code 마크)을
// 끈다 - 안 끄면 마크다운 단축키(#, -, ```)로 서버가 422로 거부하는 노드를 만들 수 있다.
export function buildEditorExtensions(store: ImageUrlStore | null): Extensions {
  return [
    StarterKit.configure({
      heading: false,
      blockquote: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      codeBlock: false,
      code: false,
      link: false, // href-only 커스텀 Link(WhitelistLink)로 교체
    }),
    WhitelistLink,
    EpisodeImage.configure({ store }),
    Paywall,
  ];
}
