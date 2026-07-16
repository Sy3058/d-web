import { getSchema } from '@tiptap/core';
import { describe, expect, it } from 'vitest';
import { buildEditorExtensions } from './index';

// getSchema는 노드뷰(React)를 만들지 않고 ProseMirror 스키마만 뽑는다 - 화이트리스트 정렬을
// 뷰 없이 검증할 수 있다. 서버 lib/content_doc의 허용 집합과 1:1로 맞는지가 회귀 대상.
const schema = getSchema(buildEditorExtensions(null));

describe('에디터 확장 화이트리스트 정렬 (서버 content_doc과 1:1)', () => {
  it('화이트리스트 밖 노드·마크는 스키마에 없다 (마크다운 단축키로도 422 노드 생성 불가)', () => {
    const forbiddenNodes = ['heading', 'blockquote', 'bulletList', 'orderedList', 'listItem', 'codeBlock'];
    expect(forbiddenNodes.filter((name) => schema.nodes[name] !== undefined)).toEqual([]);
    expect(schema.marks.code).toBeUndefined();
  });

  it('허용 노드·마크는 스키마에 있다', () => {
    const nodes = ['doc', 'paragraph', 'text', 'hardBreak', 'image', 'paywall', 'horizontalRule'];
    const marks = ['bold', 'italic', 'underline', 'strike', 'link'];
    expect(nodes.filter((name) => schema.nodes[name] === undefined)).toEqual([]);
    expect(marks.filter((name) => schema.marks[name] === undefined)).toEqual([]);
  });

  it('link 마크는 href attr만 저장한다 (target/rel은 렌더 전용이라 JSON에 없음)', () => {
    expect(Object.keys(schema.marks.link.spec.attrs ?? {})).toEqual(['href']);
  });

  it('image 노드는 key attr만, paywall 노드는 attr이 없다', () => {
    expect(Object.keys(schema.nodes.image.spec.attrs ?? {})).toEqual(['key']);
    expect(Object.keys(schema.nodes.paywall.spec.attrs ?? {})).toEqual([]);
  });
});
