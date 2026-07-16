import { Node } from '@tiptap/core';
import { ReactNodeViewRenderer } from '@tiptap/react';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { PaywallNodeView } from './PaywallNodeView';

export const PAYWALL_NAME = 'paywall';

/** 유료 경계 노드. 회차당 **항상 정확히 1개** 존재한다(삽입 버튼 없음). 로드 시 없으면 말미에
 * 넣고(EpisodeEditor), 편집 중 삭제되면 아래 플러그인이 말미에 되살린다. 위치가 곧 무료/유료
 * 경계이고 is_free는 서버가 위치에서 파생한다(attrs 없음 - 경계는 위치가 전부다). */
export const Paywall = Node.create({
  name: PAYWALL_NAME,
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,
  parseHTML() {
    return [{ tag: 'div[data-paywall]' }];
  },
  renderHTML() {
    return ['div', { 'data-paywall': '' }];
  },
  addNodeView() {
    return ReactNodeViewRenderer(PaywallNodeView);
  },
  addProseMirrorPlugins() {
    const type = this.type;
    return [
      new Plugin({
        key: new PluginKey('paywall-singleton'),
        // 항상 정확히 1개 유지: 0개면 말미에 삽입, 2개 이상이면 첫 개만 남긴다(붙여넣기·드래그
        // 복제 방어). 삽입 tr은 1개 상태를 만들어 다음 append에서 no-op이라 루프 없음.
        appendTransaction(transactions, _oldState, newState) {
          if (!transactions.some((tr) => tr.docChanged)) return null;
          const positions: number[] = [];
          newState.doc.forEach((node, pos) => {
            if (node.type === type) positions.push(pos);
          });
          if (positions.length === 1) return null;
          const tr = newState.tr;
          if (positions.length === 0) {
            tr.insert(newState.doc.content.size, type.create());
          } else {
            // 뒤에서부터 지워 앞 위치가 밀리지 않게 한다(paywall은 leaf atom이라 nodeSize=1).
            for (let i = positions.length - 1; i >= 1; i -= 1) {
              tr.delete(positions[i], positions[i] + 1);
            }
          }
          return tr.docChanged ? tr : null;
        },
      }),
    ];
  },
});
