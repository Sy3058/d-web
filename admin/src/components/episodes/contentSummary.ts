import type { Node as PMNode } from '@tiptap/pm/model';

export interface ContentStats {
  chars: number;
  images: number;
}

export interface ContentSummary {
  free: ContentStats;
  paid: ContentStats;
}

/** 현재 편집 문서가 실제로 참조하는 이미지 키를 문서 순서대로, 중복 없이 반환한다. */
export function contentImageKeys(doc: PMNode): string[] {
  const seen = new Set<string>();
  const keys: string[] = [];
  doc.descendants((node) => {
    if (node.type.name !== 'image') return;
    const key: unknown = node.attrs.key;
    if (typeof key === 'string' && !seen.has(key)) {
      seen.add(key);
      keys.push(key);
    }
  });
  return keys;
}

function accumulate(node: PMNode, stats: ContentStats): void {
  if (node.type.name === 'image') {
    stats.images += 1;
    return;
  }
  node.descendants((child) => {
    if (child.type.name === 'image') stats.images += 1;
    else if (child.isText && child.text) stats.chars += child.text.replace(/\s/g, '').length;
  });
  if (node.isText && node.text) stats.chars += node.text.replace(/\s/g, '').length;
}

/** 유료 경계(paywall) 앞/뒤 분량 요약. 글자수는 공백 제외. paywall이 없으면 전부 무료로 집계.
 * is_free는 서버가 파생하는 진실이고, 이 요약은 작가에게 경계 위치를 보여주는 UI 보조다. */
export function summarizeContent(doc: PMNode): ContentSummary {
  const free: ContentStats = { chars: 0, images: 0 };
  const paid: ContentStats = { chars: 0, images: 0 };
  let seenPaywall = false;
  doc.forEach((child) => {
    if (child.type.name === 'paywall') {
      seenPaywall = true;
      return;
    }
    accumulate(child, seenPaywall ? paid : free);
  });
  return { free, paid };
}
