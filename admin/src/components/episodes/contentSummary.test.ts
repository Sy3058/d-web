import { getSchema } from '@tiptap/core';
import { describe, expect, it } from 'vitest';
import { buildEditorExtensions } from './extensions';
import { contentImageKeys, summarizeContent } from './contentSummary';

const schema = getSchema(buildEditorExtensions(null));

function docFrom(content: unknown[]) {
  // nodeFromJSON은 뷰 없이 PMNode를 만든다 - summarizeContent를 순수 함수로 검증.
  return schema.nodeFromJSON({ type: 'doc', content });
}

describe('summarizeContent', () => {
  it('paywall 앞/뒤로 글자수(공백 제외)와 이미지 수를 나눈다', () => {
    const doc = docFrom([
      { type: 'paragraph', content: [{ type: 'text', text: '무료 다섯자' }] },
      { type: 'paywall' },
      { type: 'paragraph', content: [{ type: 'text', text: '유료 본문' }] },
      { type: 'image', attrs: { key: 'k1' } },
    ]);
    expect(summarizeContent(doc)).toEqual({
      free: { chars: 5, images: 0 },
      paid: { chars: 4, images: 1 },
    });
  });

  it('paywall이 없으면 전부 무료로 집계한다', () => {
    const doc = docFrom([
      { type: 'paragraph', content: [{ type: 'text', text: 'abc' }] },
      { type: 'image', attrs: { key: 'k1' } },
    ]);
    expect(summarizeContent(doc)).toEqual({
      free: { chars: 3, images: 1 },
      paid: { chars: 0, images: 0 },
    });
  });
});

describe('contentImageKeys', () => {
  it('본문 순서를 유지하며 중복 이미지 키를 제거한다', () => {
    const doc = docFrom([
      { type: 'image', attrs: { key: 'k3' } },
      { type: 'image', attrs: { key: 'k1' } },
      { type: 'image', attrs: { key: 'k3' } },
      { type: 'paywall' },
      { type: 'image', attrs: { key: 'k2' } },
    ]);
    expect(contentImageKeys(doc)).toEqual(['k3', 'k1', 'k2']);
  });
});
