import { Node, mergeAttributes } from '@tiptap/core';
import type { Extensions } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';

// 서버 화이트리스트(backend lib/content_doc)·admin 에디터(admin/.../extensions/index.ts)와
// 1:1로 맞춘 뷰어 렌더 스키마. #76 "서버·에디터·뷰어 3곳 동일 스키마" 규칙에서 image
// attrs만 의도적 예외다(저장은 key, 이 응답은 presigned URL이 담긴 src -
// M2 B2 IMPLEMENTATION_FREE_CONTENT_API.md).
//
// 최상위 image 노드는 이 스키마로 렌더하지 않는다 - Viewer.tsx가 최상위 블록을 분할해
// image는 React <img>로 직접 그린다(즉시 전량 요청 + fetchPriority, 결정 6). 아래 ViewerImage
// 정의는 paragraph 자식으로 내려온(비-최상위) 이미지의 generateHTML 렌더 경로용이다 - 서버
// lib/content_doc._validate_node는 paragraph 자식에 image가 오는 것을 막지 않는다.
export const ViewerImage = Node.create({
  name: 'image',
  group: 'block',
  atom: true,
  addAttributes() {
    return { src: { default: null } };
  },
  parseHTML() {
    return [{ tag: 'img[src]' }];
  },
  renderHTML({ HTMLAttributes }) {
    // loading:'lazy'를 주지 않는다 - 결정 6(즉시 전량 요청)은 최상위 image뿐 아니라 이
    // 중첩 경로에도 적용된다. lazy면 presigned(600초) 만료 뒤에야 요청돼 403이 날 수
    // 있다(이 경로는 onError 재발급 폴백도 없어 무방비하다).
    return ['img', mergeAttributes(HTMLAttributes)];
  },
});

// 저장 스키마(admin WhitelistLink)는 attrs를 href 하나로 좁혀 target/rel 주입을 막지만,
// 렌더 쪽은 반대로 rel/target을 항상 강제해야 한다(#76 인계 - 링크는 렌더러가
// rel="noopener noreferrer" target="_blank"를 부여). addAttributes를 href만으로 좁혀
// 저장 스키마와의 계약을 명시하고, 정적 HTMLAttributes로 모든 렌더에 rel/target을 합성한다
// (마크 attrs에 없어도 항상 붙는다 - mergeAttributes가 extension 옵션 값을 함께 실어준다).
export const ViewerLink = Link.extend({
  addAttributes() {
    return { href: { default: null } };
  },
}).configure({
  HTMLAttributes: {
    rel: 'noopener noreferrer',
    target: '_blank',
  },
});
// StarterKit이 v3부터 포함하는 heading·목록·codeBlock·code 마크·기본 link는 서버 화이트리스트
// 밖이라 끈다(admin buildEditorExtensions와 동일 목록 - MISTAKES.md "StarterKit v3" 항목).
// underline은 StarterKit 기본 포함이 곧 화이트리스트와 일치해 별도 설정 불요.
export function buildViewerExtensions(): Extensions {
  return [
    StarterKit.configure({
      heading: false,
      blockquote: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      codeBlock: false,
      code: false,
      link: false,
    }),
    ViewerLink,
    ViewerImage,
  ];
}
