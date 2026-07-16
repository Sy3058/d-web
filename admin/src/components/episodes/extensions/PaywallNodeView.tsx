import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { useEffect, useReducer } from 'react';
import { summarizeContent, type ContentStats } from '../contentSummary';

function statLabel(stats: ContentStats): string {
  const parts: string[] = [];
  if (stats.chars > 0) parts.push(`${stats.chars.toLocaleString()}자`);
  if (stats.images > 0) parts.push(`이미지 ${stats.images}장`);
  return parts.length > 0 ? parts.join(' · ') : '없음';
}

export function PaywallNodeView({ editor, selected }: NodeViewProps) {
  // 경계 뒤 분량은 뒤쪽 본문이 바뀔 때마다 달라지지만 노드뷰는 자기 노드가 안 바뀌면
  // 리렌더되지 않는다 - 에디터 update를 구독해 요약을 실시간 갱신한다.
  const [, bump] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    editor.on('update', bump);
    return () => {
      editor.off('update', bump);
    };
  }, [editor]);

  const { free, paid } = summarizeContent(editor.state.doc);
  return (
    <NodeViewWrapper
      data-drag-handle
      contentEditable={false}
      className={`my-3 cursor-grab select-none rounded border-2 border-dashed px-3 py-2 ${
        selected ? 'border-gray-900 bg-gray-100' : 'border-amber-400 bg-amber-50'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-medium text-amber-700">🔒 여기부터 유료</span>
        <span className="text-xs text-gray-600">
          무료 {statLabel(free)} <span className="text-gray-300">|</span> 유료 {statLabel(paid)}
        </span>
      </div>
    </NodeViewWrapper>
  );
}
