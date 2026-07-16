import Link from '@tiptap/extension-link';

// 서버 화이트리스트(backend lib/content_doc)는 link 마크 attrs를 {href}만 허용한다. TipTap
// 기본 Link는 href·target·rel·class를 attrs로 직렬화해 JSON에 실어 422를 유발하므로, 저장
// attrs에는 href만 남기고 rel/target은 renderHTML(미리보기 DOM)에서만 부여한다.
export const WhitelistLink = Link.extend({
  addAttributes() {
    return { href: { default: null } };
  },
}).configure({
  openOnClick: false,
  autolink: true,
  protocols: ['http', 'https'],
  HTMLAttributes: {
    rel: 'noopener noreferrer nofollow',
    target: '_blank',
  },
});
