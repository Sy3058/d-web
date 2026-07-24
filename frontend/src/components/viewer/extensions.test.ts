// @vitest-environment jsdom
//
// generateHTML(@tiptap/core)은 ProseMirror DOMSerializer로 렌더하므로 실제 DOM(window)이
// 필요하다(공식 문서 "browser-only" 확인, 실측: node 환경에서 "window is not defined").
// vitest.config.ts의 기본 environment:'node'(순수 로직 전용)는 그대로 두고 이 파일만
// 예외로 jsdom을 쓴다 - getSchema만 쓰는 위 스키마 형태 테스트는 DOM이 필요 없다.
import { generateHTML, getSchema } from '@tiptap/core';
import { describe, expect, it } from 'vitest';
import { buildViewerExtensions } from './extensions';

// getSchema는 뷰(NodeView) 없이 ProseMirror 스키마만 뽑는다 - 서버 lib/content_doc의
// 허용 집합과 1:1로 맞는지가 회귀 대상(admin whitelist.test.ts와 동일 패턴).
const extensions = buildViewerExtensions();
const schema = getSchema(extensions);

describe('뷰어 렌더 스키마 화이트리스트 정렬 (서버 content_doc과 1:1)', () => {
  it('화이트리스트 밖 노드·마크는 스키마에 없다', () => {
    const forbiddenNodes = ['heading', 'blockquote', 'bulletList', 'orderedList', 'listItem', 'codeBlock'];
    expect(forbiddenNodes.filter((name) => schema.nodes[name] !== undefined)).toEqual([]);
    expect(schema.marks.code).toBeUndefined();
  });

  it('허용 노드·마크는 스키마에 있다 (paywall 제외 - 서버가 항상 제거해 응답에 없음)', () => {
    const nodes = ['doc', 'paragraph', 'text', 'hardBreak', 'image', 'horizontalRule'];
    const marks = ['bold', 'italic', 'underline', 'strike', 'link'];
    expect(nodes.filter((name) => schema.nodes[name] === undefined)).toEqual([]);
    expect(marks.filter((name) => schema.marks[name] === undefined)).toEqual([]);
    expect(schema.nodes.paywall).toBeUndefined();
  });

  it('image 노드는 src attr만 (저장 스키마의 key가 아니다 - #76 의도된 예외)', () => {
    expect(Object.keys(schema.nodes.image.spec.attrs ?? {})).toEqual(['src']);
  });

  it('link 마크는 href attr만 저장한다(target/rel은 렌더 시 강제 부여라 JSON에 없음)', () => {
    expect(Object.keys(schema.marks.link.spec.attrs ?? {})).toEqual(['href']);
  });
});

describe('generateHTML 렌더 동작', () => {
  it('링크는 href만 담긴 문서에도 rel="noopener noreferrer" target="_blank"가 강제로 붙는다', () => {
    const html = generateHTML(
      {
        type: 'doc',
        content: [
          {
            type: 'paragraph',
            content: [{ type: 'text', text: '링크', marks: [{ type: 'link', attrs: { href: 'https://example.com' } }] }],
          },
        ],
      },
      extensions,
    );
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('target="_blank"');
  });

  it('image 노드는 src attr을 그대로 img 태그에 렌더한다', () => {
    const html = generateHTML(
      { type: 'doc', content: [{ type: 'image', attrs: { src: 'https://r2.example.com/signed?x=1' } }] },
      extensions,
    );
    expect(html).toContain('src="https://r2.example.com/signed?x=1"');
  });
});
